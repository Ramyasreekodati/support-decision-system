import unittest
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import pytz
import json

IST = pytz.timezone('Asia/Kolkata')

@dataclass(frozen=True)
class SecurityContext:
    role: str
    account_scope: frozenset
    snapshot_time: datetime

    def __post_init__(self):
        if self.snapshot_time.tzinfo is None:
            raise ValueError("snapshot_time must be timezone-aware (e.g., Asia/Kolkata)")

class RetrievalMode(Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"

DOCUMENT_METADATA_DEFS = {
    "doc_01": {"filename": "01_Support_Policy_v3_CURRENT.pdf", "status": "CURRENT", "customer_scope": frozenset(["General"])},
    "doc_02": {"filename": "02_Support_Policy_v2_DEPRECATED.pdf", "status": "DEPRECATED", "customer_scope": frozenset(["General"])},
    "doc_03": {"filename": "03_Cancellation_and_Service_Credit_SOP_v4.pdf", "status": "CURRENT", "customer_scope": frozenset(["General"])},
    "doc_04": {"filename": "04_Product_Operations_Guide_and_Known_Issues.pdf", "status": "CURRENT", "customer_scope": frozenset(["General"])},
    "doc_05": {"filename": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "status": "ACTIVE", "customer_scope": frozenset(["ACCT-001"])},
    "doc_06": {"filename": "06_LumenWorks_Service_Agreement.pdf", "status": "ACTIVE", "customer_scope": frozenset(["ACCT-002"])}
}

def is_authorized(context: SecurityContext, target_account_id: str) -> bool:
    if context.role == "support_admin":
        return True
    return target_account_id in context.account_scope

def is_doc_authorized(context: SecurityContext, doc_scope: frozenset) -> bool:
    if context.role == "support_admin":
        return True
    if "General" in doc_scope:
        return True
    return not doc_scope.isdisjoint(context.account_scope)

class DocumentStore:
    def retrieve(self, context: SecurityContext, mode: RetrievalMode, simulate_missing: List[str] = None) -> List[Dict[str, Any]]:
        results = []
        simulate_missing = simulate_missing or []
        for doc_id, meta in DOCUMENT_METADATA_DEFS.items():
            if meta["filename"] in simulate_missing:
                continue
            if not is_doc_authorized(context, meta["customer_scope"]):
                continue
            is_deprecated = meta["status"] == "DEPRECATED"
            if mode == RetrievalMode.CURRENT and is_deprecated:
                continue
            retrieved_meta = meta.copy()
            if mode == RetrievalMode.HISTORICAL and is_deprecated:
                retrieved_meta["historical_label"] = "[HISTORICAL - NOT CURRENT]"
            results.append({"id": doc_id, "metadata": retrieved_meta})
        return results

class OperationalDataStore:
    def __init__(self, excel_path: str):
        self.orders = pd.read_excel(excel_path, "orders")
        
    def query_orders(self, context: SecurityContext, order_id: str) -> Optional[Dict[str, Any]]:
        order_row = self.orders[self.orders["order_id"] == order_id]
        if order_row.empty:
            return None
        order_dict = order_row.iloc[0].to_dict()
        if not is_authorized(context, order_dict["account_id"]):
            raise PermissionError(f"Unauthorized account access for {context.role}")
        return order_dict

@dataclass
class DecisionResult:
    decision: str
    amount: Optional[int]
    applicable_rule: str
    evidence: List[Dict[str, str]]
    limitations: List[str]
    requires_confirmation: bool

class RuleEngine:
    def evaluate_cancellation(self, order_facts: dict, docs: List[dict], snapshot_time: datetime) -> DecisionResult:
        account_id = order_facts['account_id']
        status = order_facts['status']
        booked_at = pd.to_datetime(order_facts['booked_at']).tz_localize(IST)
        
        elapsed_mins = (snapshot_time - booked_at).total_seconds() / 60
        
        # Check available documents
        filenames = [d['metadata']['filename'] for d in docs]
        has_sop = "03_Cancellation_and_Service_Credit_SOP_v4.pdf" in filenames
        has_northstar_agreement = "05_Northstar_Logistics_Enterprise_Agreement.pdf" in filenames
        has_lumenworks_agreement = "06_LumenWorks_Service_Agreement.pdf" in filenames
        
        evidence = []
        if has_sop:
            evidence.append({"source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf", "rule": "General Cancellation SOP"})
            
        limitations = []
        if not has_sop:
            limitations.append("Missing General Cancellation SOP.")
            return DecisionResult("UNKNOWN", None, "none", evidence, limitations, False)

        # No silent fallback: if it's Northstar, we MUST have their agreement to evaluate accurately.
        if account_id == 'ACCT-001':
            if not has_northstar_agreement:
                limitations.append("Northstar account detected, but Northstar Enterprise Agreement is missing. Cannot reliably determine cancellation fee.")
                return DecisionResult("UNKNOWN", None, "missing_customer_agreement", evidence, limitations, False)
            evidence.append({"source": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "rule": "Northstar Waiver for BOOKED shipments"})

        if account_id == 'ACCT-002':
            if not has_lumenworks_agreement:
                limitations.append("LumenWorks account detected, but LumenWorks Service Agreement is missing. Cannot reliably determine overrides.")
                return DecisionResult("UNKNOWN", None, "missing_customer_agreement", evidence, limitations, False)
            evidence.append({"source": "06_LumenWorks_Service_Agreement.pdf", "rule": "No special cancellation-fee waiver applies"})

        if status == 'BOOKED':
            if account_id == 'ACCT-001':
                return DecisionResult(
                    decision="CANCELLATION_ALLOWED",
                    amount=0,
                    applicable_rule="northstar_cancellation_override",
                    evidence=evidence,
                    limitations=limitations,
                    requires_confirmation=False
                )
            else:
                fee = 250 if elapsed_mins > 30 else 0
                return DecisionResult(
                    decision="CANCELLATION_ALLOWED",
                    amount=fee,
                    applicable_rule="general_cancellation_sop",
                    evidence=evidence,
                    limitations=limitations,
                    requires_confirmation=False
                )
        elif status == 'DRAFT':
            return DecisionResult("CANCELLATION_ALLOWED", 0, "general_cancellation_sop", evidence, limitations, False)
        elif status == 'PICKED_UP':
            return DecisionResult("CANCELLATION_NOT_ALLOWED", None, "general_cancellation_sop", evidence, limitations, False)
        else:
            return DecisionResult("CANCELLATION_NOT_ALLOWED", None, "general_cancellation_sop", evidence, limitations, False)


class AgentOrchestrator:
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, rule_engine: RuleEngine):
        self.data_store = data_store
        self.doc_store = doc_store
        self.rule_engine = rule_engine

    def handle_cancellation_query(self, context: SecurityContext, order_id: str, simulate_missing: List[str] = None) -> str:
        try:
            order_facts = self.data_store.query_orders(context, order_id)
        except PermissionError:
            return "You are not authorized to view this order."
            
        if not order_facts:
            return "Order not found."
            
        docs = self.doc_store.retrieve(context, RetrievalMode.CURRENT, simulate_missing)
        decision = self.rule_engine.evaluate_cancellation(order_facts, docs, context.snapshot_time)
        
        # Format human-readable output without CoT
        if decision.decision == "UNKNOWN":
            return f"I cannot reliably determine the cancellation fee. Limitations: {', '.join(decision.limitations)}"
            
        if decision.decision == "CANCELLATION_ALLOWED":
            return f"Yes, you can cancel this order. Fee: ₹{decision.amount}."
        else:
            return "No, this order cannot be cancelled using the standard procedure."

class TestPhase2Verification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_store = OperationalDataStore("g:/ParcelPilot/ParcelPilot_Assessment_Data.xlsx")
        cls.doc_store = DocumentStore()
        cls.rule_engine = RuleEngine()
        cls.agent = AgentOrchestrator(cls.data_store, cls.doc_store, cls.rule_engine)
        
        cls.snapshot_time = IST.localize(datetime(2026, 8, 16, 11, 0))
        cls.cust_northstar = SecurityContext("customer", frozenset(["ACCT-001"]), cls.snapshot_time)
        cls.cust_lumenworks = SecurityContext("customer", frozenset(["ACCT-002"]), cls.snapshot_time)

    def test_ord_1001_northstar_decision_trace(self):
        order_facts = self.data_store.query_orders(self.cust_northstar, "ORD-1001")
        docs = self.doc_store.retrieve(self.cust_northstar, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_cancellation(order_facts, docs, self.cust_northstar.snapshot_time)
        
        print("\n--- TEST 1: ORD-1001 Northstar Verification ---")
        print("RAW FACTS:", order_facts['order_id'], order_facts['status'], order_facts['booked_at'])
        elapsed = (self.cust_northstar.snapshot_time - pd.to_datetime(order_facts['booked_at']).tz_localize(IST)).total_seconds() / 60
        print(f"ELAPSED TIME (from snapshot): {elapsed} minutes")
        print("DECISION RESULT:\n", json.dumps(res.__dict__, indent=2))
        
        self.assertEqual(res.amount, 0)
        self.assertEqual(res.applicable_rule, "northstar_cancellation_override")

    def test_ord_2001_lumenworks_decision_trace(self):
        order_facts = self.data_store.query_orders(self.cust_lumenworks, "ORD-2001")
        docs = self.doc_store.retrieve(self.cust_lumenworks, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_cancellation(order_facts, docs, self.cust_lumenworks.snapshot_time)
        
        print("\n--- TEST 2: ORD-2001 LumenWorks Verification ---")
        print("RAW FACTS:", order_facts['order_id'], order_facts['status'], order_facts['booked_at'])
        elapsed = (self.cust_lumenworks.snapshot_time - pd.to_datetime(order_facts['booked_at']).tz_localize(IST)).total_seconds() / 60
        print(f"ELAPSED TIME (from snapshot): {elapsed} minutes")
        print("DECISION RESULT:\n", json.dumps(res.__dict__, indent=2))
        
        self.assertEqual(res.amount, 250)
        self.assertEqual(res.applicable_rule, "general_cancellation_sop")
        
    def test_cancellation_uses_snapshot_time(self):
        # ORD-2001 booked at 2026-08-16 09:45. Normal snapshot is 11:00 (75 mins -> 250 fee).
        # Let's use a new snapshot time of 2026-08-16 09:15 (15 mins -> 0 fee).
        early_snapshot = IST.localize(datetime(2026, 8, 16, 9, 15))
        ctx_early = SecurityContext("customer", frozenset(["ACCT-002"]), early_snapshot)
        
        order_facts = self.data_store.query_orders(ctx_early, "ORD-2001")
        docs = self.doc_store.retrieve(ctx_early, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_cancellation(order_facts, docs, ctx_early.snapshot_time)
        
        print("\n--- TEST 3: Snapshot Time Change Verification ---")
        print(f"Early snapshot time: {early_snapshot}")
        print(f"Fee derived: INR {res.amount}")
        self.assertEqual(res.amount, 0)
        
    def test_missing_agreement_no_silent_fallback(self):
        print("\n--- TEST 4: Missing Agreement (No Silent Fallback) Verification ---")
        # Simulate missing Northstar agreement
        order_facts = self.data_store.query_orders(self.cust_northstar, "ORD-1001")
        docs = self.doc_store.retrieve(self.cust_northstar, RetrievalMode.CURRENT, simulate_missing=["05_Northstar_Logistics_Enterprise_Agreement.pdf"])
        res = self.rule_engine.evaluate_cancellation(order_facts, docs, self.cust_northstar.snapshot_time)
        
        print("DECISION RESULT:\n", json.dumps(res.__dict__, indent=2))
        self.assertEqual(res.decision, "UNKNOWN")
        self.assertIn("missing_customer_agreement", res.applicable_rule)
        
    def test_lumenworks_cannot_use_northstar_agreement(self):
        print("\n--- TEST 5: LumenWorks Cannot Use Northstar Agreement Verification ---")
        docs = self.doc_store.retrieve(self.cust_lumenworks, RetrievalMode.CURRENT)
        filenames = [d["metadata"]["filename"] for d in docs]
        print("Retrieved files for LumenWorks:", filenames)
        self.assertNotIn("05_Northstar_Logistics_Enterprise_Agreement.pdf", filenames)

if __name__ == '__main__':
    unittest.main()
