import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.security.authorization import SecurityContext
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.actions.action_gateway import ActionGateway
from src.tools.dispatcher import ToolDispatcher
from src.agent.providers import GeminiProvider, LLMResponse

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 8

class LiveToolCallingAgent:
    def __init__(self, dispatcher: ToolDispatcher, provider: Optional[GeminiProvider] = None):
        self.dispatcher = dispatcher
        self.provider = provider or GeminiProvider()

    def execute_turn(self, prompt: str, context: SecurityContext) -> Dict[str, Any]:
        self.dispatcher.collected_state = {}
        schemas = self.dispatcher.get_schemas()
        
        system_instruction = (
            "You are the ParcelPilot AI Support Agent. Assist support staff and customers with order cancellations, "
            "service credit inquiries, and SLA escalations. Select and invoke appropriate tools to look up facts "
            "and compute rule decisions. NEVER fabricate fees, deadlines, or policy terms yourself. Always cite the exact evidence."
        )

        messages = [
            {"role": "user", "content": f"{system_instruction}\n\nUser Request: {prompt}"}
        ]

        tool_trace = []
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1
            response: LLMResponse = self.provider.generate(messages, tools=schemas)

            if not response.tool_calls:
                return self._build_final_response(response.content, tool_trace, context)

            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [{"name": tc.name, "args": tc.args} for tc in response.tool_calls]
            })

            for call in response.tool_calls:
                trace_entry = {
                    "tool": call.name,
                    "input": call.args,
                    "status": "RUNNING",
                    "output": None
                }

                try:
                    result = self.dispatcher.dispatch(call.name, call.args, context)
                    trace_entry["status"] = "SUCCESS"
                    trace_entry["output"] = result
                    tool_trace.append(trace_entry)

                    messages.append({
                        "role": "tool",
                        "name": call.name,
                        "content": json.dumps(result)
                    })
                except PermissionError:
                    trace_entry["status"] = "UNAUTHORIZED"
                    tool_trace.append(trace_entry)
                    entity_id = call.args.get("order_id") or call.args.get("ticket_id") or "UNKNOWN"
                    return {
                        "Error": "UNAUTHORIZED",
                        "Requested": entity_id,
                        "Scope": list(context.account_scope)[0] if context.account_scope else "NONE",
                        "tool_trace": tool_trace,
                        "Reason": "The operational data layer rejected the request before business rules were evaluated.\n\n✓ No data exposed\n✓ No documents exposed\n✓ No rule evaluation performed"
                    }
                except Exception as e:
                    trace_entry["status"] = "FAILED"
                    trace_entry["output"] = str(e)
                    tool_trace.append(trace_entry)
                    messages.append({
                        "role": "tool",
                        "name": call.name,
                        "content": json.dumps({"error": str(e)})
                    })

        return self._build_final_response("Reached maximum tool execution limit.", tool_trace, context)

    def _build_final_response(self, text: Optional[str], tool_trace: List[Dict[str, Any]], context: SecurityContext) -> Dict[str, Any]:
        state = self.dispatcher.collected_state
        explanation: Dict[str, Any] = {"Text": text, "tool_trace": tool_trace, "Mode": "LIVE_GEMINI_AGENT"}

        if "decision_result" in state:
            res = state["decision_result"]
            explanation["Decision"] = res.decision
            fee_str = f"₹{res.amount}" if res.amount is not None else "₹0"
            explanation["Reason"] = f"Cancellation fee: {fee_str} based on rule {res.applicable_rule}."
            explanation["Evidence"] = res.evidence
            explanation["Limitations"] = res.limitations
            explanation["Intent"] = "cancellation"

        elif "service_credit_result" in state:
            res = state["service_credit_result"]
            explanation["Decision"] = res.eligibility
            explanation["Reason"] = f"Credit amount: {res.credit_amount} based on {res.applicable_rule}."
            explanation["Evidence"] = res.evidence
            explanation["Limitations"] = res.limitations
            explanation["Intent"] = "service_credit"

        elif "sla_result" in state:
            res = state["sla_result"]
            explanation["Decision"] = res.state
            explanation["Reason"] = f"Target: {res.target_minutes}m, Deadline: {res.deadline}, Escalation: {res.escalation_requirement}."
            explanation["Evidence"] = res.evidence
            explanation["Limitations"] = res.limitations
            explanation["Intent"] = "sla"
            explanation["SLA_Details"] = {
                "Ticket": state.get("entity_id", "UNKNOWN"),
                "Priority": "P1",
                "Target": f"{res.target_minutes} minutes",
                "Actual_Response": f"{res.actual_response_time or 'N/A'} minutes"
            }

        if "pending_action" in state:
            explanation["Action"] = {
                "status": "PREPARED",
                "action_id": state["pending_action"]["action_id"],
                "type": state["pending_action"]["type"],
                "ticket_id": state["pending_action"]["ticket_id"],
                "priority": state["pending_action"]["priority"],
                "reason": state["pending_action"]["reason"]
            }
        else:
            explanation["Action"] = None

        explanation["Context"] = {
            "Role": context.role,
            "Scope": list(context.account_scope)[0] if context.account_scope else "NONE",
            "Entity": state.get("entity_id", "N/A"),
            "Snapshot": context.snapshot_time.strftime("%d %b %Y %H:%M %Z")
        }
        return explanation


class DeterministicToolEngine:
    def __init__(self, dispatcher: ToolDispatcher):
        self.dispatcher = dispatcher

    def execute_turn(self, prompt: str, context: SecurityContext) -> Dict[str, Any]:
        self.dispatcher.collected_state = {}
        user_lower = prompt.lower()
        
        ord_match = re.search(r'\b(ORD-\d+)\b', prompt, re.IGNORECASE)
        tkt_match = re.search(r'\b(TKT-\d+)\b', prompt, re.IGNORECASE)
        
        order_id = ord_match.group(1).upper() if ord_match else None
        ticket_id = tkt_match.group(1).upper() if tkt_match else None
        
        tool_trace = []

        try:
            if ("cancel" in user_lower or (order_id and "credit" not in user_lower and "delay" not in user_lower and "sla" not in user_lower and not ticket_id)):
                target_ord = order_id or "ORD-1001"
                self._run_tool("get_order", {"order_id": target_ord}, context, tool_trace)
                self._run_tool("search_documents", {"query": "cancellation policy"}, context, tool_trace)
                self._run_tool("evaluate_cancellation", {"order_id": target_ord}, context, tool_trace)
                return self._build_deterministic_response(tool_trace, context, intent="cancellation", entity_id=target_ord)

            elif ("credit" in user_lower or "delay" in user_lower or "late" in user_lower or "refund" in user_lower) and order_id:
                self._run_tool("get_order", {"order_id": order_id}, context, tool_trace)
                self._run_tool("search_documents", {"query": "service credit SOP"}, context, tool_trace)
                self._run_tool("evaluate_service_credit", {"order_id": order_id}, context, tool_trace)
                return self._build_deterministic_response(tool_trace, context, intent="service_credit", entity_id=order_id)

            elif ("sla" in user_lower or "p1" in user_lower or "escalat" in user_lower or "breach" in user_lower or "response" in user_lower) and (ticket_id or "tkt" in user_lower):
                target_tkt = ticket_id or "TKT-501"
                self._run_tool("get_ticket", {"ticket_id": target_tkt}, context, tool_trace)
                self._run_tool("search_documents", {"query": "SLA policy"}, context, tool_trace)
                self._run_tool("evaluate_sla", {"ticket_id": target_tkt}, context, tool_trace)
                return self._build_deterministic_response(tool_trace, context, intent="sla", entity_id=target_tkt)

            elif order_id:
                self._run_tool("get_order", {"order_id": order_id}, context, tool_trace)
                self._run_tool("search_documents", {"query": "cancellation"}, context, tool_trace)
                self._run_tool("evaluate_cancellation", {"order_id": order_id}, context, tool_trace)
                return self._build_deterministic_response(tool_trace, context, intent="cancellation", entity_id=order_id)

            else:
                return {"Text": "I'm sorry, I can only assist with cancellations, service credits, and SLAs.", "Mode": "OFFLINE_DETERMINISTIC_TEST_ENGINE"}

        except PermissionError:
            entity_id = order_id or ticket_id or "UNKNOWN"
            return {
                "Error": "UNAUTHORIZED",
                "Requested": entity_id,
                "Scope": list(context.account_scope)[0] if context.account_scope else "NONE",
                "tool_trace": tool_trace,
                "Reason": "The operational data layer rejected the request before business rules were evaluated.\n\n✓ No data exposed\n✓ No documents exposed\n✓ No rule evaluation performed",
                "Mode": "OFFLINE_DETERMINISTIC_TEST_ENGINE"
            }

    def _run_tool(self, tool_name: str, args: Dict[str, Any], context: SecurityContext, tool_trace: List[Dict[str, Any]]):
        res = self.dispatcher.dispatch(tool_name, args, context)
        tool_trace.append({
            "tool": tool_name,
            "input": args,
            "status": "SUCCESS",
            "output": res
        })

    def _build_deterministic_response(self, tool_trace: List[Dict[str, Any]], context: SecurityContext, intent: str, entity_id: str) -> Dict[str, Any]:
        state = self.dispatcher.collected_state
        explanation: Dict[str, Any] = {"tool_trace": tool_trace, "Mode": "OFFLINE_DETERMINISTIC_TEST_ENGINE", "Intent": intent}

        if "decision_result" in state:
            res = state["decision_result"]
            explanation["Decision"] = res.decision
            fee_str = f"₹{res.amount}" if res.amount is not None else "₹0"
            explanation["Reason"] = f"Fee: {fee_str} · Rule: {res.applicable_rule}"
            explanation["Evidence"] = res.evidence
            explanation["Limitations"] = res.limitations
            explanation["ConflictDetected"] = False

        elif "service_credit_result" in state:
            res = state["service_credit_result"]
            explanation["Decision"] = res.eligibility
            explanation["Reason"] = f"Credit amount: {res.credit_amount} · Rule: {res.applicable_rule}"
            explanation["Evidence"] = res.evidence
            explanation["Limitations"] = res.limitations
            explanation["ConflictDetected"] = getattr(res, "conflict_detected", False)

        elif "sla_result" in state:
            res = state["sla_result"]
            explanation["Decision"] = res.state
            explanation["Reason"] = f"Actual response: {res.actual_response_time or 'N/A'} min · Deadline: {res.deadline} · Escalation: {res.escalation_requirement}"
            explanation["Evidence"] = res.evidence
            explanation["Limitations"] = res.limitations
            explanation["ConflictDetected"] = False
            explanation["SLA_Details"] = {
                "Ticket": entity_id,
                "Priority": "P1",
                "Target": f"{res.target_minutes} minutes",
                "Actual_Response": f"{res.actual_response_time or 'N/A'} minutes"
            }

        if "pending_action" in state:
            explanation["Action"] = {
                "status": "PREPARED",
                "action_id": state["pending_action"]["action_id"],
                "type": state["pending_action"]["type"],
                "ticket_id": state["pending_action"]["ticket_id"],
                "priority": state["pending_action"]["priority"],
                "reason": state["pending_action"]["reason"]
            }
        else:
            explanation["Action"] = None

        explanation["Context"] = {
            "Role": context.role,
            "Scope": list(context.account_scope)[0] if context.account_scope else "NONE",
            "Entity": entity_id,
            "Snapshot": context.snapshot_time.strftime("%d %b %Y %H:%M %Z")
        }
        return explanation


class AgentService:
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, action_gateway: ActionGateway):
        self.dispatcher = ToolDispatcher(data_store, doc_store, action_gateway)
        self.gemini_provider = GeminiProvider()
        self.live_agent = LiveToolCallingAgent(self.dispatcher, self.gemini_provider)
        self.offline_engine = DeterministicToolEngine(self.dispatcher)

    @property
    def is_live_mode(self) -> bool:
        return self.gemini_provider.is_available()

    def process_message_structured(self, message: str, context: SecurityContext) -> Dict[str, Any]:
        if self.is_live_mode:
            logger.info("Executing via LiveToolCallingAgent (Gemini)")
            return self.live_agent.execute_turn(message, context)
        else:
            logger.info("Executing via DeterministicToolEngine (Offline Mode)")
            return self.offline_engine.execute_turn(message, context)

    def process_message(self, message: str, context: SecurityContext) -> str:
        res = self.process_message_structured(message, context)
        if "Text" in res and len(res) == 1:
            return res["Text"]
        if "Error" in res:
            return f"{res['Error']}: You do not have permission to access this record."

        lines = []
        if "Decision" in res: lines.append(f"Decision: {res['Decision']}")
        if "Reason" in res: lines.append(f"Reason: {res['Reason']}")
        if res.get("Evidence"): lines.append(f"Evidence: {', '.join([e['source'] if isinstance(e, dict) else str(e) for e in res['Evidence']])}")
        else: lines.append("Evidence: ")

        if res.get("Limitations"):
            lines.append(f"Limitations: {' | '.join(res['Limitations'])}")

        if res.get("Action"):
            lines.append(f"Action: PREPARED. Awaiting human confirmation for Action ID: {res['Action']['action_id']}")

        return "\n".join(lines)

    def get_snapshot_time(self) -> datetime:
        return self.dispatcher.data_store.get_snapshot_time()

    def approve_action(self, action_id: str, context: SecurityContext) -> Dict[str, Any]:
        return self.dispatcher.action_gateway.approve(action_id, context)

    def reject_action(self, action_id: str) -> Dict[str, Any]:
        return self.dispatcher.action_gateway.reject(action_id)

_service_instance = None

def get_agent_service() -> AgentService:
    global _service_instance
    if _service_instance is None:
        data_store = OperationalDataStore()
        doc_store = DocumentStore()
        action_gateway = ActionGateway(data_store, doc_store)
        _service_instance = AgentService(data_store, doc_store, action_gateway)
    return _service_instance
