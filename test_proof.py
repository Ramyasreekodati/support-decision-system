import sys
import io
import json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.security.authorization import SecurityContext, IST
from src.agent.agent_service import get_agent_service

service = get_agent_service()
snap = service.get_snapshot_time()

print("================================================================================")
print("             PARCELPILOT VERIFICATION & PROOF TEST SUITE")
print("================================================================================")

print("\n--- 1. TEST: ACCT-001 (Northstar Enterprise) asking vague 'cancel my book' ---")
ctx_northstar = SecurityContext('customer', frozenset(['ACCT-001']), snap)
res1 = service.process_message_structured('cancel my book', ctx_northstar)
print(f"Target Order Evaluated : {res1.get('Context', {}).get('Entity')}")
print(f"Decision               : {res1.get('Decision')}")
print(f"Explanation            : {res1.get('Reason')}")
print(f"Evidence Source        : {res1.get('Evidence')[1].get('source')} ({res1.get('Evidence')[1].get('authority')})")
assert res1.get('Decision') == 'CANCELLATION_ALLOWED'
assert '0' in res1.get('Reason')

print("\n--- 2. TEST: ACCT-002 (LumenWorks Growth) asking vague 'cancel my book' ---")
ctx_lumen = SecurityContext('customer', frozenset(['ACCT-002']), snap)
res2 = service.process_message_structured('cancel my book', ctx_lumen)
print(f"Target Order Evaluated : {res2.get('Context', {}).get('Entity')}")
print(f"Decision               : {res2.get('Decision')}")
print(f"Explanation            : {res2.get('Reason')}")
print(f"Evidence Source        : {res2.get('Evidence')[0].get('source')} ({res2.get('Evidence')[0].get('authority')})")
assert res2.get('Decision') == 'CANCELLATION_ALLOWED'
assert '250' in res2.get('Reason')

print("\n--- 3. TEST: ACCT-003 (Beacon Retail Standard) asking vague 'cancel my book' ---")
ctx_beacon = SecurityContext('customer', frozenset(['ACCT-003']), snap)
res3 = service.process_message_structured('cancel my book', ctx_beacon)
print(f"Target Order Evaluated : {res3.get('Context', {}).get('Entity')}")
print(f"Decision               : {res3.get('Decision')}")
print(f"Explanation            : {res3.get('Reason')}")
assert res3.get('Decision') == 'CANCELLATION_ALLOWED'
assert '0' in res3.get('Reason')

print("\n--- 4. TEST: ACCT-004 (Axis Labs) asking vague 'cancel my book' (DELIVERED Order) ---")
ctx_axis = SecurityContext('customer', frozenset(['ACCT-004']), snap)
res4 = service.process_message_structured('cancel my book', ctx_axis)
print(f"Target Order Evaluated : {res4.get('Context', {}).get('Entity')}")
print(f"Decision               : {res4.get('Decision')}")
print(f"Explanation            : {res4.get('Reason')}")
assert res4.get('Decision') == 'CANCELLATION_NOT_ALLOWED'

print("\n--- 5. TEST: Cross-Account Security (ACCT-002 trying to cancel ACCT-001's ORD-1001) ---")
res5 = service.process_message_structured('Can I cancel ORD-1001?', ctx_lumen)
print(f"Security Error         : {res5.get('Error')}")
print(f"Scope Blocked          : {res5.get('Scope')}")
print(f"Isolation Proof        : {res5.get('Reason')}")
assert res5.get('Error') == 'UNAUTHORIZED'

print("\n--- 6. TEST: Uncertainty & Missing Fact Handling (ORD-2001 Service Credit) ---")
res6 = service.process_message_structured('Is ORD-2001 eligible for a service credit?', ctx_lumen)
print(f"Decision               : {res6.get('Decision')}")
print(f"Limitations Surfaced   : {res6.get('Limitations')}")
assert res6.get('Decision') == 'UNKNOWN'

print("\n--- 7. TEST: Human Action Gateway Lifecycle (TKT-501 SLA Escalation) ---")
ctx_admin = SecurityContext('support_admin', frozenset(['ALL']), snap)
res7 = service.process_message_structured('What is the SLA status for TKT-501?', ctx_admin)
print(f"Decision               : {res7.get('Decision')}")
act = res7.get('Action')
print(f"Staged Proposal        : ID={act['action_id']}, Status={act['status']}, Type={act['type']}, Priority={act['priority']}")
# Approve action
app_res = service.approve_action(act['action_id'], ctx_admin)
print(f"Approval Result        : {app_res.get('status')}")
print(f"4-Point Revalidation   : {json.dumps(app_res.get('revalidation'))}")
assert app_res.get('status') == 'EXECUTED'
assert all(v == 'PASSED' for v in app_res.get('revalidation').values())

print("\n--- 8. TEST: Proactive Operations Analytics (Problem 1) ---")
insights = service.get_proactive_insights(ctx_admin)
print(f"Total Open Tickets     : {insights.get('total_open_tickets')}")
print(f"SLA Breached Count     : {insights.get('sla_breached_count')}")
print(f"Active Issue Clusters  : {[c['cluster_id'] + ': ' + c['title'] for c in insights.get('clusters')]}")
assert insights.get('sla_breached_count') >= 1
assert len(insights.get('clusters')) >= 3

print("\n================================================================================")
print("             ALL 8 RELIABILITY & VERIFICATION TESTS PASSED (100%)")
print("================================================================================")
