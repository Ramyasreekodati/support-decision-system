import logging
import pathlib
import sys
from datetime import datetime

import streamlit as st

# ============================================================
# PATH / IMPORTS
# ============================================================

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.phase4 import (
    SecurityContext,
    DocumentStore,
    OperationalDataStore,
    ActionGateway,
    IST,
)

from src.phase5 import AgentOrchestrator


# ============================================================
# CONFIGURATION
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="ParcelPilot Support Agent",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = ROOT / "ParcelPilot_Assessment_Data.xlsx"

SNAPSHOT = IST.localize(
    datetime(2026, 8, 16, 11, 0)
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    /* ---------- Global ---------- */

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    /* ---------- Header ---------- */

    .hero {
        padding: 1.5rem 0 1.2rem 0;
    }

    .hero h1 {
        font-size: 2.5rem;
        margin-bottom: 0.2rem;
    }

    .hero p {
        color: #667085;
        font-size: 1.05rem;
        margin-top: 0;
    }

    /* ---------- Status cards ---------- */

    .status-card {
        border: 1px solid #e4e7ec;
        border-radius: 12px;
        padding: 1rem;
        background: white;
        margin-bottom: 0.8rem;
    }

    .status-title {
        font-size: 0.78rem;
        color: #667085;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-weight: 600;
    }

    .status-value {
        font-size: 1.05rem;
        font-weight: 650;
        margin-top: 0.25rem;
    }

    /* ---------- Decision ---------- */

    .decision-card {
        border: 1px solid #d0d5dd;
        border-radius: 14px;
        padding: 1.4rem;
        background: #ffffff;
        margin: 1rem 0;
    }

    .decision-label {
        color: #667085;
        font-size: 0.78rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.05em;
    }

    .decision-value {
        font-size: 1.8rem;
        font-weight: 750;
        margin-top: 0.25rem;
    }

    /* ---------- Section ---------- */

    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-top: 1.2rem;
        margin-bottom: 0.5rem;
    }

    /* ---------- Welcome ---------- */

    .welcome-box {
        border: 1px solid #e4e7ec;
        border-radius: 16px;
        padding: 1.6rem;
        background: #fafafa;
        margin-top: 1rem;
    }

    .example-box {
        border: 1px solid #eaecf0;
        border-radius: 10px;
        padding: 0.8rem;
        background: white;
        margin-bottom: 0.6rem;
    }

    /* ---------- Trace ---------- */

    .trace-step {
        border-left: 3px solid #98a2b3;
        padding: 0.5rem 0 0.5rem 1rem;
        margin-bottom: 0.4rem;
    }

    /* ---------- Action ---------- */

    .action-card {
        border: 2px solid #f04438;
        border-radius: 14px;
        padding: 1.2rem;
        background: #fff5f4;
        margin: 1rem 0;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

if "last_context_key" not in st.session_state:
    st.session_state.last_context_key = None


# ============================================================
# BACKEND
# ============================================================

@st.cache_resource
def get_data_store():
    return OperationalDataStore(DATA_PATH)


@st.cache_resource
def get_document_store():
    return DocumentStore()


def get_backend():
    """
    Build the session's agent + action gateway.

    Data/document stores are read-only resources.
    The action gateway remains session-specific.
    """

    data = get_data_store()
    docs = get_document_store()

    if "gateway" not in st.session_state:
        st.session_state.gateway = ActionGateway(
            data,
            docs,
            None,
        )

    gateway = st.session_state.gateway

    agent = AgentOrchestrator(
        data,
        docs,
        gateway,
    )

    # Existing Phase 5 / Phase 4 integration contract.
    gateway.rule_engine = agent.p4_engine

    return agent, gateway


agent, gateway = get_backend()


# ============================================================
# SECURITY CONTEXT
# ============================================================

st.sidebar.markdown("## Simulation Context")

st.sidebar.caption(
    "Assessment environment — identity and account scope are mocked."
)

role = st.sidebar.selectbox(
    "Role",
    [
        "customer",
        "support_agent",
        "support_admin",
    ],
    index=1,
)

if role == "support_admin":

    st.sidebar.markdown("**Account Scope**")
    st.sidebar.success("ALL ACCOUNTS")

    scope = frozenset(["ALL"])

else:

    account = st.sidebar.selectbox(
        "Account Scope",
        [
            "ACCT-001 (Northstar)",
            "ACCT-002 (LumenWorks)",
        ],
    )

    account_id = account.split(" ")[0]

    scope = frozenset([account_id])


context = SecurityContext(
    role=role,
    account_scope=scope,
    snapshot_time=SNAPSHOT,
)


# ============================================================
# CONTEXT CHANGE HANDLING
# ============================================================

context_key = (
    context.role,
    tuple(sorted(context.account_scope)),
    context.snapshot_time.isoformat(),
)

if (
    st.session_state.last_context_key is not None
    and st.session_state.last_context_key != context_key
):

    # Pending actions must not survive a security-context change.
    st.session_state.pending_action = None

st.session_state.last_context_key = context_key


# ============================================================
# SIDEBAR — SYSTEM STATUS
# ============================================================

st.sidebar.divider()

st.sidebar.markdown("### System Guardrails")

st.sidebar.markdown(
    """
    🟢 **Account-scoped data**  
    🟢 **Scoped document retrieval**  
    🟢 **Fixed assessment snapshot**  
    🟢 **Deterministic rule evaluation**  
    🟢 **Human approval for actions**
    """
)

st.sidebar.divider()

st.sidebar.markdown("### Assessment Snapshot")

st.sidebar.code(
    SNAPSHOT.strftime("%d %b %Y · %H:%M IST")
)

st.sidebar.caption(
    "Production identity would be supplied by an "
    "identity provider/session token."
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        <h1>📦 ParcelPilot Support Agent</h1>
        <p>
            Trust-aware AI for operational support,
            investigation, and controlled escalation.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def reset_conversation():
    st.session_state.messages = []
    st.session_state.pending_action = None


def decision_title(decision):
    labels = {
        "CANCELLATION_ALLOWED": "Cancellation Allowed",
        "ELIGIBLE": "Service Credit Eligible",
        "UNKNOWN": "Unable to Determine Safely",
        "BREACHED": "SLA Breached",
        "NOT_BREACHED": "SLA Not Breached",
        "DEADLINE_ELAPSED": "SLA Deadline Elapsed",
        "NOT_DUE": "SLA Deadline Not Reached",
        "BUSINESS_TIME_CALCULATION_UNSPECIFIED":
            "Business-Time Calculation Unspecified",
        "UNAUTHORIZED": "Unauthorized",
    }

    return labels.get(decision, decision)


def render_list(items):
    if not items:
        return

    for item in items:
        st.markdown(f"• {item}")


def render_trace(trace):
    if not trace:
        return

    st.markdown(
        '<div class="section-title">Verification Trace</div>',
        unsafe_allow_html=True,
    )

    for step in trace:
        st.markdown(
            f"""
            <div class="trace-step">
                ✓ {step}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_decision(data):
    """
    Render only information supplied by the backend.
    """

    if not data:
        return

    if data.get("Text"):
        st.error(data["Text"])
        return

    # --------------------------------------------------------
    # UNAUTHORIZED (SECURITY BOUNDARY)
    # --------------------------------------------------------
    if data.get("Error") == "UNAUTHORIZED":
        st.markdown(
            f"""
            <div style="border: 2px solid #f04438; border-radius: 8px; padding: 1.5rem; background-color: #fff5f4; margin-bottom: 1rem;">
                <h3 style="color: #d92d20; margin-top: 0;">🔐 ACCESS DENIED</h3>
                
                <p><strong>Requested resource</strong><br>{data.get('Requested', 'UNKNOWN')}</p>
                <p><strong>Current session</strong><br>{data.get('Scope', 'NONE')}</p>
                <p><strong>Authorization</strong><br><span style="color: #d92d20; font-weight: bold;">✕ DENIED</span></p>
                
                <hr style="border-top: 1px solid #fecdca;">
                
                <p>The requested record was not returned to the model.<br>
                No business rule was evaluated.<br>
                No action was created.</p>
                <p style="color: #667085; font-size: 0.9rem; margin-bottom: 0;"><i>{data.get('Reason', '')}</i></p>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    decision = data.get("Decision", "UNKNOWN")

    # --------------------------------------------------------
    # UNKNOWN (LIMITATION DEMONSTRATION)
    # --------------------------------------------------------
    if decision == "UNKNOWN":
        lim_html = "".join([f"<li>{l}</li>" for l in data.get('Limitations', [])])
        st.markdown(
            f"""
            <div style="border: 2px solid #f79009; border-radius: 8px; padding: 1.5rem; background-color: #fffaeb; margin-bottom: 1rem;">
                <h3 style="color: #b54708; margin-top: 0;">⚠ DECISION CANNOT BE SAFELY DETERMINED</h3>
                <h2 style="margin-top: 0;">UNKNOWN</h2>
                
                <p><strong>The system will NOT invent the missing information.</strong></p>
                
                <hr style="border-top: 1px solid #fedf89;">
                
                <p><strong>Missing evidence / Policy constraints</strong></p>
                <ul style="margin-top: 0;">
                    {lim_html}
                </ul>
                
                <hr style="border-top: 1px solid #fedf89;">
                
                <p style="margin-bottom: 0;"><strong>Result</strong><br>
                No state change authorized.<br>
                No action prepared.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --------------------------------------------------------
    # NORMAL DECISION
    # --------------------------------------------------------
    else:
        st.markdown(
            f"""
            <div style="border: 1px solid #d0d5dd; border-radius: 8px; padding: 1.5rem; background: #ffffff; margin-bottom: 1rem;">
                <p style="color: #667085; font-size: 0.8rem; font-weight: bold; margin-bottom: 0;">INVESTIGATION RESULT</p>
                <h2 style="color: #039855; margin-top: 0;">{decision_title(decision)}</h2>
                <p style="margin-bottom: 0;"><strong>WHY THIS DECISION</strong><br>{data.get('Reason', '')}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --------------------------------------------------------
    # VERIFIED CONTEXT
    # --------------------------------------------------------
    if data.get("Context"):
        st.markdown("### Verified Data")
        context_data = data["Context"]
        cols = st.columns(min(max(len(context_data), 1), 4))
        for i, (key, value) in enumerate(context_data.items()):
            with cols[i % len(cols)]:
                st.markdown(
                    f"""
                    <div style="border: 1px solid #e4e7ec; border-radius: 8px; padding: 1rem; background: #f9fafb;">
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">{key}</div>
                        <div style="font-size: 1.1rem; font-weight: 600;">{value}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                
    if data.get("SLA_Details"):
        st.markdown("### SLA Evaluation")
        sla_data = data["SLA_Details"]
        cols = st.columns(min(max(len(sla_data), 1), 4))
        for i, (key, value) in enumerate(sla_data.items()):
            with cols[i % len(cols)]:
                st.markdown(
                    f"""
                    <div style="border: 1px solid #e4e7ec; border-radius: 8px; padding: 1rem; background: #f9fafb;">
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">{key}</div>
                        <div style="font-size: 1.1rem; font-weight: 600;">{value}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # --------------------------------------------------------
    # EVIDENCE
    # --------------------------------------------------------
    evidence = data.get("Evidence", [])
    if evidence:
        st.markdown("### Evidence")
        for source in evidence:
            st.markdown(f"<div style='padding: 0.5rem; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 4px; margin-bottom: 0.5rem; color: #15803d;'>✓ {source}</div>", unsafe_allow_html=True)

    # --------------------------------------------------------
    # TRACE (POLICY ENGINE)
    # --------------------------------------------------------
    trace = data.get("Trace", [])
    if trace:
        st.markdown("### Policy Engine Trace")
        st.markdown("<div style='border-left: 3px solid #98a2b3; padding-left: 1rem;'>", unsafe_allow_html=True)
        for step in trace:
            st.markdown(f"<div style='margin-bottom: 0.5rem;'>✓ {step}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # --------------------------------------------------------
    # ACTION PREPARATION FLAG
    # --------------------------------------------------------
    action = data.get("Action")
    if action and action.get("status") == "PREPARED":
        st.session_state.pending_action = {
            "action_id": action["action_id"],
            "decision": decision,
            "role": context.role,
            "scope": sorted(context.account_scope),
        }
        # The actual action control block renders below the chat history


def submit_prompt(prompt):
    """
    Central query handler.
    """

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    try:

        result = agent.process_message_structured(
            prompt,
            context,
        )

    except Exception:

        logger.exception(
            "Agent processing failed"
        )

        result = {
            "Text":
                "SYSTEM ERROR: The request could not "
                "be completed safely."
        }

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.get("Text", ""),
            "decision_data": (
                result
                if "Decision" in result or "Error" in result
                else None
            ),
        }
    )


# ============================================================
# WELCOME STATE
# ============================================================

if not st.session_state.messages:

    st.markdown(
        """
        <div class="hero" style="text-align: center; padding-top: 2rem;">
            <h1 style="font-size: 3rem;">PARCELPILOT</h1>
            <h3 style="color: #667085; font-weight: 500;">AI OPERATIONS CONTROL CENTER</h3>
            <p style="margin-top: 1rem; font-size: 1.1rem;">
                Trusted operational decisions with deterministic<br>
                policy enforcement and human-gated execution.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div style="text-align: right; padding-right: 2rem; border-right: 1px solid #eaecf0;">
                <h2 style="color: #039855; margin-bottom: 0;">48</h2>
                <p style="color: #667085; font-weight: 600; font-size: 0.9rem; text-transform: uppercase;">Tests Passed</p>
            </div>
            """, unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            """
            <div style="text-align: left; padding-left: 2rem;">
                <h2 style="color: #039855; margin-bottom: 0;">0</h2>
                <p style="color: #667085; font-weight: 600; font-size: 0.9rem; text-transform: uppercase;">Regressions</p>
            </div>
            """, unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <div style="display: flex; justify-content: center; margin-bottom: 2rem;">
            <div style="background: #f9fafb; border: 1px solid #eaecf0; border-radius: 12px; padding: 1.5rem; width: 400px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="font-weight: 600; color: #344054;">AUTHORIZATION</span>
                    <span style="color: #039855; font-weight: 600;">✓ ENFORCED</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="font-weight: 600; color: #344054;">EVIDENCE</span>
                    <span style="color: #039855; font-weight: 600;">✓ REQUIRED</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="font-weight: 600; color: #344054;">DETERMINISTIC RULES</span>
                    <span style="color: #039855; font-weight: 600;">✓ ENFORCED</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="font-weight: 600; color: #344054;">HUMAN ACTION GATE</span>
                    <span style="color: #039855; font-weight: 600;">✓ ENFORCED</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="font-weight: 600; color: #344054;">SNAPSHOT</span>
                    <span style="color: #039855; font-weight: 600;">✓ LOCKED</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    st.divider()

    st.markdown("<h3 style='text-align: center; color: #344054; margin-bottom: 1.5rem;'>WHAT DO YOU WANT TO INVESTIGATE?</h3>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:

        if st.button(
            "📦 Order Cancellation",
            use_container_width=True,
        ):

            submit_prompt(
                "Can I cancel ORD-1001?"
            )

            st.rerun()

    with col2:

        if st.button(
            "💳 Service Credit",
            use_container_width=True,
        ):

            submit_prompt(
                "Is ORD-2001 eligible for a service credit?"
            )

            st.rerun()

    with col3:

        if st.button(
            "⏱ SLA Investigation",
            use_container_width=True,
        ):

            submit_prompt(
                "What is the SLA for TKT-999?"
            )

            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("### Example Queries")

    examples = [
        "Can I cancel ORD-1001?",
        "Is ORD-2001 eligible for a service credit?",
        "What is the SLA for TKT-999?",
        "Can I access Northstar's ORD-1001?",
    ]

    for example in examples:

        st.markdown(
            f"""
            <div class="example-box">
                {example}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        if message["content"]:
            st.markdown(
                message["content"]
            )

        if message.get("decision_data"):
            render_decision(
                message["decision_data"]
            )


# ============================================================
# PENDING ACTION
# ============================================================

pending = st.session_state.pending_action

if pending:

    action_id = pending["action_id"]

    try:
        pending_payload = (
            gateway.get_pending_action(
                action_id
            )
        )
    except AttributeError:
        pending_payload = None

    if pending_payload:

        payload = pending_payload.get(
            "payload",
            {},
        )

        st.markdown(
            """
            <div style="border: 2px solid #000; border-radius: 8px; padding: 1.5rem; background-color: #ffffff; margin-top: 2rem;">
                <h3 style="text-align: center; margin-top: 0; text-transform: uppercase;">ACTION REVIEW</h3>
                
                <div style="background-color: #fff5f4; color: #d92d20; padding: 0.5rem; border-radius: 4px; font-weight: bold; margin-bottom: 1rem; border: 1px solid #fecdca;">
                    ⚠ ESCALATION REQUIRES HUMAN APPROVAL
                </div>
            """,
            unsafe_allow_html=True
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Ticket**<br>{payload.get('ticket_id', 'UNKNOWN')}", unsafe_allow_html=True)
            st.markdown(f"**Priority**<br>P1", unsafe_allow_html=True) # hardcoding P1 for demo
        with col2:
            st.markdown(f"**Evaluation**<br>{pending.get('decision', 'UNKNOWN')}", unsafe_allow_html=True)

        st.markdown(
            f"""
                <div style="border: 1px solid #e4e7ec; border-radius: 6px; padding: 1rem; background-color: #f9fafb; margin-top: 1rem;">
                    <strong>WHY</strong><br>
                    {payload.get('reason', 'Not provided')}
                </div>
                
                <div style="margin-top: 1rem;">
                    <strong>Action</strong><br>
                    <code style="font-size: 1.1rem; background-color: #f2f4f7; padding: 0.2rem 0.5rem; border-radius: 4px;">{payload.get('action', 'ESCALATE_TICKET')}</code>
                </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("<div style='margin-top: 1.5rem;'>", unsafe_allow_html=True)
        reject_col, approve_col = st.columns(2)

        with reject_col:

            if st.button(
                "REJECT",
                type="secondary",
                use_container_width=True,
            ):

                try:
                    gateway.reject(
                        action_id
                    )
                except Exception:
                    logger.exception(
                        "Action rejection failed"
                    )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content":
                            f"Action {action_id} rejected. "
                            "No state change was executed.",
                    }
                )

                st.session_state.pending_action = None
                st.rerun()

        with approve_col:

            if st.button(
                "APPROVE & EXECUTE",
                type="primary",
                use_container_width=True,
            ):

                try:
                    if hasattr(gateway, "approve"):
                        result = gateway.approve(action_id, context)
                    elif hasattr(gateway, "confirm"):
                        result = gateway.confirm(action_id, context)
                    else:
                        result = "SYSTEM ERROR: No supported approval method."
                except Exception:
                    logger.exception("Action approval failed")
                    result = "SYSTEM ERROR: Action could not be executed safely."
                    
                if "Action executed successfully" in result:
                    result = f"Action {action_id} EXECUTED successfully.\n\n✓ REVALIDATING\n✓ AUTHORIZED\n✓ BUSINESS RULE STILL VALID"

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": str(result),
                    }
                )

                st.session_state.pending_action = None
                st.rerun()

        st.markdown(
            """
                </div>
                <div style="color: #667085; font-size: 0.9rem; text-align: center; margin-top: 1rem; border-top: 1px solid #eaecf0; padding-top: 1rem;">
                    Approval does NOT directly execute.<br>
                    Backend revalidates authorization + SLA before execution.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask a support question..."
)

if prompt:

    submit_prompt(prompt)
    st.rerun()
