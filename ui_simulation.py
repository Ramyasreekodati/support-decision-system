import pathlib
import sys
from src.phase4 import SecurityContext, IST
from datetime import datetime
from src.phase5 import AgentOrchestrator
from src.phase4 import DocumentStore, OperationalDataStore, ActionGateway

print("\n=== MANUAL UI TEST SIMULATION ===")

# Streamlit Backend Emulation
data = OperationalDataStore(pathlib.Path(__file__).resolve().parent / "ParcelPilot_Assessment_Data.xlsx")
snapshot = data.get_snapshot_time()  # dynamic — same source as app.py
docs = DocumentStore()
gateway = ActionGateway(data, docs, None)
agent = AgentOrchestrator(data, docs, gateway)
gateway.rule_engine = agent.p4_engine 

admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), snapshot)
lw_ctx = SecurityContext("customer", frozenset(["ACCT-002"]), snapshot)

def simulate_ui_chat(prompt, context):
    print(f"\n[User]: {prompt}")
    try:
        structured = agent.process_message_structured(prompt, context)
    except PermissionError:
        structured = {"Text": "UNAUTHORIZED: You do not have permission to access this record."}
        
    print("[Agent]")
    
    # Assert required fields
    if "Decision" in structured or "Error" in structured:
        assert "tool_trace" in structured, "FAIL: tool_trace missing from structured response"
        print(f"  tool_trace: {[s['tool'] for s in structured['tool_trace']]}")
        
        if "Evidence" in structured:
            for e in structured["Evidence"]:
                if isinstance(e, dict):
                    assert "authority" in e, f"FAIL: authority missing from evidence item {e}"
            print(f"  evidence: {[e.get('source','?') for e in structured['Evidence']]}")
    
    print(f"  Decision: {structured.get('Decision', structured.get('Error', structured.get('Text', '?')))}")
    
    action = structured.get("Action")
    if action and action.get("status") == "PREPARED":
        action_id = action["action_id"]
        print(f"\n[UI rendered Approve/Reject buttons for Action: {action_id}]")
        return action_id
    return None

# A. Northstar cancellation
print("\n--- SCENARIO A: Normal Cancellation ---")
result_a = simulate_ui_chat("Can I cancel ORD-1001?", admin_ctx)
assert result_a is None  # cancellations don't create actions

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
print(f"Action State before Reject: {len(gateway.executed_actions)} executed.")
res_reject = gateway.reject(action_id)
assert res_reject["status"] == "REJECTED", f"Expected REJECTED, got {res_reject}"
print(f"Reject result: {res_reject['status']}")
print(f"Action State after Reject: {len(gateway.executed_actions)} executed.")

action_id_2 = simulate_ui_chat("SLA for TKT-999", admin_ctx)
print("\n[User clicks Approve]")
res = gateway.approve(action_id_2, admin_ctx)
assert res["status"] == "EXECUTED", f"Expected EXECUTED, got {res}"
assert res["revalidation"]["authorization"] == "PASSED"
assert res["revalidation"]["rule_state"] == "PASSED"
assert res["revalidation"]["payload_integrity"] == "PASSED"
print(f"Approve result: {res['status']}")
print(f"  Revalidation: {res['revalidation']}")
print(f"Action State after Approve: {len(gateway.executed_actions)} executed.")
data.query_tickets = original

# D. Cross-account access
print("\n--- SCENARIO D: Security ---")
simulate_ui_chat("Cancel Northstar's ORD-1001", lw_ctx)

print("\n=== ALL ASSERTIONS PASSED ===")
print("=== UI SIMULATION COMPLETE ===")

