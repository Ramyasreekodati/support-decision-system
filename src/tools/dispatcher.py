import json
import logging
from typing import Dict, Any, List, Optional
from src.security.authorization import SecurityContext
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore, RetrievalMode
from src.domain.cancellation_engine import CancellationEngine
from src.domain.service_credit_engine import ServiceCreditEngine
from src.domain.sla_engine import SLAEngine
from src.actions.action_gateway import ActionGateway

logger = logging.getLogger(__name__)

class ToolDispatcher:
    """
    Central dispatcher exposing the 7 formal tool contracts.
    Validates schemas, permissions, and routes to deterministic domain engines.
    """
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, action_gateway: ActionGateway):
        self.data_store = data_store
        self.doc_store = doc_store
        self.cancellation_engine = CancellationEngine()
        self.service_credit_engine = ServiceCreditEngine()
        self.sla_engine = SLAEngine()
        self.action_gateway = action_gateway
        self.action_gateway.rule_engine = self.sla_engine
        self.collected_state: Dict[str, Any] = {}

    def get_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_order",
                "description": "Retrieve verified facts for a specific order (status, booking time, fee, fault flags). Enforces tenant isolation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string", "description": "Order ID (e.g. ORD-1001, ORD-2001)"}
                    },
                    "required": ["order_id"]
                }
            },
            {
                "name": "get_ticket",
                "description": "Retrieve verified facts for a support ticket (account, priority, created time, response time). Enforces tenant isolation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string", "description": "Ticket ID (e.g. TKT-501, TKT-999)"}
                    },
                    "required": ["ticket_id"]
                }
            },
            {
                "name": "search_documents",
                "description": "Search active policy documents and customer agreements. Automatically filters out deprecated/superseded policies.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Topic or clause to search (e.g. 'cancellation policy', 'SLA response target')"},
                        "account_id": {"type": "string", "description": "Optional account ID to retrieve customer-specific agreement overrides"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "evaluate_cancellation",
                "description": "Deterministic rule calculation for order cancellation eligibility and fees in INR.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string", "description": "Order ID to evaluate"}
                    },
                    "required": ["order_id"]
                }
            },
            {
                "name": "evaluate_service_credit",
                "description": "Deterministic calculation for service credit eligibility based on pickup delay and fault attribution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string", "description": "Order ID to evaluate"}
                    },
                    "required": ["order_id"]
                }
            },
            {
                "name": "evaluate_sla",
                "description": "Deterministic timezone-aware calculation for ticket SLA deadline and breach verification.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string", "description": "Ticket ID to evaluate"}
                    },
                    "required": ["ticket_id"]
                }
            },
            {
                "name": "prepare_escalation",
                "description": "Stage a proposed P1 escalation in the ActionGateway. Does NOT execute mutations; requires human confirmation in UI.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string", "description": "Ticket ID to escalate"},
                        "priority": {"type": "string", "enum": ["P1", "P2", "P3"], "description": "Priority level"},
                        "reason": {"type": "string", "description": "Justification for escalation"}
                    },
                    "required": ["ticket_id", "priority", "reason"]
                }
            }
        ]

    def dispatch(self, tool_name: str, args: Dict[str, Any], context: SecurityContext) -> Dict[str, Any]:
        if tool_name == "get_order":
            order_id = args.get("order_id", "").strip().upper()
            order = self.data_store.query_orders(context, order_id)
            if not order:
                return {"error": f"Order {order_id} not found."}
            self.collected_state["order"] = order
            self.collected_state["entity_id"] = order_id
            return order

        elif tool_name == "get_ticket":
            ticket_id = args.get("ticket_id", "").strip().upper()
            ticket = self.data_store.query_tickets(context, ticket_id)
            if not ticket:
                return {"error": f"Ticket {ticket_id} not found."}
            self.collected_state["ticket"] = ticket
            self.collected_state["entity_id"] = ticket_id
            return ticket

        elif tool_name == "search_documents":
            query = args.get("query", "").lower()
            docs = self.doc_store.retrieve(context, RetrievalMode.CURRENT)
            self.collected_state["docs"] = docs
            
            results = []
            for d in docs:
                fn = d.get("metadata", {}).get("filename", "")
                content = d.get("content", "")
                auth = "CUSTOMER_SPECIFIC" if "Agreement" in fn else "GENERAL_POLICY"
                
                # Extract relevant text snippets if query keywords match
                snippets = []
                if query:
                    keywords = [k for k in query.split() if len(k) > 2]
                    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                    for p in paragraphs:
                        if any(k in p.lower() for k in keywords):
                            snippets.append(p[:300])
                
                results.append({
                    "filename": fn,
                    "authority": auth,
                    "precedence": "HIGH" if auth == "CUSTOMER_SPECIFIC" else "STANDARD",
                    "matched_snippets": snippets[:3] if snippets else ["Document available for full rule evaluation."]
                })
            return {"retrieved_count": len(results), "documents": results}

        elif tool_name == "evaluate_cancellation":
            order_id = args.get("order_id", "").strip().upper()
            order = self.collected_state.get("order") or self.data_store.query_orders(context, order_id)
            if not order:
                return {"error": f"Order {order_id} not found for cancellation evaluation."}
            docs = self.collected_state.get("docs") or self.doc_store.retrieve(context, RetrievalMode.CURRENT)
            res = self.cancellation_engine.evaluate_cancellation(order, docs, context.snapshot_time)
            self.collected_state["decision_result"] = res
            return {
                "decision": res.decision,
                "amount_inr": res.amount,
                "applicable_rule": res.applicable_rule,
                "evidence": res.evidence,
                "limitations": res.limitations
            }

        elif tool_name == "evaluate_service_credit":
            order_id = args.get("order_id", "").strip().upper()
            order = self.collected_state.get("order") or self.data_store.query_orders(context, order_id)
            if not order:
                return {"error": f"Order {order_id} not found for service credit evaluation."}
            docs = self.collected_state.get("docs") or self.doc_store.retrieve(context, RetrievalMode.CURRENT)
            res = self.service_credit_engine.evaluate_service_credit(order, docs, context.snapshot_time)
            self.collected_state["service_credit_result"] = res
            return {
                "decision": res.eligibility,
                "credit_amount_inr": res.credit_amount,
                "applicable_rule": res.applicable_rule,
                "missing_facts": res.conditions_missing,
                "evidence": res.evidence,
                "limitations": res.limitations
            }

        elif tool_name == "evaluate_sla":
            ticket_id = args.get("ticket_id", "").strip().upper()
            ticket = self.collected_state.get("ticket") or self.data_store.query_tickets(context, ticket_id)
            if not ticket:
                return {"error": f"Ticket {ticket_id} not found for SLA evaluation."}
            docs = self.collected_state.get("docs") or self.doc_store.retrieve(context, RetrievalMode.CURRENT)
            res = self.sla_engine.evaluate_sla(ticket, docs, context.snapshot_time, is_p1=True)
            self.collected_state["sla_result"] = res
            
            output = {
                "decision": res.state,
                "target_minutes": res.target_minutes,
                "deadline": str(res.deadline),
                "actual_response_time": res.actual_response_time,
                "escalation_requirement": res.escalation_requirement,
                "evidence": res.evidence,
                "limitations": res.limitations
            }
            
            if res.escalation_requirement == "REQUIRED" and self.action_gateway and res.escalation_payload:
                action_id = self.action_gateway.prepare(context, res.escalation_payload)
                res.pending_action = action_id
                self.collected_state["pending_action"] = {
                    "action_id": action_id,
                    "type": "ESCALATE_TICKET",
                    "ticket_id": ticket_id,
                    "priority": res.escalation_payload.get("priority", "P1"),
                    "reason": res.escalation_payload.get("reason", "")
                }
                output["prepared_action_id"] = action_id
                
            return output

        elif tool_name == "prepare_escalation":
            ticket_id = args.get("ticket_id", "").strip().upper()
            priority = args.get("priority", "P1")
            reason = args.get("reason", "")
            payload = {
                "ticket_id": ticket_id,
                "priority": priority,
                "reason": reason,
                "action": "ESCALATE_TICKET"
            }
            action_id = self.action_gateway.prepare(context, payload)
            self.collected_state["pending_action"] = {
                "action_id": action_id,
                "type": "ESCALATE_TICKET",
                "ticket_id": ticket_id,
                "priority": priority,
                "reason": reason
            }
            return {
                "action_id": action_id,
                "status": "PREPARED",
                "requires_human_confirmation": True
            }

        else:
            return {"error": f"Unknown tool '{tool_name}'"}
