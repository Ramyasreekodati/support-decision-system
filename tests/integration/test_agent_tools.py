import unittest
from datetime import datetime
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.actions.action_gateway import ActionGateway
from src.agent.agent_service import AgentService

class TestAgentToolsIntegration(unittest.TestCase):
    def setUp(self):
        self.snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
        self.data_store = OperationalDataStore()
        self.doc_store = DocumentStore()
        self.gateway = ActionGateway(self.data_store, self.doc_store)
        self.service = AgentService(self.data_store, self.doc_store, self.gateway)
        self.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), self.snapshot)
        self.lw_ctx = SecurityContext("customer", frozenset(["ACCT-002"]), self.snapshot)

    def test_multi_tool_cancellation_pipeline(self):
        res = self.service.process_message_structured("Can I cancel ORD-1001?", self.admin_ctx)
        tools = [step["tool"] for step in res["tool_trace"]]
        self.assertIn("get_order", tools)
        self.assertIn("search_documents", tools)
        self.assertIn("evaluate_cancellation", tools)
        self.assertEqual(res["Decision"], "CANCELLATION_ALLOWED")

    def test_security_boundary_blocks_unauthorized_access(self):
        res = self.service.process_message_structured("Show me Northstar's ORD-1001", self.lw_ctx)
        self.assertEqual(res.get("Error"), "UNAUTHORIZED")

if __name__ == '__main__':
    unittest.main()
