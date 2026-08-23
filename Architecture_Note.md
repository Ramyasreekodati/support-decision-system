# Architecture Note: ParcelPilot Support System

## 1. Problem Context
B2B logistics support teams handle high-stakes customer inquiries involving strict contract terms, SLA breaches, and monetary credits. While LLMs are adept at natural-language understanding, relying on an unconstrained LLM for enterprise calculations or policy enforcement introduces risks of hallucinations, prompt injections, and compliance failures.

## 2. Core Architectural Philosophy
Our architecture enforces strict separation of concerns:
> **The LLM decides *what to investigate* (tool selection and argument parsing); deterministic, auditable components decide *what the evidence means* (policy rules, data queries, and actions).**

```
User Prompt (Natural Language)
               │
               ▼
┌──────────────────────────────────────────────┐
│        MockToolCallingAgent (Phase 5)        │
│  - Extracts Intent                           │
│  - Extracts Entities (e.g. ORD-1001, TKT-501)│
│  - Selects Sequential Tool Pipeline          │
└──────────────────────┬───────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌──────────────┐┌──────────────┐┌──────────────┐
│ Structured   ││ Document     ││ Rule Engines │
│ Data Store   ││ Store (Docs) ││ (Phases 2-4) │
│ - get_order  ││ - search_docs││ - evaluate_* │
│ - get_ticket ││              ││              │
└──────────────┘└──────────────┘└──────┬───────┘
                                       │ (if escalation required)
                                       ▼
                       ┌───────────────────────────────┐
                       │     Action Gateway (Phase 4)  │
                       │ 1. PREPARE Action             │
                       │ 2. AWAIT Human Confirmation   │
                       │ 3. REVALIDATE (Auth/Rule/Hash)│
                       │ 4. EXECUTE & Log Audit Trail  │
                       └───────────────────────────────┘
```

## 3. Agent & Tool Design (7 Distinct Tools)
1. `get_order`: Queries order facts (order status, timestamps, fees, fault flags) from `OperationalDataStore`.
2. `get_ticket`: Queries support tickets (account, priority, created time, response time).
3. `search_documents`: Retrieves current, non-deprecated policies and agreements from `DocumentStore`.
4. `evaluate_cancellation`: Deterministic engine for cancellation eligibility and fees.
5. `evaluate_service_credit`: Deterministic engine for delay calculation and credit limits.
6. `evaluate_sla`: Timezone-aware engine for SLA response deadlines and breach verification.
7. `prepare_escalation`: Creates idempotent, human-gated escalation proposals.

## 4. Document Hierarchy & Source Precedence
When an enterprise agreement contradicts a standard policy, the deterministic engine enforces strict legal hierarchy:
$$\text{Customer Agreement (Enterprise Tier)} > \text{General SOP v4} > \text{Deprecated Policies (Filtered)}$$
Every decision explicitly tags the evidence source and authority level (`CUSTOMER_SPECIFIC` vs `GENERAL_POLICY`).

## 5. Security & Access Control
Access control is enforced **strictly at the data and tool layer**, not via model prompts:
- `is_authorized(context, account_id)` validates tenant isolation before returning order/ticket data.
- Unauthorized cross-account access immediately raises `PermissionError`, terminating the tool chain before business rules run or data is exposed.

## 6. Action Lifecycle & Human-in-the-Loop
No state-changing mutation can occur autonomously. The lifecycle requires:
1. **PREPARE:** Action created in `ActionState.PREPARED` with a unique ID and payload hash.
2. **CONFIRM:** Human agent reviews the proposed action in the UI.
3. **REVALIDATE:** Live 4-point verification before execution:
   - Authorization (active `SecurityContext`)
   - Record Access (entity existence)
   - Rule State (re-evaluation of breach condition)
   - Payload Integrity (tampering check)
4. **EXECUTE:** Transitions to `EXECUTED` and appends to the immutable execution ledger. Duplicate calls return `ALREADY_EXECUTED` (idempotent).

## 7. Dynamic Reference Time
The system dynamically extracts the reference snapshot time from row 1 of the Excel `README` sheet (`2026-08-16 11:00 Asia/Kolkata`), eliminating static date assumptions.

## 8. Verification & Testing
51 automated test cases verify every boundary:
- Phase 2 (17 tests): Cancellation rules, override precedence, missing agreement handling.
- Phase 3 (13 tests): Service credits, fault conflicts, missing pickup times.
- Phase 4 (11 tests): SLA deadlines, ActionGateway lifecycle, security revalidation.
- Phase 5 (2 tests): Agent tool selection, multi-tool pipelines, injection resistance.
- E2E (8 tests): End-to-end user workflows and human approval flows.
