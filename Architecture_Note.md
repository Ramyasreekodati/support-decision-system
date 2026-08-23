# Architecture Note: ParcelPilot Support System

## The Problem
Support agents spend significant time answering policy questions and calculating service credits across various enterprise agreements. While LLMs excel at intent extraction and communication, they struggle with strict deterministic arithmetic, enterprise access controls, and legally binding document precedence.

## Design Principles
This architecture operates on a core tenet: **The LLM determines what needs to be investigated; deterministic components determine what the trusted evidence means.**

## Source Precedence
When an enterprise agreement (e.g., Northstar) overrides standard operating procedures (e.g., General Cancellation SOP), the deterministic engine strictly enforces the override. The LLM cannot hallucinate terms or ignore explicit overrides because it is never given raw control over policy evaluation.

## Security Model
The system enforces rigorous, multi-layered authorization:
- **Customer:** Restricted to their exact account scope (e.g., LumenWorks).
- **Support Agent:** Restricted to explicitly assigned accounts.
- **Support Admin:** Authorized for ALL scopes.
The UI merely mocks the identity token. All true validation occurs cryptographically within the `OperationalDataStore` and `ActionGateway`, ensuring that prompt injection cannot bypass tenant isolation.

## Deterministic Rule Engine
Complex calculations—such as cancellation fees, SLA response targets, and service credit eligibility—are executed entirely via Python-based Rule Engines. The LLM passes raw operational facts to these engines, and the engines return a structured decision payload.

## Retrieval Model
A `DocumentStore` securely retrieves PDFs based on the user's role and account context. It additionally filters out deprecated documents based on the `snapshot_time`, ensuring the LLM is only exposed to current, active policies.

## LLM Responsibilities
1. Extract intent from the user query (e.g., "Cancel order 1001" -> `type: CANCELLATION`).
2. Synthesize the structured output of the deterministic engines into a conversational format.

## Action Lifecycle
The LLM cannot mutate state directly. Instead, it prepares actions in an idempotent sandbox.
1. **PREPARE:** The LLM requests an escalation.
2. **CONFIRM:** A human user manually reviews the request via the UI.
3. **REVALIDATE:** The backend revalidates the exact action payload against the user's current security context (preventing mid-flight authorization tampering).
4. **EXECUTE:** The action is finalized.

## Uncertainty Handling
The system does not fabricate missing data. If an order lacks an actual pickup time, the decision yields `UNKNOWN` and explicitly notes the limitation. If an SLA deadline has passed but a `first_response_at` timestamp is missing, it yields `DEADLINE_ELAPSED` instead of a verified `BREACHED`. 

## Testing Strategy
The architecture was verified using an adversarial `MockLLM` that intentionally attempted prompt injections, hallucinated calculations, ignored scopes, and manipulated states. 48 deterministic unit tests and 8 E2E simulation tests prove that the boundaries hold under attack.

## Trade-offs
To achieve absolute deterministic reliability, we traded away free-form LLM flexibility. The LLM must conform to the strict JSON constraints expected by the Action Gateway, meaning it cannot creatively devise custom workflows that haven't been engineered into the Rule Engine yet.
