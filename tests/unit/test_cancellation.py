import unittest
from datetime import datetime
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.domain.cancellation_engine import CancellationEngine

class TestCancellationEngine(unittest.TestCase):
    def setUp(self):
        self.snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
        self.data_store = OperationalDataStore()
        self.doc_store = DocumentStore()
        self.engine = CancellationEngine()
        self.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), self.snapshot)

    def test_northstar_cancellation_override(self):
        order = self.data_store.query_orders(self.admin_ctx, "ORD-1001")
        docs = self.doc_store.retrieve(self.admin_ctx)
        res = self.engine.evaluate_cancellation(order, docs, self.snapshot)
        self.assertEqual(res.decision, "CANCELLATION_ALLOWED")
        self.assertEqual(res.amount, 0)
        self.assertEqual(res.applicable_rule, "northstar_cancellation_override")

    def test_lumenworks_general_sop_fee(self):
        order = self.data_store.query_orders(self.admin_ctx, "ORD-2001")
        docs = self.doc_store.retrieve(self.admin_ctx)
        res = self.engine.evaluate_cancellation(order, docs, self.snapshot)
        self.assertEqual(res.decision, "CANCELLATION_ALLOWED")
        self.assertEqual(res.amount, 250)
        self.assertEqual(res.applicable_rule, "general_cancellation_sop")

    def test_early_cancellation_fee_zero(self):
        early_snapshot = IST.localize(datetime(2026, 8, 16, 9, 15))
        order = self.data_store.query_orders(self.admin_ctx, "ORD-2001")
        docs = self.doc_store.retrieve(self.admin_ctx)
        res = self.engine.evaluate_cancellation(order, docs, early_snapshot)
        self.assertEqual(res.decision, "CANCELLATION_ALLOWED")
        self.assertEqual(res.amount, 0)

if __name__ == '__main__':
    unittest.main()
