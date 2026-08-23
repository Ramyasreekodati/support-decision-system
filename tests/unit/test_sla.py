import unittest
from datetime import datetime
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.domain.sla_engine import SLAEngine

class TestSLAEngine(unittest.TestCase):
    def setUp(self):
        self.snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
        self.data_store = OperationalDataStore()
        self.doc_store = DocumentStore()
        self.engine = SLAEngine()
        self.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), self.snapshot)

    def test_northstar_p1_deadline_elapsed(self):
        ticket = self.data_store.query_tickets(self.admin_ctx, "TKT-501")
        docs = self.doc_store.retrieve(self.admin_ctx)
        res = self.engine.evaluate_sla(ticket, docs, self.snapshot)
        self.assertEqual(res.target_minutes, 15)
        self.assertEqual(res.state, "DEADLINE_ELAPSED")
        self.assertEqual(res.escalation_requirement, "REQUIRED")

if __name__ == '__main__':
    unittest.main()
