import unittest
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import pytz
import os

IST = pytz.timezone('Asia/Kolkata')

# 1 & 2 & 3. Corrected SecurityContext
@dataclass(frozen=True)
class SecurityContext:
    """
    MOCK AUTHORIZATION CONTEXT:
    In a production system, identity and scoping would be provided securely 
    via an IdP (Identity Provider) and session token. Here, it is mocked 
    to validate data-layer access controls for the assessment.
    """
    role: str
    account_scope: frozenset
    snapshot_time: datetime

    def __post_init__(self):
        if self.snapshot_time.tzinfo is None:
            raise ValueError("snapshot_time must be timezone-aware (e.g., Asia/Kolkata)")

class RetrievalMode(Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"

# Document Metadata
DOCUMENT_METADATA_DEFS = {
    "doc_01": {"status": "CURRENT", "customer_scope": frozenset(["General"])},
    "doc_02": {"status": "DEPRECATED", "customer_scope": frozenset(["General"])},
    "doc_03": {"status": "CURRENT", "customer_scope": frozenset(["General"])},
    "doc_04": {"status": "CURRENT", "customer_scope": frozenset(["General"])},
    "doc_05": {"status": "ACTIVE", "customer_scope": frozenset(["ACCT-001"])},
    "doc_06": {"status": "ACTIVE", "customer_scope": frozenset(["ACCT-002"])}
}

# 4. Explicit Authorization Logic
def is_authorized(context: SecurityContext, target_account_id: str) -> bool:
    if context.role == "support_admin":
        return True
    elif context.role == "support_agent":
        return target_account_id in context.account_scope
    elif context.role == "customer":
        return target_account_id in context.account_scope
    return False

def is_doc_authorized(context: SecurityContext, doc_scope: frozenset) -> bool:
    if context.role == "support_admin":
        return True
    if "General" in doc_scope:
        return True
    return not doc_scope.isdisjoint(context.account_scope)

class DocumentStore:
    def retrieve(self, context: SecurityContext, mode: RetrievalMode) -> List[Dict[str, Any]]:
        results = []
        for doc_id, meta in DOCUMENT_METADATA_DEFS.items():
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

# 5. RETRIEVAL -> APPLICABILITY -> AUTHORITY -> DECISION
class RuleEngine:
    def evaluate_cancellation(self, order_facts: dict, docs: List[dict], snapshot_time: datetime) -> dict:
        # APPLICABILITY
        account_id = order_facts['account_id']
        status = order_facts['status']
        booked_at = pd.to_datetime(order_facts['booked_at']).tz_localize(IST)
        
        elapsed_mins = (snapshot_time - booked_at).total_seconds() / 60
        is_northstar = account_id == 'ACCT-001'
        
        # We ensure docs contain the relevant agreements/SOPs
        doc_ids = [d['id'] for d in docs]
        has_sop = "doc_03" in doc_ids
        has_northstar_agreement = "doc_05" in doc_ids
        
        if not has_sop:
            return {"error": "Missing SOP rules for cancellation."}

        # AUTHORITY & DECISION
        if status == 'BOOKED':
            if is_northstar and has_northstar_agreement:
                return {
                    "allowed": True,
                    "fee": 0,
                    "reason": "Northstar Enterprise Agreement waives cancellation fee for BOOKED shipments regardless of time.",
                    "authoritative_source": "05_Northstar_Logistics_Enterprise_Agreement.pdf"
                }
            else:
                fee = 250 if elapsed_mins > 30 else 0
                return {
                    "allowed": True,
                    "fee": fee,
                    "reason": f"General SOP applies. {elapsed_mins} mins elapsed.",
                    "authoritative_source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"
                }
        elif status == 'DRAFT':
            return {"allowed": True, "fee": 0, "reason": "DRAFT shipments cancel for free."}
        elif status == 'PICKED_UP':
            return {"allowed": False, "fee": None, "reason": "Use Return-to-origin workflow."}
        else:
            return {"allowed": False, "fee": None, "reason": "Cannot cancel DELIVERED."}

class AgentOrchestrator:
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, rule_engine: RuleEngine):
        self.data_store = data_store
        self.doc_store = doc_store
        self.rule_engine = rule_engine

    def handle_cancellation_query(self, context: SecurityContext, order_id: str) -> str:
        # Step 1: Secure Data Retrieval
        try:
            order_facts = self.data_store.query_orders(context, order_id)
        except PermissionError:
            return "You are not authorized to view this order."
            
        if not order_facts:
            return "Order not found."
            
        # Step 2: Secure Doc Retrieval
        docs = self.doc_store.retrieve(context, RetrievalMode.CURRENT)
        
        # Step 3: Rule Evaluation
        decision = self.rule_engine.evaluate_cancellation(order_facts, docs, context.snapshot_time)
        
        # Step 4: Formatting Response
        if decision.get("allowed"):
            return f"Yes, you can cancel this order. Fee: ₹{decision['fee']}. Reason: {decision['reason']} (Source: {decision['authoritative_source']})"
        else:
            return f"No, this order cannot be cancelled. Reason: {decision['reason']}"

# TESTS
class TestPhase2Architecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot_time = IST.localize(datetime(2026, 8, 16, 11, 0))
        cls.data_store = OperationalDataStore("g:/ParcelPilot/ParcelPilot_Assessment_Data.xlsx")
        cls.doc_store = DocumentStore()
        cls.rule_engine = RuleEngine()
        cls.agent = AgentOrchestrator(cls.data_store, cls.doc_store, cls.rule_engine)
        
        cls.cust_northstar = SecurityContext("customer", frozenset(["ACCT-001"]), cls.snapshot_time)
        cls.cust_lumenworks = SecurityContext("customer", frozenset(["ACCT-002"]), cls.snapshot_time)
        cls.support_agent = SecurityContext("support_agent", frozenset(["ACCT-001"]), cls.snapshot_time)
        cls.support_admin = SecurityContext("support_admin", frozenset(["ALL"]), cls.snapshot_time)

    # FOUNDATION SECURITY TESTS
    def test_customer_access_own_account(self):
        order = self.data_store.query_orders(self.cust_northstar, "ORD-1001") # ACCT-001
        self.assertIsNotNone(order)

    def test_customer_access_another_account(self):
        with self.assertRaises(PermissionError):
            self.data_store.query_orders(self.cust_northstar, "ORD-2001") # ACCT-002

    def test_customer_retrieve_own_agreement(self):
        docs = self.doc_store.retrieve(self.cust_northstar, RetrievalMode.CURRENT)
        doc_ids = [d["id"] for d in docs]
        self.assertIn("doc_05", doc_ids) # Northstar agreement
        
    def test_customer_retrieve_another_agreement(self):
        docs = self.doc_store.retrieve(self.cust_northstar, RetrievalMode.CURRENT)
        doc_ids = [d["id"] for d in docs]
        self.assertNotIn("doc_06", doc_ids) # LumenWorks agreement
        
    def test_customer_retrieve_general_policy(self):
        docs = self.doc_store.retrieve(self.cust_northstar, RetrievalMode.CURRENT)
        doc_ids = [d["id"] for d in docs]
        self.assertIn("doc_01", doc_ids) # General Support Policy v3
        
    def test_support_agent_access_assigned(self):
        order = self.data_store.query_orders(self.support_agent, "ORD-1001")
        self.assertIsNotNone(order)
        
    def test_support_agent_access_unassigned(self):
        with self.assertRaises(PermissionError):
            self.data_store.query_orders(self.support_agent, "ORD-2001")
            
    def test_support_admin_global_access(self):
        order1 = self.data_store.query_orders(self.support_admin, "ORD-1001")
        order2 = self.data_store.query_orders(self.support_admin, "ORD-2001")
        self.assertIsNotNone(order1)
        self.assertIsNotNone(order2)

    def test_current_mode_excludes_deprecated(self):
        docs = self.doc_store.retrieve(self.support_admin, RetrievalMode.CURRENT)
        doc_ids = [d["id"] for d in docs]
        self.assertNotIn("doc_02", doc_ids)

    def test_historical_mode_allows_deprecated_with_label(self):
        docs = self.doc_store.retrieve(self.support_admin, RetrievalMode.HISTORICAL)
        doc_02 = next(d for d in docs if d["id"] == "doc_02")
        self.assertEqual(doc_02["metadata"]["historical_label"], "[HISTORICAL - NOT CURRENT]")
        
    def test_snapshot_cannot_be_modified(self):
        with self.assertRaises(Exception):
            self.cust_northstar.snapshot_time = datetime.now()
            
    def test_snapshot_timezone_enforced(self):
        with self.assertRaises(ValueError):
            SecurityContext("customer", frozenset(["ACCT-001"]), datetime(2026, 8, 16, 11, 0))

    # PHASE 2 VERTICAL SLICE TEST (Northstar Cancellation)
    def test_northstar_cancellation_e2e(self):
        # ORD-1001 was booked at 09:00. Snapshot is 11:00 (120 mins).
        # Normal fee would be 250. Northstar agreement waives it.
        response = self.agent.handle_cancellation_query(self.cust_northstar, "ORD-1001")
        self.assertIn("Fee: ₹0", response)
        self.assertIn("Northstar Enterprise Agreement", response)
        
    def test_lumenworks_cancellation_e2e(self):
        # ORD-2001 was booked at 09:45. Snapshot is 11:00 (75 mins).
        # Lumenworks has no special waiver, so General SOP applies (Fee: 250).
        response = self.agent.handle_cancellation_query(self.cust_lumenworks, "ORD-2001")
        self.assertIn("Fee: ₹250", response)
        self.assertIn("General SOP applies", response)

if __name__ == '__main__':
    unittest.main()
