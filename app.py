import pathlib
import sys
import logging
import streamlit as st
from datetime import datetime

logger = logging.getLogger(__name__)

# Add src to sys.path so internal imports (e.g. from phase4) resolve correctly
sys.path.append(str(pathlib.Path(__file__).resolve().parent / "src"))

# Import backend orchestrator and models
from src.phase4 import SecurityContext, DocumentStore, OperationalDataStore, ActionGateway, IST
from src.phase5 import AgentOrchestrator

# --- INIT STATE ---
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pending_action' not in st.session_state:
    st.session_state.pending_action = None

DATA_PATH = pathlib.Path(__file__).resolve().parent / "ParcelPilot_Assessment_Data.xlsx"

@st.cache_resource
def get_data_store():
    return OperationalDataStore(DATA_PATH)

@st.cache_resource
def get_document_store():
    return DocumentStore()

if "gateway" not in st.session_state:
    st.session_state.gateway = ActionGateway(get_data_store(), get_document_store(), None)

# We do NOT cache the stateful components across the global server. Create/retrieve per user session.
def get_backend():
    data = get_data_store()
    docs = get_document_store()
    gateway = st.session_state.gateway
    agent = AgentOrchestrator(data, docs, gateway)
    gateway.rule_engine = agent.p4_engine 
    return agent, gateway

# --- SIDEBAR: CONTEXT ---
st.sidebar.title("Session Context")
st.sidebar.markdown("**Assessment Snapshot (fixed): 16 Aug 2026 11:00 IST**")
snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))

role = st.sidebar.selectbox("Role", ["customer", "support_agent", "support_admin"], index=1)

if role == "customer" or role == "support_agent":
    account = st.sidebar.selectbox("Account Scope", ["ACCT-001 (Northstar)", "ACCT-002 (LumenWorks)"], index=0)
    scope = frozenset([account.split(" ")[0]])
else:
    st.sidebar.markdown("**Scope: ALL**")
    scope = frozenset(["ALL"])

context = SecurityContext(role, scope, snapshot)

st.sidebar.divider()
st.sidebar.markdown("**Security Model enforced on all queries.**")
st.sidebar.markdown("""
**Authorization:**
✓ Data access scoped
✓ Document access scoped
✓ Snapshot locked
✓ Actions require confirmation
""")
st.sidebar.caption("The UI provides a mocked security context for assessment purposes. Production identity and authorization would be supplied by an identity provider/session token.")

agent, gateway = get_backend()

# --- MAIN UI ---
st.title("ParcelPilot Support Agent")

def render_structured_decision(data):
    if "Error" in data:
        st.error("🔐 **ACCESS DENIED**")
        st.markdown(f"**Requested resource:** {data.get('Requested', 'UNKNOWN')}")
        st.markdown(f"**Current account scope:** {data.get('Scope', 'NONE')}")
        st.markdown("**Result:** UNAUTHORIZED")
        st.markdown(f"**Why?**\n\n{data.get('Reason')}")
        return
        
    if "Text" in data and len(data) == 1:
        st.markdown(data["Text"])
        return

    # Verified Context
    if "Context" in data:
        ctx = data["Context"]
        st.info(f"**VERIFIED CONTEXT**\n\n**Account:** {ctx.get('Scope')}\n\n**Entity:** {ctx.get('Entity')}\n\n**Snapshot:** {ctx.get('Snapshot')}")

    # Trace
    if "Trace" in data:
        trace_str = "\n".join([f"✓ {t}" for t in data["Trace"]])
        st.markdown(f"**VERIFICATION TRACE**\n\n{trace_str}")
        
    # SLA Details
    if "SLA_Details" in data:
        sla = data["SLA_Details"]
        st.markdown(f"**SLA EVALUATION**\n\n**Ticket:** {sla.get('Ticket')} | **Priority:** {sla.get('Priority')}\n\n**Target:** {sla.get('Target')} | **Actual Response:** {sla.get('Actual_Response')}")
        
    # Decision
    if "Decision" in data:
        decision_str = data.get('Decision', 'UNKNOWN')
        st.success(f"**DECISION: {decision_str}**\n\n{data.get('Reason', '')}")
        
    # Evidence
    if data.get('Evidence'):
        evs = data['Evidence']
        ev_str = "\n".join([f"✓ {e}" for e in evs])
        st.markdown(f"**EVIDENCE USED**\n\n{ev_str}")
            
    # Limitations
    if data.get('Limitations'):
        lims = data['Limitations']
        lim_str = "\n".join([f"• {l}" for l in lims])
        st.warning(f"**LIMITATIONS & UNCERTAINTY**\n\n{lim_str}")

# Render Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "decision_data" in msg:
            render_structured_decision(msg["decision_data"])

# Pending Action Panel
if st.session_state.pending_action:
    action_data = st.session_state.pending_action
    action_id = action_data["action_id"]
    ctx_role = action_data["role"]
    ctx_scope = action_data["scope"]
    
    # Use get_pending_action to retrieve payload
    payload = gateway.get_pending_action(action_id)
    if payload:
        payload_data = payload["payload"]
        ticket_id = payload_data.get('ticket_id', 'UNKNOWN')
        sla_state = action_data.get('decision', 'UNKNOWN')
        reason = payload_data.get('reason', 'UNKNOWN')
        
        st.error(f"🚨 **ACTION REQUIRES APPROVAL**\n\n"
                 f"**Ticket:** {ticket_id}\n\n"
                 f"**SLA Evaluation:** {sla_state}\n\n"
                 f"**Escalation:** REQUIRED ({reason})\n\n"
                 f"**Context:** Role: {ctx_role} | Scope: {ctx_scope}")
                 
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reject"):
                st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} REJECTED by human."})
                gateway.reject(action_id)
                st.session_state.pending_action = None
                st.rerun()
        with col2:
            if st.button("Approve Escalation"):
                res = gateway.approve(action_id, context)
                if "Action executed successfully" in res:
                    st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} EXECUTED successfully.\n\n✓ REVALIDATING\n✓ AUTHORIZED\n✓ BUSINESS RULE STILL VALID"})
                elif "Action already executed" in res:
                    st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} ALREADY EXECUTED. No duplicate action was created."})
                elif "Unauthorized" in res:
                    st.session_state.messages.append({"role": "assistant", "content": f"Execution Failed: UNAUTHORIZED."})
                elif "Revalidation failed" in res:
                    st.session_state.messages.append({"role": "assistant", "content": f"Execution Failed: {res}"})
                else:
                    st.session_state.messages.append({"role": "assistant", "content": f"Execution Failed: {res}"})
                    
                st.session_state.pending_action = None
                st.rerun()

# User Input
if prompt := st.chat_input("Ask a support question..."):
    message_entry = {"role": "user", "content": prompt}
    st.session_state.messages.append(message_entry)
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.chat_message("assistant"):
        with st.spinner("Evaluating deterministic rules..."):
            try:
                structured_data = agent.process_message_structured(prompt, context)
            except PermissionError:
                structured_data = {"Text": "UNAUTHORIZED: You do not have permission to access this record."}
            except Exception:
                logger.exception("Agent processing failed")
                structured_data = {"Text": "SYSTEM ERROR: The request could not be completed safely."}
            
            # Extract Action ID if pending
            action = structured_data.get("Action")
            if action and action.get("status") == "PREPARED":
                st.session_state.pending_action = {
                    "action_id": action["action_id"],
                    "decision": structured_data.get("Decision", "UNKNOWN"),
                    "role": context.role,
                    "scope": ", ".join(list(context.account_scope))
                }
            
            if structured_data.get("Text"):
                st.markdown(structured_data["Text"])
                assistant_message = {"role": "assistant", "content": structured_data["Text"]}
            else:
                render_structured_decision(structured_data)
                assistant_message = {"role": "assistant", "content": ""}
                
            if "Decision" in structured_data:
                assistant_message["decision_data"] = structured_data
                
            st.session_state.messages.append(assistant_message)
            st.rerun()
