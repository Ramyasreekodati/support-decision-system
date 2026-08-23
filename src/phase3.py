import pathlib
import unittest
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timedelta
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
    amount: Optional[float]
    applicable_rule: str
    evidence: List[Dict[str, str]]
    limitations: List[str]
    requires_confirmation: bool

@dataclass
class ServiceCreditDecision:
    eligibility: str  # ELIGIBLE, NOT_ELIGIBLE, UNKNOWN
    credit_amount: Optional[float]
    applicable_rule: str
    conditions_checked: List[str]
    conditions_missing: List[str]
    customer_override: Optional[str]
    cap_status: str  # VERIFIED, NOT_APPLICABLE, UNKNOWN
    evidence: List[Dict[str, str]]
    requires_manager_approval: bool
    limitations: List[str]

class RuleEngine:
    def evaluate_cancellation(self, order_facts: dict, docs: List[dict], snapshot_time: datetime) -> DecisionResult:
        account_id = order_facts['account_id']
        status = order_facts['status']
        booked_at = pd.to_datetime(order_facts['booked_at']).tz_localize(IST)
        elapsed_mins = (snapshot_time - booked_at).total_seconds() / 60
        
        filenames = [d['metadata']['filename'] for d in docs]
        has_sop = "03_Cancellation_and_Service_Credit_SOP_v4.pdf" in filenames
        has_northstar_agreement = "05_Northstar_Logistics_Enterprise_Agreement.pdf" in filenames
        has_lumenworks_agreement = "06_LumenWorks_Service_Agreement.pdf" in filenames
        
        evidence = []
        limitations = []
        if has_sop:
            evidence.append({"source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf", "rule": "General Cancellation SOP", "authority": "GENERAL_POLICY"})
        else:
            limitations.append("Missing General Cancellation SOP.")
            return DecisionResult("UNKNOWN", None, "none", evidence, limitations, False)

        if account_id == 'ACCT-001':
            if not has_northstar_agreement:
                limitations.append("Northstar account detected, but Northstar Enterprise Agreement is missing. Cannot reliably determine cancellation fee.")
                return DecisionResult("UNKNOWN", None, "missing_customer_agreement", evidence, limitations, False)
            evidence.append({"source": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "rule": "Northstar Waiver for BOOKED shipments", "authority": "CUSTOMER_SPECIFIC"})

        if account_id == 'ACCT-002':
            if not has_lumenworks_agreement:
                limitations.append("LumenWorks account detected, but LumenWorks Service Agreement is missing. Cannot reliably determine overrides.")
                return DecisionResult("UNKNOWN", None, "missing_customer_agreement", evidence, limitations, False)
            evidence.append({"source": "06_LumenWorks_Service_Agreement.pdf", "rule": "No special cancellation-fee waiver applies", "authority": "CUSTOMER_SPECIFIC"})

        if status == 'BOOKED':
            if account_id == 'ACCT-001':
                return DecisionResult("CANCELLATION_ALLOWED", 0, "northstar_cancellation_override", evidence, limitations, False)
            else:
                fee = 250 if elapsed_mins > 30 else 0
                return DecisionResult("CANCELLATION_ALLOWED", fee, "general_cancellation_sop", evidence, limitations, False)
        elif status == 'DRAFT':
            return DecisionResult("CANCELLATION_ALLOWED", 0, "general_cancellation_sop", evidence, limitations, False)
        else:
            return DecisionResult("CANCELLATION_NOT_ALLOWED", None, "general_cancellation_sop", evidence, limitations, False)

    def evaluate_service_credit(self, order_facts: dict, docs: List[dict], snapshot_time: datetime) -> ServiceCreditDecision:
        account_id = order_facts.get('account_id')
        carrier_fault = order_facts.get('carrier_fault')
        customer_fault = order_facts.get('customer_fault')
        carrier_fault_conflict = order_facts.get('carrier_fault_conflict', False)
        customer_fault_conflict = order_facts.get('customer_fault_conflict', False)
        shipment_fee = order_facts.get('shipment_fee_inr')
        
        window_end_raw = order_facts.get('pickup_window_end')
        window_end = pd.to_datetime(window_end_raw).tz_localize(IST) if not pd.isna(window_end_raw) else None
        actual_pickup = order_facts.get('pickup_actual_at')

        if window_end is None:
            return ServiceCreditDecision("UNKNOWN", None, "none", [], ["pickup_window_end"], None, "UNKNOWN", [], False, ["Missing pickup window."])

        # Active delay handling: documents do not explicitly allow calculating delay against snapshot if pickup hasn't happened.
        if pd.isna(actual_pickup) or actual_pickup is None:
            return ServiceCreditDecision("UNKNOWN", None, "none", [], ["pickup_actual_at"], None, "UNKNOWN", [], False, ["Pickup timing is unknown (pickup_actual_at is missing). The SOP explicitly forbids promising credit when pickup timing is unknown."])
            
        actual_pickup_dt = pd.to_datetime(actual_pickup).tz_localize(IST)
        delay_hours = (actual_pickup_dt - window_end).total_seconds() / 3600.0

        filenames = [d['metadata']['filename'] for d in docs]
        has_sop = "03_Cancellation_and_Service_Credit_SOP_v4.pdf" in filenames
        has_nw_agmt = "05_Northstar_Logistics_Enterprise_Agreement.pdf" in filenames
        has_lw_agmt = "06_LumenWorks_Service_Agreement.pdf" in filenames

        evidence = []
        conditions_checked = [f"Pickup delay: {delay_hours:.2f} hours"]
        conditions_missing = []
        limitations = []
        
        if carrier_fault_conflict or customer_fault_conflict:
            limitations.append("Trusted sources contain conflicting fault information.")
            return ServiceCreditDecision("UNKNOWN", None, "conflict_resolution_required", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
            
        # Check faults
        if pd.isna(carrier_fault) or carrier_fault is None:
            conditions_missing.append("carrier_fault")
        else:
            conditions_checked.append(f"Carrier fault: {carrier_fault}")
            
        if pd.isna(customer_fault) or customer_fault is None:
            conditions_missing.append("customer_fault")
        else:
            conditions_checked.append(f"Customer fault: {customer_fault}")
            
        if pd.isna(shipment_fee) or shipment_fee is None:
            conditions_missing.append("shipment_fee_inr")

        if not has_sop:
            limitations.append("Missing General Service Credit SOP.")
            return ServiceCreditDecision("UNKNOWN", None, "none", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
        else:
            evidence.append({"source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf", "rule": "General Service Credit SOP", "authority": "GENERAL_POLICY"})

        # Check agreements
        if account_id == 'ACCT-001':
            if not has_nw_agmt:
                limitations.append("Missing Northstar Agreement.")
                return ServiceCreditDecision("UNKNOWN", None, "missing_customer_agreement", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
            evidence.append({"source": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "rule": "Northstar terms", "authority": "CUSTOMER_SPECIFIC"})
            
        if account_id == 'ACCT-002':
            if not has_lw_agmt:
                limitations.append("Missing LumenWorks Agreement.")
                return ServiceCreditDecision("UNKNOWN", None, "missing_customer_agreement", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
            evidence.append({"source": "06_LumenWorks_Service_Agreement.pdf", "rule": "LumenWorks fixed credit amount and threshold", "authority": "CUSTOMER_SPECIFIC"})

        # Unknown handling
        if "carrier_fault" in conditions_missing or "customer_fault" in conditions_missing:
            limitations.append("Cannot verify fault.")
            return ServiceCreditDecision("UNKNOWN", None, "fault_verification_required", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)

        if carrier_fault == False or customer_fault == True:
            return ServiceCreditDecision("NOT_ELIGIBLE", None, "fault_conditions_not_met", conditions_checked, conditions_missing, None, "NOT_APPLICABLE", evidence, False, limitations)

        # Cap applies to everyone unless specifically waived. We have no history for anyone.
        cap_status = "UNKNOWN"
        limitations.append("Monthly aggregate service credits are capped at INR 5,000, but historical credit data is unavailable.")

        # LUMENWORKS OVERRIDE
        if account_id == 'ACCT-002':
            if delay_hours > 4:
                return ServiceCreditDecision("ELIGIBLE", 300.0, "lumenworks_override", conditions_checked, conditions_missing, "LumenWorks >4h rule", cap_status, evidence, False, limitations)
            else:
                return ServiceCreditDecision("NOT_ELIGIBLE", None, "lumenworks_override", conditions_checked, conditions_missing, "LumenWorks >4h rule", "NOT_APPLICABLE", evidence, False, limitations)

        # GENERAL SOP (and Northstar base formula)
        if delay_hours > 2:
            if "shipment_fee_inr" in conditions_missing:
                limitations.append("Shipment fee missing, cannot calculate 10%.")
                return ServiceCreditDecision("UNKNOWN", None, "general_sop", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
            
            calculated_credit = min(500.0, 0.1 * float(shipment_fee))
            requires_approval = True if calculated_credit > 1000 else False
            
            return ServiceCreditDecision("ELIGIBLE", calculated_credit, "general_sop", conditions_checked, conditions_missing, None, cap_status, evidence, requires_approval, limitations)
        else:
            return ServiceCreditDecision("NOT_ELIGIBLE", None, "general_sop", conditions_checked, conditions_missing, None, "NOT_APPLICABLE", evidence, False, limitations)

# TESTS
class TestPhase3ServiceCredits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot_time = IST.localize(datetime(2026, 8, 16, 11, 0))
        cls.data_store = OperationalDataStore(pathlib.Path(__file__).resolve().parent.parent / "ParcelPilot_Assessment_Data.xlsx")
        cls.doc_store = DocumentStore()
        cls.rule_engine = RuleEngine()
        
        cls.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), cls.snapshot_time)
        cls.lw_ctx = SecurityContext("customer", frozenset(["ACCT-002"]), cls.snapshot_time)

    def _mock_order(self, account_id, delay_hours, c_fault, cust_fault, fee):
        # Helper to create perfectly crafted order facts for the matrix
        window_end = self.snapshot_time - timedelta(hours=delay_hours)
        return {
            'account_id': account_id,
            'pickup_window_end': window_end.strftime("%Y-%m-%d %H:%M"),
            'pickup_actual_at': self.snapshot_time.strftime("%Y-%m-%d %H:%M"),
            'carrier_fault': c_fault,
            'customer_fault': cust_fault,
            'shipment_fee_inr': fee
        }

    # 1. LumenWorks 3-hour delay → NOT_ELIGIBLE
    def test_lw_3h_delay(self):
        order = self._mock_order('ACCT-002', 3, True, False, 5000)
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "NOT_ELIGIBLE")

    # 2. LumenWorks 5-hour delay + carrier fault + no customer fault → ₹300
    def test_lw_5h_delay_eligible(self):
        order = self._mock_order('ACCT-002', 5, True, False, 5000)
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "ELIGIBLE")
        self.assertEqual(res.credit_amount, 300)

    # 3. LumenWorks 5-hour delay + customer fault → NOT_ELIGIBLE
    def test_lw_5h_delay_customer_fault(self):
        order = self._mock_order('ACCT-002', 5, True, True, 5000)
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "NOT_ELIGIBLE")

    # 4. Unknown carrier fault → UNKNOWN
    def test_unknown_carrier_fault(self):
        order = self._mock_order('ACCT-002', 5, None, False, 5000)
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertIn("carrier_fault", res.conditions_missing)

    # 5. Default customer >2h + carrier fault + no cust fault → SOP calc (400)
    def test_default_gt_2h(self):
        order = self._mock_order('ACCT-003', 3, True, False, 4000)
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "ELIGIBLE")
        self.assertEqual(res.credit_amount, 400.0) # 10% of 4000

    # 6. Default customer ≤2h → NOT_ELIGIBLE
    def test_default_lt_2h(self):
        order = self._mock_order('ACCT-003', 1.5, True, False, 4000)
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "NOT_ELIGIBLE")

    # 7. Missing shipment fee → UNKNOWN where required
    def test_missing_shipment_fee(self):
        order = self._mock_order('ACCT-003', 3, True, False, None)
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertIn("shipment_fee_inr", res.conditions_missing)

    # 8. Northstar eligible but credit history missing → cap UNKNOWN
    def test_northstar_eligible_cap_unknown(self):
        order = self._mock_order('ACCT-001', 3, True, False, 6000)
        ctx = SecurityContext("customer", frozenset(["ACCT-001"]), self.snapshot_time)
        docs = self.doc_store.retrieve(ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "ELIGIBLE")
        self.assertEqual(res.credit_amount, 500.0) # Cap of min formula
        self.assertEqual(res.cap_status, "UNKNOWN")
        self.assertTrue(any("INR 5,000" in l for l in res.limitations))

    # 9. Missing customer agreement → UNKNOWN
    def test_missing_customer_agreement(self):
        order = self._mock_order('ACCT-002', 5, True, False, 5000)
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT, simulate_missing=["06_LumenWorks_Service_Agreement.pdf"])
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertEqual(res.applicable_rule, "missing_customer_agreement")

    # 10. Cross-account access → Unauthorized (Data tool)
    def test_cross_account_access(self):
        with self.assertRaises(PermissionError):
            self.data_store.query_orders(self.lw_ctx, "ORD-1001") # ACCT-001

    # 11. Conflicting evidence test
    def test_conflicting_evidence(self):
        order = self._mock_order('ACCT-002', 5, True, False, 5000)
        order['carrier_fault_conflict'] = True
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertTrue(any("conflict" in l for l in res.limitations))

    # 12. Missing irrelevant agreement
    def test_missing_irrelevant_agreement(self):
        order = self._mock_order('ACCT-003', 3, True, False, 4000) # Default customer
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT, simulate_missing=["06_LumenWorks_Service_Agreement.pdf"])
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "ELIGIBLE") # Proceeds normally, not UNKNOWN
        
    # 13. Active delay missing pickup_actual_at
    def test_active_delay_missing_pickup_actual_at(self):
        order = self._mock_order('ACCT-002', 5, True, False, 5000)
        order['pickup_actual_at'] = None
        docs = self.doc_store.retrieve(self.lw_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_service_credit(order, docs, self.snapshot_time)
        self.assertEqual(res.eligibility, "UNKNOWN")
        self.assertTrue(any("pickup_actual_at is missing" in l for l in res.limitations))

    # Ensure Phase 2 tests still run properly
    def test_phase2_cancellation_still_works(self):
        order = self.data_store.query_orders(self.admin_ctx, "ORD-1001")
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_cancellation(order, docs, self.snapshot_time)
        self.assertEqual(res.decision, "CANCELLATION_ALLOWED")
        self.assertEqual(res.amount, 0)

if __name__ == '__main__':
    unittest.main()
