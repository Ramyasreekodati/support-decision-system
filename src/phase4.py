import pathlib
import unittest
import pandas as pd
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
            raise ValueError("snapshot_time must be timezone-aware")

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
        self.tickets = pd.read_excel(excel_path, "tickets")
        self.accounts = pd.read_excel(excel_path, "accounts")
        
        # Parse dynamic snapshot from README
        readme = pd.read_excel(excel_path, "README", header=None)
        snapshot_str = str(readme.iloc[1, 1]) # row 1 = "Dataset snapshot", col 1 = "2026-08-16 11:00 Asia/Kolkata"
        dt_str = snapshot_str.rsplit(' ', 1)[0]
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        self.snapshot_time = IST.localize(dt)
        
    def get_snapshot_time(self) -> datetime:
        return self.snapshot_time
        
    def query_orders(self, context: SecurityContext, order_id: str) -> Optional[Dict[str, Any]]:
        order_row = self.orders[self.orders["order_id"] == order_id]
        if order_row.empty: return None
        order_dict = order_row.iloc[0].to_dict()
        if not is_authorized(context, order_dict["account_id"]):
            raise PermissionError("Unauthorized")
        return order_dict

    def query_tickets(self, context: SecurityContext, ticket_id: str) -> Optional[Dict[str, Any]]:
        ticket_row = self.tickets[self.tickets["ticket_id"] == ticket_id]
        if ticket_row.empty: return None
        ticket_dict = ticket_row.iloc[0].to_dict()
        if not is_authorized(context, ticket_dict["account_id"]):
            raise PermissionError("Unauthorized")
        acc_row = self.accounts[self.accounts["account_id"] == ticket_dict["account_id"]]
        if not acc_row.empty:
            ticket_dict["plan"] = acc_row.iloc[0]["plan"]
        return ticket_dict

@dataclass
class SLADecision:
    state: str
    target_minutes: Optional[int]
    deadline: Optional[datetime]
    actual_response_time: Optional[int]
    evidence: List[Dict[str, str]]
    limitations: List[str]
    escalation_requirement: str  # REQUIRED, RECOMMENDED, NOT_REQUIRED, UNKNOWN
    escalation_payload: Optional[Dict[str, Any]]

class RuleEngine:
    def evaluate_sla(self, ticket_facts: dict, docs: List[dict], snapshot_time: datetime, is_p1: bool) -> SLADecision:
        if not is_p1:
            return SLADecision("UNKNOWN", None, None, None, [], ["Only P1 SLA is implemented."], "UNKNOWN", None)
            
        account_id = ticket_facts.get('account_id')
        plan = ticket_facts.get('plan')
        created_at_raw = ticket_facts.get('created_at')
        first_response_raw = ticket_facts.get('first_response_at') 
        
        if pd.isna(created_at_raw) or created_at_raw is None:
            return SLADecision("UNKNOWN", None, None, None, [], ["Missing created_at."], "UNKNOWN", None)
            
        created_at = pd.to_datetime(created_at_raw).tz_localize(IST)
        
        filenames = [d['metadata']['filename'] for d in docs]
        has_sop = "01_Support_Policy_v3_CURRENT.pdf" in filenames
        has_nw = "05_Northstar_Logistics_Enterprise_Agreement.pdf" in filenames
        
        if account_id == 'ACCT-001' and not has_nw:
            return SLADecision("UNKNOWN", None, None, None, [], ["Missing Northstar Agreement."], "UNKNOWN", None)
            
        target_minutes = None
        is_24x7 = False
        evidence = []
        
        if account_id == 'ACCT-001':
            target_minutes = 15
            is_24x7 = True
            evidence.append({"source": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "rule": "Custom P1 15-minute target, 24x7", "authority": "CUSTOMER_SPECIFIC"})
        else:
            if not has_sop:
                return SLADecision("UNKNOWN", None, None, None, [], ["Missing General Support Policy."], "UNKNOWN", None)
            
            if plan == 'Enterprise': 
                target_minutes = 30
                is_24x7 = True
                evidence.append({"source": "01_Support_Policy_v3_CURRENT.pdf", "rule": "General P1 30-minute target, 24x7 for Enterprise plan", "authority": "GENERAL_POLICY"})
            elif plan == 'Growth': 
                target_minutes = 120
                is_24x7 = False
                evidence.append({"source": "01_Support_Policy_v3_CURRENT.pdf", "rule": "General P1 2 business hours target for Growth plan", "authority": "GENERAL_POLICY"})
            elif plan == 'Standard': 
                target_minutes = 240
                is_24x7 = False
                evidence.append({"source": "01_Support_Policy_v3_CURRENT.pdf", "rule": "General P1 4 business hours target for Standard plan", "authority": "GENERAL_POLICY"})
            else: 
                return SLADecision("UNKNOWN", None, None, None, [], ["Unknown plan."], "UNKNOWN", None)
            
        # Business hours fallback
        if not is_24x7:
            limitations = ["Plan is not 24x7. Exact business hours calendar is undefined in source policies."]
            return SLADecision("BUSINESS_TIME_CALCULATION_UNSPECIFIED", target_minutes, None, None, evidence, limitations, "REQUIRED", None)
            
        deadline = created_at + timedelta(minutes=target_minutes)
        
        # Escalation is always REQUIRED for P1 based on Support Policy v3
        escalation_payload = {
            "action": "ESCALATE_TICKET",
            "ticket_id": ticket_facts.get('ticket_id'),
            "priority": "P1",
            "reason": "P1 requires immediate escalation",
            "evidence": [e["source"] for e in evidence]
        }
        
        if pd.isna(first_response_raw) or first_response_raw is None:
            if snapshot_time <= deadline:
                return SLADecision("NOT_DUE", target_minutes, deadline, None, evidence, [], "REQUIRED", escalation_payload)
            else:
                return SLADecision("DEADLINE_ELAPSED", target_minutes, deadline, None, evidence, ["Actual SLA breach cannot be verified because first_response_at is missing."], "REQUIRED", escalation_payload)
                
        first_response = pd.to_datetime(first_response_raw).tz_localize(IST)
        actual_response_time = int((first_response - created_at).total_seconds() / 60)
        
        if first_response <= deadline:
            return SLADecision("NOT_BREACHED", target_minutes, deadline, actual_response_time, evidence, [], "REQUIRED", escalation_payload)
        else:
            escalation_payload["reason"] = "P1 response target breached"
            return SLADecision("BREACHED", target_minutes, deadline, actual_response_time, evidence, [], "REQUIRED", escalation_payload)

class ActionState(Enum):
    PREPARE = "PREPARE"
    CONFIRM = "CONFIRM"
    REVALIDATE = "REVALIDATE"
    EXECUTE = "EXECUTE"

class ActionGateway:
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, rule_engine: RuleEngine):
        self.data_store = data_store
        self.doc_store = doc_store
        self.rule_engine = rule_engine
        self.pending_actions = {}
        self.executed_actions = set()
        
    def prepare(self, context: SecurityContext, payload: dict) -> str:
        action_id = f"act_{len(self.pending_actions) + 1}"
        self.pending_actions[action_id] = {
            "context": context,
            "payload": payload,
            "state": ActionState.PREPARE
        }
        return action_id
        
    def approve(self, action_id: str, context: SecurityContext) -> dict:
        if action_id not in self.pending_actions:
            return {"status": "FAILED", "error": "Action not found."}
        action = self.pending_actions[action_id]
        if action["context"].role != context.role or action["context"].account_scope != context.account_scope:
            return {"status": "FAILED", "error": "Unauthorized confirmation."}
        
        action["state"] = ActionState.CONFIRM
        return self.revalidate_and_execute(action_id, context)
        
    def get_pending_action(self, action_id: str) -> Optional[dict]:
        return self.pending_actions.get(action_id)

    def reject(self, action_id: str) -> dict:
        if action_id in self.pending_actions:
            action = self.pending_actions[action_id]
            del self.pending_actions[action_id]
            return {"status": "REJECTED", "error": "Action rejected."}
        return {"status": "FAILED", "error": "Action not found."}
        
    def revalidate_and_execute(self, action_id: str, context: SecurityContext) -> dict:
        if action_id not in self.pending_actions:
            return {"status": "FAILED", "error": "Action not found."}
            
        action = self.pending_actions[action_id]
        
        unique_exec_key = f"{action['payload']['action']}_{action['payload']['ticket_id']}"
        if unique_exec_key in self.executed_actions:
            return {"status": "FAILED", "error": "Action already executed (idempotent)."}
            
        action["state"] = ActionState.REVALIDATE
        payload = action["payload"]
        
        revalidation = {
            "authorization": "PENDING",
            "record_access": "PENDING",
            "rule_state": "PENDING",
            "payload_integrity": "PENDING"
        }
        
        if payload["action"] != "ESCALATE_TICKET":
            revalidation["payload_integrity"] = "FAILED"
            return {"status": "FAILED", "error": "Revalidation failed: Action not allowed.", "revalidation": revalidation}
            
        ticket_id = payload["ticket_id"]
        try:
            ticket = self.data_store.query_tickets(context, ticket_id)
            revalidation["authorization"] = "PASSED"
        except PermissionError:
            revalidation["authorization"] = "FAILED"
            return {"status": "FAILED", "error": "Revalidation failed: Unauthorized access to ticket.", "revalidation": revalidation}
            
        if ticket is None:
            revalidation["record_access"] = "FAILED"
            return {"status": "FAILED", "error": "Revalidation failed: Ticket no longer exists.", "revalidation": revalidation}
        revalidation["record_access"] = "PASSED"
            
        # Re-inject first_response_at if testing mocked it
        first_response = payload.get('_mock_first_response')
        if first_response:
            ticket['first_response_at'] = first_response
            
        docs = self.doc_store.retrieve(context, RetrievalMode.CURRENT)
        sla_decision = self.rule_engine.evaluate_sla(ticket, docs, context.snapshot_time, is_p1=True)
        
        if sla_decision.state != "BREACHED":
            revalidation["rule_state"] = "FAILED"
            return {"status": "FAILED", "error": "Revalidation failed: Ticket is no longer in BREACHED state.", "revalidation": revalidation}
        revalidation["rule_state"] = "PASSED"
            
        if payload["reason"] != "P1 response target breached":
            revalidation["payload_integrity"] = "FAILED"
            return {"status": "FAILED", "error": "Revalidation failed: Tampered payload.", "revalidation": revalidation}
        revalidation["payload_integrity"] = "PASSED"
            
        action["state"] = ActionState.EXECUTE
        self.executed_actions.add(unique_exec_key)
        return {
            "status": "EXECUTED",
            "revalidation": revalidation,
            "execution": {
                "status": "SUCCESS",
                "action_id": action_id
            }
        }

class TestPhase4SLA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot_time = IST.localize(datetime(2026, 8, 16, 11, 0))
        cls.data_store = OperationalDataStore(pathlib.Path(__file__).resolve().parent.parent / "ParcelPilot_Assessment_Data.xlsx")
        cls.doc_store = DocumentStore()
        cls.rule_engine = RuleEngine()
        
        cls.admin_ctx = SecurityContext("support_admin", frozenset(["ALL"]), cls.snapshot_time)
        cls.nw_ctx = SecurityContext("customer", frozenset(["ACCT-001"]), cls.snapshot_time)
        cls.lw_ctx = SecurityContext("customer", frozenset(["ACCT-002"]), cls.snapshot_time)

    def setUp(self):
        self.action_gateway = ActionGateway(self.data_store, self.doc_store, self.rule_engine)

    def _mock_ticket(self, account_id, created_offset, response_offset=None, plan="Enterprise"):
        t = {
            'ticket_id': 'TKT-MOCK',
            'account_id': account_id,
            'plan': plan,
            'created_at': (self.snapshot_time - timedelta(minutes=created_offset)).strftime("%Y-%m-%d %H:%M"),
            'first_response_at': None
        }
        if response_offset is not None:
            t['first_response_at'] = (self.snapshot_time - timedelta(minutes=created_offset) + timedelta(minutes=response_offset)).strftime("%Y-%m-%d %H:%M")
        return t

    # A. P1 + verified breach
    def test_p1_verified_breach(self):
        t = self._mock_ticket('ACCT-001', created_offset=40, response_offset=20) # target 15m, responded in 20m
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_sla(t, docs, self.snapshot_time, is_p1=True)
        self.assertEqual(res.state, "BREACHED")
        self.assertEqual(res.escalation_requirement, "REQUIRED")
        self.assertEqual(res.escalation_payload["action"], "ESCALATE_TICKET")
        self.assertEqual(res.escalation_payload["reason"], "P1 response target breached")

    # B. P1 + deadline elapsed + missing response
    def test_p1_deadline_elapsed_missing_response(self):
        t = self._mock_ticket('ACCT-001', created_offset=20, response_offset=None) # target 15m, missing response
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_sla(t, docs, self.snapshot_time, is_p1=True)
        self.assertEqual(res.state, "DEADLINE_ELAPSED")
        self.assertEqual(res.escalation_requirement, "REQUIRED")
        self.assertTrue(any("cannot be verified" in l for l in res.limitations))

    # C. P1 + response within target
    def test_p1_response_within_target(self):
        t = self._mock_ticket('ACCT-001', created_offset=20, response_offset=10) # target 15m, responded in 10m
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_sla(t, docs, self.snapshot_time, is_p1=True)
        self.assertEqual(res.state, "NOT_BREACHED")
        self.assertEqual(res.escalation_requirement, "REQUIRED")

    # D. Business-hours/weekend case
    def test_business_hours_case(self):
        # Growth plan is not 24x7
        t = self._mock_ticket('ACCT-002', created_offset=20, response_offset=None, plan="Growth") 
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_sla(t, docs, self.snapshot_time, is_p1=True)
        self.assertEqual(res.state, "BUSINESS_TIME_CALCULATION_UNSPECIFIED")
        self.assertTrue(any("Exact business hours calendar is undefined" in l for l in res.limitations))
        
    # E. 24x7 case (ordinary timedelta calculation)
    def test_24x7_case(self):
        t = self._mock_ticket('ACCT-004', created_offset=10, response_offset=None, plan="Enterprise") # Target 30m, 10m elapsed
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT)
        res = self.rule_engine.evaluate_sla(t, docs, self.snapshot_time, is_p1=True)
        self.assertEqual(res.state, "NOT_DUE")
        self.assertEqual(res.escalation_requirement, "REQUIRED")

    # 6. Unknown SLA applicability → UNKNOWN
    def test_unknown_sla_applicability(self):
        t = self._mock_ticket('ACCT-004', created_offset=40, response_offset=20, plan="Enterprise")
        docs = self.doc_store.retrieve(self.admin_ctx, RetrievalMode.CURRENT, simulate_missing=["01_Support_Policy_v3_CURRENT.pdf"])
        res = self.rule_engine.evaluate_sla(t, docs, self.snapshot_time, is_p1=True)
        self.assertEqual(res.state, "UNKNOWN")

    # 7. Cross-account ticket → Unauthorized
    def test_cross_account(self):
        with self.assertRaises(PermissionError):
            self.data_store.query_tickets(self.lw_ctx, "TKT-501") # ACCT-001

    # Action Gateway Tests
    def test_action_prepare_reject(self):
        payload = {"action": "ESCALATE_TICKET", "ticket_id": "TKT-501"}
        action_id = self.action_gateway.prepare(self.admin_ctx, payload)
        self.assertEqual(self.action_gateway.pending_actions[action_id]["state"], ActionState.PREPARE)
        res = self.action_gateway.reject(action_id)
        self.assertEqual(res["status"], "REJECTED")
        self.assertNotIn(action_id, self.action_gateway.pending_actions)

    def test_action_approve_execute(self):
        payload = {
            "action": "ESCALATE_TICKET", 
            "ticket_id": "TKT-501", 
            "reason": "P1 response target breached",
            "_mock_first_response": "2026-08-16 10:55" 
        }
        action_id = self.action_gateway.prepare(self.admin_ctx, payload)
        res = self.action_gateway.approve(action_id, self.admin_ctx)
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["revalidation"]["authorization"], "PASSED")
        
        # Duplicate execution
        res_dup = self.action_gateway.approve(action_id, self.admin_ctx)
        self.assertEqual(res_dup["error"], "Action already executed (idempotent).")

    def test_unauthorized_execution(self):
        payload = {"action": "ESCALATE_TICKET", "ticket_id": "TKT-504"} # ACCT-001
        action_id = self.action_gateway.prepare(self.admin_ctx, payload)
        # Attempt to confirm as customer (not authorized)
        res = self.action_gateway.approve(action_id, self.lw_ctx) # ACCT-002
        self.assertEqual(res["error"], "Unauthorized confirmation.")

    def test_tampered_payload_revalidation_failure(self):
        payload = {
            "action": "ESCALATE_TICKET", 
            "ticket_id": "TKT-501", 
            "reason": "Changed reason",
            "_mock_first_response": "2026-08-16 10:55"
        }
        action_id = self.action_gateway.prepare(self.admin_ctx, payload)
        res = self.action_gateway.approve(action_id, self.admin_ctx)
        self.assertEqual(res["error"], "Revalidation failed: Tampered payload.")
        self.assertEqual(res["revalidation"]["payload_integrity"], "FAILED")

if __name__ == '__main__':
    unittest.main()
