import streamlit as st
from datetime import datetime
import traceback

# Import backend orchestrator and models
from src.phase4 import SecurityContext, DocumentStore, OperationalDataStore, ActionGateway, IST
from src.phase5 import AgentOrchestrator

# --- INIT STATE ---
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pending_action' not in st.session_state:
    st.session_state.pending_action = None

@st.cache_resource
def get_backend():
    snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
    data = OperationalDataStore("g:/ParcelPilot/ParcelPilot_Assessment_Data.xlsx")
    docs = DocumentStore()
    gateway = ActionGateway(data, docs, None) # It gets patched in agent orchestrator if needed, but phase5 handles it
    agent = AgentOrchestrator(data, docs, gateway)
    
    # We must patch the gateway inside agent orchestrator to use the proper engine
    gateway.rule_engine = agent.p4_engine 
    
    return agent, gateway, snapshot

agent, gateway, snapshot = get_backend()

# --- SIDEBAR: CONTEXT ---
st.sidebar.title("Session Context")
st.sidebar.markdown(f"**Snapshot:** {snapshot.strftime('%d %b %Y %H:%M %Z')}")

role = st.sidebar.selectbox("Role", ["support_agent", "customer", "support_admin"], index=0)
account = st.sidebar.selectbox("Account Scope", ["ACCT-001 (Northstar)", "ACCT-002 (LumenWorks)", "ALL"], index=0)

scope = frozenset([account.split(" ")[0]]) if account != "ALL" else frozenset(["ALL"])
context = SecurityContext(role, scope, snapshot)

st.sidebar.divider()
st.sidebar.markdown("**Security Model enforced on all queries.**")

# --- MAIN UI ---
st.title("ParcelPilot Support Agent")

# Render Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # If there's structured data to render
        if "decision_data" in msg:
            data = msg["decision_data"]
            
            # Decision Panel
            st.info(f"**Decision:** {data.get('Decision', 'UNKNOWN')}\n\n**Reason:** {data.get('Reason', '')}")
            
            # Evidence Panel
            if data.get('Evidence'):
                st.success(f"**Evidence:**\n{data.get('Evidence')}")
                
            # Limitations Panel (Uncertainty)
            if data.get('Limitations'):
                st.warning(f"**Limitations / Uncertainty:**\n{data.get('Limitations')}")

# Pending Action Panel
if st.session_state.pending_action:
    action_id = st.session_state.pending_action
    st.error(f"🚨 **ACTION REQUIRES APPROVAL**\n\nAction ID: {action_id}")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Reject"):
            st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} REJECTED by human."})
            st.session_state.pending_action = None
            st.rerun()
    with col2:
        if st.button("Approve Escalation"):
            res = gateway.confirm(action_id, context)
            if "executed successfully" in res or "idempotent" in res:
                st.session_state.messages.append({"role": "assistant", "content": f"Action {action_id} APPROVED. Result: {res}"})
            else:
                st.session_state.messages.append({"role": "assistant", "content": f"Execution Failed: {res}"})
            st.session_state.pending_action = None
            st.rerun()

# User Input
if prompt := st.chat_input("Ask a support question..."):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Process
    with st.chat_message("assistant"):
        with st.spinner("Evaluating deterministic rules..."):
            reply = agent.process_message(prompt, context)
            
            # Very basic parser for the rigid LLM explanation string to map to UI components
            # "Decision: ...\nReason: ...\nEvidence: ...\nLimitations: ...\nAction: ..."
            structured_data = {}
            lines = reply.split('\n')
            current_key = "Text"
            structured_data[current_key] = ""
            
            for line in lines:
                if line.startswith("Decision:"): current_key = "Decision"; structured_data[current_key] = line.replace("Decision:", "").strip()
                elif line.startswith("Reason:"): current_key = "Reason"; structured_data[current_key] = line.replace("Reason:", "").strip()
                elif line.startswith("Evidence:"): current_key = "Evidence"; structured_data[current_key] = line.replace("Evidence:", "").strip()
                elif line.startswith("Limitations:"): current_key = "Limitations"; structured_data[current_key] = line.replace("Limitations:", "").strip()
                elif line.startswith("Action:"): current_key = "Action"; structured_data[current_key] = line.replace("Action:", "").strip()
                elif line.startswith("UNAUTHORIZED:") or line.startswith("SYSTEM ERROR:"):
                    structured_data["Text"] = line
                else:
                    if current_key in structured_data:
                        structured_data[current_key] += " " + line.strip()
            
            # Extract Action ID if pending
            if "Action" in structured_data and "Action ID:" in structured_data["Action"]:
                action_id = structured_data["Action"].split("Action ID:")[1].strip()
                st.session_state.pending_action = action_id
            
            # Display
            if structured_data.get("Text"):
                st.markdown(structured_data["Text"])
            if "Decision" in structured_data:
                st.info(f"**Decision:** {structured_data.get('Decision')}\n\n**Reason:** {structured_data.get('Reason')}")
            if structured_data.get('Evidence'):
                st.success(f"**Evidence:**\n{structured_data.get('Evidence')}")
            if structured_data.get('Limitations'):
                st.warning(f"**Limitations / Uncertainty:**\n{structured_data.get('Limitations')}")
                
            # Store in history
            st.session_state.messages.append({
                "role": "assistant", 
                "content": structured_data.get("Text", ""),
                "decision_data": structured_data
            })
            
            st.rerun()
