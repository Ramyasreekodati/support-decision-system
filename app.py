import pathlib
import streamlit as st
from datetime import datetime

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
st.sidebar.caption("The UI provides a mocked security context for assessment purposes. Production identity and authorization would be supplied by an identity provider/session token.")

agent, gateway = get_backend()

# --- MAIN UI ---
st.title("ParcelPilot Support Agent")

def render_structured_decision(data):
    if "Text" in data and len(data) == 1:
        st.markdown(data["Text"])
        return
        
    if "Decision" in data:
        st.info(f"**Decision:** {data.get('Decision', 'UNKNOWN')}\n\n**Reason:** {data.get('Reason', '')}")
        
    if data.get('Evidence'):
        evs = data['Evidence'].split(', ')
        ev_str = "\n".join([f"• {e}" for e in evs])
        st.success(f"**Evidence**\n────────\n{ev_str}")
            
    if data.get('Limitations'):
        lims = data['Limitations'].split('. ')
        lim_str = "\n".join([f"⚠ {l.strip()}" for l in lims if l.strip()])
        st.warning(f"**Limitations**\n───────────\n{lim_str}")

# Render Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "decision_data" in msg:
            render_structured_decision(msg["decision_data"])

# Pending Action Panel
if st.session_state.pending_action:
    action_data = st.session_state.pending_action
    action_id = action_data["id"]
    ctx_role = action_data["role"]
    ctx_scope = action_data["scope"]
    
    # Retrieve action payload from gateway to show details
    if action_id in gateway.pending_actions:
        payload = gateway.pending_actions[action_id]["payload"]
        st.error(f"🚨 **P1 ESCALATION REQUIRED**\n\n"
                 f"**Ticket:** {payload.get('ticket_id')}\n\n"
                 f"**SLA:** BREACHED\n\n"
                 f"**Reason:** {payload.get('reason')}\n\n"
                 f"**Prepared For:** Role: {ctx_role} | Scope: {ctx_scope}")
                 
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reject"):
                st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} REJECTED by human."})
                gateway.reject(action_id)
                st.session_state.pending_action = None
                st.rerun()
        with col2:
            if st.button("Approve Escalation"):
                res = gateway.confirm(action_id, context)
                if "Action executed successfully" in res:
                    st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} EXECUTED successfully."})
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
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.chat_message("assistant"):
        with st.spinner("Evaluating deterministic rules..."):
            try:
                structured_data = agent.process_message_structured(prompt, context)
            except PermissionError:
                structured_data = {"Text": "UNAUTHORIZED: You do not have permission to access this record."}
            except Exception as e:
                structured_data = {"Text": "System error: The request could not be completed safely."}
            
            # Extract Action ID if pending
            if "Action" in structured_data and "Action ID:" in structured_data["Action"]:
                action_id = structured_data["Action"].split("Action ID:")[1].strip()
                st.session_state.pending_action = {
                    "id": action_id,
                    "role": context.role,
                    "scope": ", ".join(list(context.account_scope))
                }
            
            if structured_data.get("Text"):
                st.markdown(structured_data["Text"])
            else:
                render_structured_decision(structured_data)
                
            st.session_state.messages.append({
                "role": "assistant", 
                "content": structured_data.get("Text", ""),
                "decision_data": structured_data if "Decision" in structured_data else None
            })
            st.rerun()
