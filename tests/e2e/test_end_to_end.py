import unittest
from datetime import datetime
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.actions.action_gateway import ActionGateway
from src.agent.agent_service import AgentService

class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
        self.data_store = OperationalDataStore()
        self.doc_store = DocumentStore()
        self.gateway = ActionGateway(self.data_store, self.doc_store)
        self.service = AgentService(self.data_store, self.doc_store, self.gateway)
        self.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), self.snapshot)

    def test_e2e_cancellation_flow(self):
        reply = self.service.process_message("Can Northstar cancel ORD-1001 without fee?", self.admin_ctx)
        self.assertIn("Decision: CANCELLATION_ALLOWED", reply)
        self.assertIn("05_Northstar_Logistics_Enterprise_Agreement.pdf", reply)

    def test_e2e_unknown_credit_flow(self):
        reply = self.service.process_message("Is ORD-2001 eligible for a credit?", self.admin_ctx)
        self.assertIn("Decision: UNKNOWN", reply)

    def test_e2e_human_gated_escalation(self):
        res = self.service.process_message_structured("SLA for TKT-501", self.admin_ctx)
        self.assertEqual(res["Decision"], "DEADLINE_ELAPSED")
        self.assertIsNotNone(res["Action"])
        action_id = res["Action"]["action_id"]
        
        # Approve and execute
        exec_res = self.gateway.approve(action_id, self.admin_ctx)
        self.assertEqual(exec_res["status"], "EXECUTED")
        self.assertEqual(exec_res["revalidation"]["authorization"], "PASSED")

if __name__ == '__main__':
    unittest.main()
