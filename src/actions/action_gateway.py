from enum import Enum
from typing import Dict, Any, Optional
import hashlib
import json
from src.security.authorization import SecurityContext, is_authorized, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore

class ActionState(Enum):
    PREPARED = "PREPARED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"

class ActionGateway:
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, rule_engine: Optional[Any] = None):
        self.data_store = data_store
        self.doc_store = doc_store
        self.rule_engine = rule_engine
        self.pending_actions: Dict[str, Dict[str, Any]] = {}
        self.executed_actions = []

    def _compute_hash(self, payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def prepare(self, context: SecurityContext, payload: dict) -> str:
        action_id = f"act_{len(self.pending_actions) + len(self.executed_actions) + 1}"
        self.pending_actions[action_id] = {
            "action_id": action_id,
            "payload": payload,
            "payload_hash": self._compute_hash(payload),
            "state": ActionState.PREPARED,
            "context_scope": context.account_scope
        }
        return action_id

    def get_pending_action(self, action_id: str) -> Optional[dict]:
        return self.pending_actions.get(action_id)

    def approve(self, action_id: str, current_context: SecurityContext) -> dict:
        return self.revalidate_and_execute(action_id, current_context)

    def reject(self, action_id: str) -> dict:
        if action_id not in self.pending_actions:
            return {"status": "FAILED", "error": f"Action ID {action_id} not found."}
        self.pending_actions[action_id]["state"] = ActionState.REJECTED
        return {"status": "REJECTED", "action_id": action_id, "message": f"Action {action_id} was rejected. No mutation occurred."}

    def revalidate_and_execute(self, action_id: str, current_context: SecurityContext) -> dict:
        revalidation = {
            "authorization": "FAILED",
            "record_access": "FAILED",
            "rule_state": "FAILED",
            "payload_integrity": "FAILED"
        }

        if action_id not in self.pending_actions:
            for act in self.executed_actions:
                if act.get("action_id") == action_id:
                    return {"status": "FAILED", "error": "Action already executed", "revalidation": revalidation}
            return {"status": "FAILED", "error": "Action ID not found", "revalidation": revalidation}

        action = self.pending_actions[action_id]
        if action["state"] == ActionState.EXECUTED:
            return {"status": "FAILED", "error": "Action already executed", "revalidation": revalidation}
        if action["state"] == ActionState.REJECTED:
            return {"status": "FAILED", "error": "Cannot execute rejected action", "revalidation": revalidation}

        # 1. Authorization Recheck
        payload_acc = action["payload"].get("account_id")
        if not is_authorized(current_context, payload_acc):
            return {"status": "FAILED", "error": "User context lacks authority to execute action", "revalidation": revalidation}
        revalidation["authorization"] = "PASSED"

        # 2. Record Access Recheck
        ticket_id = action["payload"].get("ticket_id")
        try:
            tkt = self.data_store.query_tickets(current_context, ticket_id)
            if not tkt:
                return {"status": "FAILED", "error": "Target record no longer accessible", "revalidation": revalidation}
        except PermissionError:
            return {"status": "FAILED", "error": "Target record permission denied", "revalidation": revalidation}
        revalidation["record_access"] = "PASSED"

        # 3. Rule State Recheck
        if self.rule_engine:
            docs = self.doc_store.retrieve(current_context)
            sla_res = self.rule_engine.evaluate_sla(tkt, docs, current_context.snapshot_time)
            if sla_res.escalation_requirement != "REQUIRED":
                return {"status": "FAILED", "error": "Underlying rule state changed; escalation no longer required", "revalidation": revalidation}
        revalidation["rule_state"] = "PASSED"

        # 4. Payload Integrity Recheck
        if self._compute_hash(action["payload"]) != action["payload_hash"]:
            return {"status": "FAILED", "error": "Payload hash mismatch; payload was modified in flight", "revalidation": revalidation}
        revalidation["payload_integrity"] = "PASSED"

        # 5. Execute Action
        action["state"] = ActionState.EXECUTED
        self.executed_actions.append(action)
        del self.pending_actions[action_id]

        return {
            "status": "EXECUTED",
            "action_id": action_id,
            "revalidation": revalidation,
            "execution": {
                "status": "SUCCESS",
                "action_id": action_id,
                "timestamp": str(current_context.snapshot_time),
                "payload": action["payload"]
            }
        }
