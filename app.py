import sys
import pathlib

# Ensure repository root is in Python sys.path for Streamlit Cloud deployment
ROOT_DIR = pathlib.Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import logging
import html
from typing import Dict, Any, Optional

import streamlit as st
from src.security.authorization import SecurityContext
from src.agent.agent_service import get_agent_service, AgentService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="ParcelPilot Support & Decision System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------
# Custom CSS (Presentation Styling Only)
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .hero-box {
        padding: 1.5rem 2rem;
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        color: white;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .hero-title {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        color: #F8FAFC;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: #94A3B8;
        margin-top: 0.4rem;
        margin-bottom: 0;
    }
    .badge-customer {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        background-color: #EDE9FE;
        color: #6D28D9;
        font-weight: 600;
        font-size: 0.75rem;
        border-radius: 6px;
        border: 1px solid #DDD6FE;
    }
    .badge-general {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        background-color: #F1F5F9;
        color: #475569;
        font-weight: 600;
        font-size: 0.75rem;
        border-radius: 6px;
        border: 1px solid #E2E8F0;
    }
    .action-card {
        border: 2px solid #F59E0B;
        background-color: #FFFBEB;
        border-radius: 8px;
        padding: 1.2rem;
        margin: 1rem 0;
    }
    .cluster-card {
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        background-color: #FFFFFF;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Service & Session Initialization
# ------------------------------------------------------------
agent_service: AgentService = get_agent_service()
snapshot_time = agent_service.get_snapshot_time()

if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {}
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

# ------------------------------------------------------------
# Sidebar: Identity & System Guardrails
# ------------------------------------------------------------
st.sidebar.markdown("## 🛡️ Identity & Security")

role = st.sidebar.selectbox(
    "Active Role",
    options=["support_admin", "customer"],
    format_func=lambda r: "Support Admin (Full Access)" if r == "support_admin" else "Customer (Scoped)",
    help="Demo identity selector for constructing the request SecurityContext."
)

if role == "support_admin":
    scope = frozenset(["ALL"])
    account_label = "ALL Accounts (Support Admin)"
    st.sidebar.success("✓ Authorization: FULL ACCESS (All Accounts)")
else:
    account_choice = st.sidebar.selectbox(
        "Tenant Account",
        options=["ACCT-001", "ACCT-002", "ACCT-003", "ACCT-004"],
        format_func=lambda a: {
            "ACCT-001": "ACCT-001 — Northstar Logistics (Enterprise)",
            "ACCT-002": "ACCT-002 — LumenWorks Inc. (Growth)",
            "ACCT-003": "ACCT-003 — Beacon Retail (Standard)",
            "ACCT-004": "ACCT-004 — Axis Labs (Enterprise)"
        }.get(a, a)
    )
    scope = frozenset([account_choice])
    account_label = account_choice
    st.sidebar.info(f"✓ Authorization: SCOPED ({account_choice} only)")

context = SecurityContext(
    role=role,
    account_scope=scope,
    snapshot_time=snapshot_time,
)

context_key = f"{role}:{sorted(list(scope))}"
if context_key not in st.session_state.chat_histories:
    st.session_state.chat_histories[context_key] = []

active_history = st.session_state.chat_histories[context_key]

st.sidebar.divider()

st.sidebar.markdown("### 🤖 Agent Engine Mode")

custom_api_key = st.sidebar.text_input("🔑 Gemini API Key (Optional)", type="password", help="Paste your Gemini API key to activate live LLM agent")
if custom_api_key:
    agent_service.set_api_key(custom_api_key)

if agent_service.is_live_mode:
    st.sidebar.success("🟢 **LIVE AGENT** — Gemini Tool Calling")
else:
    st.sidebar.warning("⚙️ **OFFLINE TEST ENGINE**\n\n*Deterministic fixture (add key above for live LLM)*")

st.sidebar.divider()

st.sidebar.markdown("### ⏱️ Dataset Snapshot")
st.sidebar.code(snapshot_time.strftime("%d %b %Y · %H:%M IST"))

st.sidebar.divider()

if st.sidebar.button("🧹 Clear This Session", use_container_width=True):
    st.session_state.chat_histories[context_key] = []
    st.session_state.pending_action = None
    st.rerun()

# ------------------------------------------------------------
# Header
# ------------------------------------------------------------
st.markdown(
    f"""
    <div class="hero-box">
        <h1 class="hero-title">📦 ParcelPilot Support & Decision System</h1>
        <p class="hero-subtitle">Active Identity: <strong>{account_label}</strong> · Deterministic safety boundaries · Proactive queue monitoring · Human-gated action governance.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Core UI Rendering Helpers
# ------------------------------------------------------------
def render_decision_card(data: Dict[str, Any]):
    decision = data.get("Decision")
    if not decision:
        return

    if any(k in decision for k in ["ALLOWED", "ELIGIBLE", "NOT_BREACHED", "PROACTIVE"]):
        st.success(f"### Decision: {decision}")
    elif any(k in decision for k in ["UNKNOWN", "UNSPECIFIED", "WARNING", "NOT_ALLOWED"]):
        st.warning(f"### Decision: ⚠️ {decision}")
    elif any(k in decision for k in ["BREACHED", "DEADLINE_ELAPSED"]):
        st.error(f"### Decision: 🚨 {decision}")
    else:
        st.info(f"### Decision: {decision}")

    if data.get("Reason"):
        st.markdown(f"**Explanation:** {data['Reason']}")

    limitations = data.get("limitations") or data.get("Limitations") or []
    if limitations:
        with st.expander("⚠️ Operational Limitations / Missing Information", expanded=True):
            for lim in limitations:
                st.markdown(f"- {lim}")

def render_tool_trace(tool_trace: list):
    if not tool_trace:
        return
    with st.expander("🔍 Agent Activity & Tool Calls", expanded=False):
        for step in tool_trace:
            tool_name = step.get("tool", "unknown_tool")
            status = step.get("status", "SUCCESS")
            inp = step.get("input", {})
            out = step.get("output", {})

            status_icon = "✓" if status == "SUCCESS" else "⚠️" if status == "UNAUTHORIZED" else "✗"
            st.markdown(f"**{status_icon} `{tool_name}`** — Status: `{status}`")
            st.json({"arguments": inp, "result_summary": out})

def render_evidence_panel(evidence_list: list):
    if not evidence_list:
        return
    with st.expander("📄 Evidence & Policy Citations", expanded=True):
        for ev in evidence_list:
            if isinstance(ev, dict):
                src = ev.get("source", "Unknown Document")
                rule = ev.get("rule", "Applicable Rule")
                auth = ev.get("authority", "GENERAL_POLICY")
                
                badge_class = "badge-customer" if auth == "CUSTOMER_SPECIFIC" else "badge-general"
                badge_label = "Customer Agreement (Override)" if auth == "CUSTOMER_SPECIFIC" else "General Policy SOP"
                
                st.markdown(
                    f"<span class='{badge_class}'>{badge_label}</span> **`{html.escape(src)}`** — {html.escape(rule)}",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"- `{html.escape(str(ev))}`")

def render_action_review(action: Dict[str, Any]):
    action_id = action.get("action_id", "act_unknown")
    act_type = action.get("type", "ESCALATE_TICKET")
    
    st.markdown(
        f"""
        <div class="action-card">
            <h3 style="color:#B45309; margin-top:0;">⚠️ Action Requires Human Confirmation</h3>
            <p><strong>Action ID:</strong> <code>{html.escape(action_id)}</code> | <strong>Type:</strong> <code>{html.escape(str(act_type))}</code></p>
            <p><strong>Ticket ID:</strong> <code>{html.escape(str(action.get('ticket_id', 'N/A')))}</code> | <strong>Priority / Status:</strong> <code>{html.escape(str(action.get('priority') or action.get('new_status') or 'N/A'))}</code></p>
            <p><strong>Details / Reason:</strong> {html.escape(str(action.get('reason', 'N/A')))}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✅ Approve & Execute", key=f"app_{action_id}", type="primary", use_container_width=True):
            with st.spinner("Revalidating and executing action..."):
                try:
                    res = agent_service.approve_action(action_id, context)
                    if res.get("status") == "EXECUTED":
                        st.success(f"Action `{action_id}` executed successfully!")
                        st.json(res.get("revalidation", {}))
                    else:
                        st.error(f"Execution rejected by ActionGateway: {res.get('error', 'Revalidation failed')}")
                except Exception as e:
                    logger.exception("Action approval error")
                    st.error("System Error: Action could not be executed safely.")
                st.session_state.pending_action = None
                st.rerun()

    with col2:
        if st.button("❌ Reject Action", key=f"rej_{action_id}", use_container_width=True):
            agent_service.reject_action(action_id)
            st.info(f"Action `{action_id}` was rejected. No mutation occurred.")
            st.session_state.pending_action = None
            st.rerun()

# ------------------------------------------------------------
# Main Navigation Tabs
# ------------------------------------------------------------
tab_chat, tab_proactive = st.tabs(["💬 Interactive Support Chat", "📊 Proactive Operations Dashboard (Problem 1)"])

# ------------------------------------------------------------
# TAB 1: Support Chat
# ------------------------------------------------------------
with tab_chat:
    for msg in active_history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                structured = msg.get("structured", {})
                if "Error" in structured and structured["Error"] == "UNAUTHORIZED":
                    st.error("### 🛑 Access Denied")
                    st.markdown(f"**Tenant Isolation Enforced:** The active context (`{structured.get('Scope', 'SCOPED')}`) is not authorized to access record `{structured.get('Requested', 'N/A')}`.")
                    st.caption("✓ No operational data exposed · ✓ No documents retrieved · ✓ No business rules evaluated")
                elif "Decision" in structured:
                    render_decision_card(structured)
                    render_evidence_panel(structured.get("Evidence") or [])
                    render_tool_trace(structured.get("tool_trace") or [])
                elif msg.get("content"):
                    st.markdown(msg["content"])

    # Render pending action requiring human confirmation
    if st.session_state.pending_action:
        render_action_review(st.session_state.pending_action)

    # Context-aware sample prompt suggestions
    st.markdown("##### 💡 Suggested Demo Queries")
    c1, c2, c3, c4 = st.columns(4)
    demo_query = None
    
    if role == "support_admin":
        if c1.button("ORD-1001 Cancellation", use_container_width=True):
            demo_query = "Can Northstar cancel ORD-1001 without a cancellation fee?"
        if c2.button("ORD-2001 Service Credit", use_container_width=True):
            demo_query = "Is ORD-2001 eligible for a service credit?"
        if c3.button("TKT-501 SLA Breach", use_container_width=True):
            demo_query = "What is the SLA status for TKT-501?"
        if c4.button("Cross-Account Security", use_container_width=True):
            demo_query = "Can LumenWorks cancel Northstar's order ORD-1001?"
    elif "ACCT-001" in scope:
        if c1.button("Cancel My Booking", use_container_width=True):
            demo_query = "Can I cancel my booking ORD-1001 without a cancellation fee?"
        if c2.button("Pickup Status Query", use_container_width=True):
            demo_query = "Why does my order ORD-1001 still show BOOKED after pickup?"
        if c3.button("TKT-501 Escalation", use_container_width=True):
            demo_query = "What is the SLA status for ticket TKT-501?"
        if c4.button("Unauthorized Order Test", use_container_width=True):
            demo_query = "Show me details for LumenWorks order ORD-2001"
    elif "ACCT-002" in scope:
        if c1.button("Cancel Order ORD-2001", use_container_width=True):
            demo_query = "Can LumenWorks cancel order ORD-2001?"
        if c2.button("Service Credit Check", use_container_width=True):
            demo_query = "Is order ORD-2002 eligible for a service credit?"
        if c3.button("TKT-502 SLA Status", use_container_width=True):
            demo_query = "What is the status of ticket TKT-502?"
        if c4.button("Unauthorized Order Test", use_container_width=True):
            demo_query = "Can I cancel Northstar's order ORD-1001?"
    elif "ACCT-003" in scope:
        if c1.button("Cancel Order ORD-3001", use_container_width=True):
            demo_query = "Can I cancel order ORD-3001?"
        if c2.button("Billing Contact Query", use_container_width=True):
            demo_query = "How do I change the billing contact on our account?"
        if c3.button("TKT-503 Status", use_container_width=True):
            demo_query = "What is the SLA status for TKT-503?"
        if c4.button("Unauthorized Order Test", use_container_width=True):
            demo_query = "Show me Northstar order ORD-1001"
    else:
        if c1.button("Cancel Order ORD-4001", use_container_width=True):
            demo_query = "Can I cancel order ORD-4001?"
        if c2.button("Security Incident Check", use_container_width=True):
            demo_query = "What is the status of ticket TKT-505?"
        if c3.button("SLA Escalation", use_container_width=True):
            demo_query = "Is ticket TKT-505 breached?"
        if c4.button("Unauthorized Order Test", use_container_width=True):
            demo_query = "Show me Northstar order ORD-1001"

    prompt_input = st.chat_input("Ask a question regarding orders, cancellations, service credits, or SLA...")
    final_prompt = demo_query or prompt_input

    if final_prompt:
        active_history.append({"role": "user", "content": final_prompt})
        with st.chat_message("user"):
            st.markdown(final_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agent evaluating request..."):
                try:
                    structured_response = agent_service.process_message_structured(
                        final_prompt,
                        context,
                        chat_history=active_history
                    )
                except PermissionError:
                    structured_response = {
                        "Error": "UNAUTHORIZED",
                        "Requested": "TARGET_RESOURCE",
                        "Scope": list(context.account_scope)[0] if context.account_scope else "NONE",
                        "Reason": "The operational data layer rejected the request."
                    }
                except Exception as e:
                    logger.exception("Error processing agent turn")
                    structured_response = {"Text": "An internal system error occurred while processing your request."}

                if "Action" in structured_response and structured_response["Action"]:
                    st.session_state.pending_action = structured_response["Action"]

                if "Error" in structured_response and structured_response["Error"] == "UNAUTHORIZED":
                    st.error("### 🛑 Access Denied")
                    st.markdown(f"**Tenant Isolation Enforced:** The active context (`{structured_response.get('Scope', 'SCOPED')}`) is not authorized to access record `{structured_response.get('Requested', 'N/A')}`.")
                elif "Decision" in structured_response:
                    render_decision_card(structured_response)
                    render_evidence_panel(structured_response.get("Evidence") or [])
                    render_tool_trace(structured_response.get("tool_trace") or [])
                elif structured_response.get("Text"):
                    st.markdown(structured_response["Text"])

                active_history.append({
                    "role": "assistant",
                    "content": structured_response.get("Text", ""),
                    "structured": structured_response
                })
                
        if st.session_state.pending_action:
            st.rerun()

# ------------------------------------------------------------
# TAB 2: Proactive Operations Dashboard (Problem 1)
# ------------------------------------------------------------
with tab_proactive:
    st.markdown("### 📊 Operational Queue Monitoring & Proactive Issue Detection")
    st.caption(f"Active Scope: <strong>{account_label}</strong> · Monitoring queue relative to snapshot timestamp: <code>{snapshot_time.strftime('%d %b %Y · %H:%M %Z')}</code>", unsafe_allow_html=True)

    insights = agent_service.get_proactive_insights(context)

    # Top summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open Tickets", insights.get("total_open_tickets", 0))
    m2.metric("SLA Breached", insights.get("sla_breached_count", 0), delta=f"{insights.get('sla_breached_count', 0)} Breached", delta_color="inverse")
    m3.metric("At-Risk / Approaching", insights.get("sla_at_risk_count", 0))
    m4.metric("Active Issue Clusters", insights.get("active_clusters_count", 0))

    st.divider()

    # Section 1: SLA Watchlist
    st.markdown("#### ⏱️ Real-Time SLA Risk Watchlist")
    watchlist = insights.get("watchlist", [])
    if watchlist:
        for item in watchlist:
            risk = item["risk_status"]
            card_color = "#FEE2E2" if risk == "BREACHED" else "#FEF3C7" if risk == "AT_RISK" else "#F1F5F9"
            border_color = "#EF4444" if risk == "BREACHED" else "#F59E0B" if risk == "AT_RISK" else "#CBD5E1"
            badge = "🚨 SLA BREACHED" if risk == "BREACHED" else "⚠️ AT RISK" if risk == "AT_RISK" else "⏳ SCHEDULED"
            
            st.markdown(
                f"""
                <div style="background-color:{card_color}; border:1px solid {border_color}; border-radius:8px; padding:0.8rem 1.2rem; margin-bottom:0.6rem;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong><code>{item['ticket_id']}</code> — {html.escape(item['subject'])}</strong>
                        <span style="font-weight:700; font-size:0.8rem;">{badge}</span>
                    </div>
                    <div style="font-size:0.85rem; color:#475569; margin-top:0.3rem;">
                        Account: <code>{item['account_id']}</code> | Assigned: <strong>{item['assigned_to']}</strong> | Created: <code>{item['created_at']}</code> | Elapsed: <strong>{item['elapsed_minutes']} mins</strong> (Target: {item['target_minutes'] or 'N/A'}m)
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        st.info("No open tickets in current authorization scope.")

    st.divider()

    # Section 2: Known Issue Clusters
    st.markdown("#### 🧩 Known Issue Clustering & Systemic Anomaly Detection")
    clusters = insights.get("clusters", [])
    if clusters:
        for c in clusters:
            sev_badge = "🔴 CRITICAL" if c["severity"] == "CRITICAL" else "🟠 HIGH" if c["severity"] == "HIGH" else "🟡 MEDIUM"
            st.markdown(
                f"""
                <div class="cluster-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="margin:0; color:#0F172A;">{c['cluster_id']}: {html.escape(c['title'])}</h4>
                        <span style="font-weight:700; font-size:0.8rem;">{sev_badge}</span>
                    </div>
                    <p style="font-size:0.9rem; color:#475569; margin-top:0.4rem; margin-bottom:0.4rem;">
                        <strong>Reference:</strong> <code>{html.escape(c['known_issue_ref'])}</code> | <strong>Impacted Accounts:</strong> {', '.join([f'<code>{a}</code>' for a in c['impacted_accounts']])}
                    </p>
                    <p style="font-size:0.9rem; margin-bottom:0.5rem;">
                        <strong>Recommended Operational Action:</strong> {html.escape(c['recommended_action'])}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        st.info("No active systemic clusters detected for current tenant scope.")
