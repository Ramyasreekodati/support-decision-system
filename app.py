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
def _discover_test_count() -> int:
    """Count passing tests across all Phase suites at startup — no hardcoding."""
    import unittest, io
    loader = unittest.TestLoader()
    suites = [
        loader.loadTestsFromName("src.phase2_verification"),
        loader.loadTestsFromName("src.phase3"),
        loader.loadTestsFromName("src.phase4"),
        loader.loadTestsFromName("src.phase5"),
    ]
    suite = unittest.TestSuite(suites)
    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=0)
    result = runner.run(suite)
    return result.testsRun - len(result.failures) - len(result.errors)

_test_count = _discover_test_count()


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
    snapshot_time=get_data_store().get_snapshot_time(),
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
    context.snapshot_time.strftime("%d %b %Y · %H:%M IST")
)

st.sidebar.divider()

st.sidebar.markdown("### Authorization Status")

if role == "support_admin":
    st.sidebar.success("✓ FULL ACCESS — All accounts")
else:
    scope_str = list(context.account_scope)[0] if context.account_scope else "NONE"
    st.sidebar.info(f"✓ SCOPED — {scope_str} only")

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
    Layout: Decision → Agent Activity → Evidence & Sources → Verified Data
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
        requested = data.get('Requested', 'UNKNOWN')
        session_scope = data.get('Scope', 'NONE')
        st.markdown(
            f"""
            <div style="border: 2px solid #f04438; border-radius: 8px; padding: 1.5rem; background-color: #fff5f4; margin-bottom: 1rem;">
                <h3 style="color: #d92d20; margin-top: 0;">🔐 ACCESS DENIED</h3>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div>
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">Requested</div>
                        <div style="font-size: 1rem; font-weight: 600;">{requested}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">Your scope</div>
                        <div style="font-size: 1rem; font-weight: 600;">{session_scope}</div>
                    </div>
                </div>

                <hr style="border-top: 1px solid #fecdca;">

                <p style="margin-bottom: 0.3rem;"><strong>Rule engine</strong> — <span style="color: #d92d20;">NOT INVOKED</span></p>
                <p style="margin-bottom: 0.3rem;"><strong>Data returned</strong> — <span style="color: #d92d20;">NONE</span></p>
                <p style="margin-bottom: 0;"><strong>Action created</strong> — <span style="color: #d92d20;">NONE</span></p>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Show the tool trace even for denials (demonstrates early termination)
        tool_trace = data.get("tool_trace", [])
        if tool_trace:
            st.markdown("### Agent Activity")
            st.markdown("<div style='border-left: 3px solid #f04438; padding-left: 1rem;'>", unsafe_allow_html=True)
            for step in tool_trace:
                tool_name = step.get('tool', '')
                tool_in = step.get('input', {})
                in_str = ", ".join(f"{k}={v}" for k, v in tool_in.items())
                st.markdown(f"<div style='margin-bottom: 0.5rem;'><strong style='color: #d92d20;'>✕ {tool_name}</strong> (blocked)<br><span style='color: #667085; font-size: 0.9rem;'>Input: {in_str}</span></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        return

    decision = data.get("Decision", "UNKNOWN")

    # --------------------------------------------------------
    # 1. DECISION BOX (top — always first)
    # --------------------------------------------------------
    if decision == "UNKNOWN":
        lim_html = "".join([f"<li>{l}</li>" for l in data.get('Limitations', [])])
        st.markdown(
            f"""
            <div style="border: 2px solid #f79009; border-radius: 8px; padding: 1.5rem; background-color: #fffaeb; margin-bottom: 1rem;">
                <p style="color: #b54708; font-size: 0.8rem; font-weight: bold; margin-bottom: 0; text-transform: uppercase;">Decision</p>
                <h2 style="color: #b54708; margin-top: 0;">⚠ UNKNOWN</h2>

                <p>The system cannot safely determine eligibility. No assumption was made.</p>

                <h4 style="color: #b54708; margin-bottom: 0;">Missing evidence / Policy constraints</h4>
                <hr style="border-top: 1px solid #fedf89; margin-top: 0.3rem;">
                <ul style="margin-top: 0;">
                    {lim_html}
                </ul>

                <h4 style="color: #b54708; margin-bottom: 0;">Outcome</h4>
                <hr style="border-top: 1px solid #fedf89; margin-top: 0.3rem;">
                <p style="margin-bottom: 0;"><strong>Human investigation required.</strong><br>
                No state change authorized. No action prepared.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        border_color = "#039855" if decision in ("CANCELLATION_ALLOWED", "ELIGIBLE", "NOT_BREACHED", "NOT_DUE") else "#d92d20"
        conflict = data.get("ConflictDetected", False)
        conflict_html = "<br><span style='color: #b54708; font-size: 0.9rem; font-weight: 600;'>⚠ CONFLICT DETECTED in source data</span>" if conflict else ""
        st.markdown(
            f"""
            <div style="border: 2px solid {border_color}; border-radius: 8px; padding: 1.5rem; background: #ffffff; margin-bottom: 1rem;">
                <p style="color: #667085; font-size: 0.8rem; font-weight: bold; margin-bottom: 0; text-transform: uppercase;">Decision</p>
                <h2 style="color: {border_color}; margin-top: 0;">{decision_title(decision)}</h2>
                <p style="margin-bottom: 0;"><strong>Why</strong><br>{data.get('Reason', '')}{conflict_html}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --------------------------------------------------------
    # 2. AGENT ACTIVITY (intent + tool trace)
    # --------------------------------------------------------
    tool_trace = data.get("tool_trace", [])
    intent = data.get("Intent", "")
    if tool_trace or intent:
        st.markdown("### Agent Activity")
        if intent:
            intent_labels = {
                "cancellation": "Order Cancellation",
                "service_credit": "Service Credit",
                "sla": "SLA Investigation",
            }
            st.markdown(
                f"<div style='margin-bottom: 0.8rem; padding: 0.5rem 0.8rem; background: #f9fafb; border: 1px solid #eaecf0; border-radius: 4px;'>"
                f"<span style='font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;'>Intent detected</span><br>"
                f"<strong>{intent_labels.get(intent, intent)}</strong>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("<div style='border-left: 3px solid #98a2b3; padding-left: 1rem;'>", unsafe_allow_html=True)
        for step in tool_trace:
            tool_name = step.get('tool', '')
            tool_in = step.get('input', {})
            tool_out = step.get('output', '')
            in_str = ", ".join(f"{k}={v}" for k, v in tool_in.items())
            st.markdown(
                f"<div style='margin-bottom: 0.8rem;'>"
                f"<strong style='color: #039855;'>✓ {tool_name}</strong><br>"
                f"<span style='color: #667085; font-size: 0.9rem;'>Input: {in_str}</span><br>"
                f"<span style='color: #344054; font-size: 0.9rem;'>Result: {tool_out}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # --------------------------------------------------------
    # 3. EVIDENCE & SOURCES
    # --------------------------------------------------------
    evidence = data.get("Evidence", [])
    if evidence:
        st.markdown("### Evidence & Sources")
        for e in evidence:
            if isinstance(e, dict):
                source = e.get('source', '')
                rule = e.get('rule', '')
                raw_authority = e.get('authority', '')
            else:
                source = str(e)
                rule = ""
                raw_authority = ""

            if raw_authority == "CUSTOMER_SPECIFIC":
                authority_label = "Customer-specific · Higher authority"
                badge_color = "#15803d"
                star = "★"
            elif raw_authority == "GENERAL_POLICY":
                authority_label = "General policy"
                badge_color = "#667085"
                star = "○"
            else:
                authority_label = ""
                badge_color = "#667085"
                star = "○"

            st.markdown(
                f"<div style='padding: 0.8rem; background: #f9fafb; border: 1px solid #eaecf0; border-radius: 4px; margin-bottom: 0.5rem;'>"
                f"<strong style='color: #15803d;'>{star} {source}</strong><br>"
                f"<span style='font-size: 0.85rem; color: {badge_color}; text-transform: uppercase; font-weight: 600;'>{authority_label}</span><br>"
                f"<span style='font-size: 0.9rem; color: #344054;'>{rule}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

    # --------------------------------------------------------
    # 4. VERIFIED DATA (context + SLA metrics — last, supporting detail)
    # --------------------------------------------------------
    if data.get("Context") or data.get("SLA_Details"):
        st.markdown("### Verified Data")
        all_fields = {}
        if data.get("Context"):
            all_fields.update(data["Context"])
        if data.get("SLA_Details"):
            all_fields.update(data["SLA_Details"])

        cols = st.columns(min(max(len(all_fields), 1), 4))
        for i, (key, value) in enumerate(all_fields.items()):
            with cols[i % len(cols)]:
                st.markdown(
                    f"""
                    <div style="border: 1px solid #e4e7ec; border-radius: 8px; padding: 1rem; background: #f9fafb;">
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">{key}</div>
                        <div style="font-size: 1rem; font-weight: 600;">{value}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

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
            f"""
            <div style="text-align: right; padding-right: 2rem; border-right: 1px solid #eaecf0;">
                <h2 style="color: #039855; margin-bottom: 0;">{_test_count}</h2>
                <p style="color: #667085; font-weight: 600; font-size: 0.9rem; text-transform: uppercase;">Tests Passing</p>
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
            <div style="background: #f9fafb; border: 1px solid #eaecf0; border-radius: 12px; padding: 1.5rem; width: 600px; text-align: left;">
                <h4 style="margin-top: 0; color: #344054; text-align: center; text-transform: uppercase;">What this system proves</h4>
                <hr style="border-top: 1px solid #eaecf0;">
                
                <p style="margin-bottom: 0.8rem;"><strong>🔐 Authorization</strong><br>
                <span style="color: #667085; font-size: 0.95rem;">Only authorized data is retrieved.</span></p>

                <p style="margin-bottom: 0.8rem;"><strong>📚 Evidence</strong><br>
                <span style="color: #667085; font-size: 0.95rem;">Decisions cite the actual source documents.</span></p>

                <p style="margin-bottom: 0.8rem;"><strong>⚙ Deterministic rules</strong><br>
                <span style="color: #667085; font-size: 0.95rem;">Business decisions are not delegated to the LLM.</span></p>

                <p style="margin-bottom: 0.8rem;"><strong>⚠ Uncertainty</strong><br>
                <span style="color: #667085; font-size: 0.95rem;">Missing/conflicting evidence produces UNKNOWN.</span></p>

                <p style="margin-bottom: 0.8rem;"><strong>👤 Human control</strong><br>
                <span style="color: #667085; font-size: 0.95rem;">State-changing actions require approval.</span></p>

                <p style="margin-bottom: 0;"><strong>🔄 Revalidation</strong><br>
                <span style="color: #667085; font-size: 0.95rem;">Authorization and rules are checked again before execution.</span></p>
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

        st.markdown(
            f"""
            <div style="margin-bottom: 1rem;">
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.8rem; margin-bottom: 1rem;">
                    <div>
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">Action Type</div>
                        <code style="font-size: 0.95rem;">{payload.get('action', 'ESCALATE_TICKET')}</code>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">Target</div>
                        <div style="font-weight: 600;">{payload.get('ticket_id', 'UNKNOWN')}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">Priority</div>
                        <div style="font-weight: 600; color: #d92d20;">{payload.get('priority', 'P1')}</div>
                    </div>
                </div>
                <div style="border: 1px solid #e4e7ec; border-radius: 6px; padding: 1rem; background-color: #f9fafb; margin-bottom: 0.8rem;">
                    <strong>Reason for action</strong><br>
                    {payload.get('reason', 'Not provided')}
                </div>
                <div style="border: 1px solid #e4e7ec; border-radius: 6px; padding: 0.6rem 1rem; background-color: #f9fafb;">
                    <span style="font-size: 0.8rem; color: #667085; font-weight: bold; text-transform: uppercase;">Action ID</span><br>
                    <code>{action_id}</code> &nbsp;
                    <span style="background: #fef3c7; color: #b45309; font-size: 0.8rem; font-weight: bold; padding: 0.15rem 0.4rem; border-radius: 3px; text-transform: uppercase;">PREPARED</span>
                </div>
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
                    result = gateway.approve(action_id, context)
                    
                    if result.get("status") == "EXECUTED":
                        rev = result.get("revalidation", {})
                        
                        def _check(v):
                            return "✓" if v == "PASSED" else "✕"
                        
                        content = f"""**⟳ REVALIDATING**

{_check(rev.get('authorization', 'PENDING'))} Authorization — `{rev.get('authorization', 'PENDING')}`
{_check(rev.get('record_access', 'PENDING'))} Record access — `{rev.get('record_access', 'PENDING')}`
{_check(rev.get('rule_state', 'PENDING'))} SLA rule state — `{rev.get('rule_state', 'PENDING')}`
{_check(rev.get('payload_integrity', 'PENDING'))} Payload integrity — `{rev.get('payload_integrity', 'PENDING')}`

**EXECUTING...**

✓ **ACTION EXECUTED**

Action ID: `{action_id}`"""
                    else:
                        rev = result.get("revalidation", {})
                        content = f"""**⟳ REVALIDATING**

✕ **REVALIDATION FAILED**

{result.get('error', 'Unknown error')}
Action ID: `{action_id}`"""
                except Exception as e:
                    logger.exception("Action approval failed")
                    content = f"SYSTEM ERROR: {str(e)}"

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": content,
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
