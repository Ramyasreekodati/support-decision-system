import unittest
from datetime import datetime
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.domain.service_credit_engine import ServiceCreditEngine

class TestServiceCreditEngine(unittest.TestCase):
    def setUp(self):
        self.snapshot = IST.localize(datetime(2026, 8, 16, 11, 0))
        self.data_store = OperationalDataStore()
        self.doc_store = DocumentStore()
        self.engine = ServiceCreditEngine()
        self.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), self.snapshot)

    def test_missing_actual_pickup_yields_unknown(self):
        order = self.data_store.query_orders(self.admin_ctx, "ORD-2001")
        docs = self.doc_store.retrieve(self.admin_ctx)
        res = self.engine.evaluate_service_credit(order, docs, self.snapshot)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertIn("pickup_actual_at", res.conditions_missing)

    def test_conflicting_fault_yields_unknown(self):
        order = self.data_store.query_orders(self.admin_ctx, "ORD-2001")
        order['carrier_fault_conflict'] = True
        docs = self.doc_store.retrieve(self.admin_ctx)
        res = self.engine.evaluate_service_credit(order, docs, self.snapshot)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertEqual(res.applicable_rule, "conflict_resolution_required")

if __name__ == '__main__':
    unittest.main()
