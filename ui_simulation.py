import sys
from src.phase4 import SecurityContext, IST
from datetime import datetime
from src.phase5 import AgentOrchestrator
from src.phase4 import DocumentStore, OperationalDataStore, ActionGateway

print("\n=== MANUAL UI TEST SIMULATION ===")

# Streamlit Backend Emulation
snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
data = OperationalDataStore("g:/ParcelPilot/ParcelPilot_Assessment_Data.xlsx")
docs = DocumentStore()
gateway = ActionGateway(data, docs, None)
agent = AgentOrchestrator(data, docs, gateway)
gateway.rule_engine = agent.p4_engine 

admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), snapshot)
lw_ctx = SecurityContext("customer", frozenset(["ACCT-002"]), snapshot)

def simulate_ui_chat(prompt, context):
    print(f"\n[User]: {prompt}")
    reply = agent.process_message(prompt, context)
    print(f"[Agent]:\n{reply}")
    
    # Action simulation
    if "Action ID:" in reply:
        action_id = reply.split("Action ID:")[1].strip()
        print(f"\n[UI rendered Approve/Reject buttons for Action: {action_id}]")
        return action_id
    return None

# A. Northstar cancellation
print("\n--- SCENARIO A: Normal ---")
simulate_ui_chat("Can I cancel ORD-1001?", admin_ctx)

# B. Unknown service-credit case
print("\n--- SCENARIO B: Unknown ---")
simulate_ui_chat("Credit for ORD-2001?", admin_ctx)

# C. P1 verified breach
print("\n--- SCENARIO C: P1 Verified Breach ---")
# Mock ticket to be verified breach for this specific test
original = data.query_tickets
def mock_query_tkt(ctx, tid):
    return {'ticket_id': 'TKT-999', 'account_id': 'ACCT-001', 'created_at': '2026-08-16 09:00', 'first_response_at': '2026-08-16 10:00', 'priority': 'P1'}
data.query_tickets = mock_query_tkt

action_id = simulate_ui_chat("SLA for TKT-999", admin_ctx)
print("\n[User clicks Reject]")
print(f"Action State before Reject execution: {len(gateway.executed_actions)} executed.")
gateway.reject(action_id)
print(f"Action State after Reject execution: {len(gateway.executed_actions)} executed.")

action_id_2 = simulate_ui_chat("SLA for TKT-999", admin_ctx)
print("\n[User clicks Approve]")
gateway.confirm(action_id_2, admin_ctx)
gateway.revalidate_and_execute(action_id_2, admin_ctx)
print(f"Action State after Approve execution: {len(gateway.executed_actions)} executed.")
data.query_tickets = original

# D. Cross-account access
print("\n--- SCENARIO D: Security ---")
simulate_ui_chat("Cancel Northstar's ORD-1001", lw_ctx)

print("\n=== UI SIMULATION COMPLETE ===")
