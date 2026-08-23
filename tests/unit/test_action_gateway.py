import unittest
from datetime import datetime
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.domain.sla_engine import SLAEngine
from src.actions.action_gateway import ActionGateway, ActionState

class TestActionGateway(unittest.TestCase):
    def setUp(self):
        self.snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
        self.data_store = OperationalDataStore()
        self.doc_store = DocumentStore()
        self.engine = SLAEngine()
        self.gateway = ActionGateway(self.data_store, self.doc_store, self.engine)
        self.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), self.snapshot)
        self.lw_ctx = SecurityContext("customer", frozenset(["ACCT-002"]), self.snapshot)

    def test_prepare_and_revalidate_flow(self):
        payload = {
            "ticket_id": "TKT-501",
            "account_id": "ACCT-001",
            "priority": "P1",
            "reason": "Test escalation",
            "action": "ESCALATE_TICKET"
        }
        action_id = self.gateway.prepare(self.admin_ctx, payload)
        self.assertEqual(action_id, "act_1")
        
        # Test unauthorized approval fails
        fail_res = self.gateway.approve(action_id, self.lw_ctx)
        self.assertEqual(fail_res["status"], "FAILED")
        self.assertEqual(fail_res["revalidation"]["authorization"], "FAILED")
        
        # Test authorized approval succeeds
        succ_res = self.gateway.approve(action_id, self.admin_ctx)
        self.assertEqual(succ_res["status"], "EXECUTED")
        self.assertEqual(succ_res["revalidation"]["authorization"], "PASSED")
        self.assertEqual(succ_res["revalidation"]["rule_state"], "PASSED")

    def test_ticket_update_action(self):
        payload = {
            "ticket_id": "TKT-502",
            "account_id": "ACCT-002",
            "new_status": "escalated",
            "comment": "Updating status for testing",
            "action": "UPDATE_TICKET"
        }
        action_id = self.gateway.prepare(self.lw_ctx, payload)
        res = self.gateway.approve(action_id, self.lw_ctx)
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["execution"]["action_type"], "UPDATE_TICKET")

    def test_followup_task_action(self):
        payload = {
            "ticket_id": "TKT-504",
            "account_id": "ACCT-001",
            "task_type": "CARRIER_DISPUTE",
            "description": "Investigate pickup confirmation lag with SwiftShip",
            "assigned_team": "Carrier Operations",
            "action": "CREATE_TASK"
        }
        action_id = self.gateway.prepare(self.admin_ctx, payload)
        res = self.gateway.approve(action_id, self.admin_ctx)
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["execution"]["action_type"], "CREATE_TASK")

if __name__ == '__main__':
    unittest.main()
