# Architecture Note: ParcelPilot Support System

## 1. Problem Context
B2B logistics support teams handle high-stakes customer inquiries involving strict contract terms, SLA breaches, and monetary credits. While LLMs are adept at natural-language understanding, relying on an unconstrained LLM for enterprise calculations or policy enforcement introduces risks of hallucinations, prompt injections, and compliance failures.

## 2. Core Architectural Philosophy
Our architecture enforces strict separation of concerns:
> **The LLM decides *what to investigate* (tool selection and argument parsing); deterministic, auditable domain engines decide *what the evidence means* (policy rules, data queries, proactive clustering, and actions). Streamlit serves strictly as a thin presentation and demonstration client.**

```
                         USER / EVALUATOR
                                │
                                ▼
                     ┌─────────────────────┐
                     │ Streamlit Thin UI   │  (app.py - Chat & Proactive Dashboard)
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │    Agent Service    │  (src/agent/agent_service.py)
                     │ ┌─────────────────┐ │
                     │ │ Live Gemini     │ │  (Tool-calling bounded reasoning loop)
                     │ │ LLM Agent       │ │
                     │ └─────────────────┘ │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │   Tool Dispatcher   │  (src/tools/dispatcher.py)
                     └──────────┬──────────┘
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Data Store   │        │ Document     │        │ Domain Engine│
│ (src/data/)  │        │ Store        │        │ (src/domain/)│
│ - get_order  │        │ - search_docs│        │ - evaluate_* │
│ - get_ticket │        │ (filters v2) │        │ - proactive  │
└──────┬───────┘        └──────────────┘        └──────┬───────┘
       │                                               │
       ▼                                               ▼ (if mutation required)
┌──────────────┐                                ┌──────────────┐
│ Security     │                                │ ActionGateway│ (src/actions/)
│ (src/sec/)   │                                │ 1. PREPARE   │
│ - is_auth()  │                                │ 2. CONFIRM   │
│              │                                │ 3. REVALIDATE│
│              │                                │ 4. EXECUTE   │
└──────────────┘                                └──────────────┘
```

## 3. Agent & Tool Design (10 Distinct Tools)
1. `get_order`: Queries order facts (order status, timestamps, fees, fault flags) from `OperationalDataStore`.
2. `get_ticket`: Queries support tickets (account, priority, created time, response time).
3. `search_documents`: Retrieves current, non-deprecated policies and agreements from `DocumentStore`.
4. `evaluate_cancellation`: Deterministic engine for cancellation eligibility and fees.
5. `evaluate_service_credit`: Deterministic engine for delay calculation and credit limits.
6. `evaluate_sla`: Timezone-aware engine for SLA response deadlines and breach verification.
7. `prepare_escalation`: Creates idempotent, human-gated escalation proposals.
8. `prepare_ticket_update`: Stages status and note modifications on existing tickets.
9. `prepare_followup_task`: Stages operational and carrier dispute follow-up tasks.
10. `get_proactive_insights`: Scans open tickets for SLA risks, known issue clusters, and systemic anomalies.

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
   - Rule State (re-evaluation of breach/validity condition)
   - Payload Integrity (tampering check via SHA256)
4. **EXECUTE:** Transitions to `EXECUTED` and appends to the immutable execution ledger. Duplicate calls return `ALREADY_EXECUTED` (idempotent).

## 7. Dynamic Reference Time
The system dynamically extracts the reference snapshot time from row 1 of the Excel `README` sheet (`2026-08-16 11:00 Asia/Kolkata`), eliminating static date assumptions.

## 8. Proactive Issue Detection (Problem 1)
Implemented `ProactiveEngine` to continuously monitor operational queues relative to the dataset snapshot timestamp:
- **SLA Watchlist:** Detects breached tickets (`TKT-501`) and approaching deadlines.
- **Known Issue Clustering:** Groups tickets by operational signatures (`KI-208` CSV batch failures, `KI-211` SwiftShip pickup webhook lag, global HTTP 500 outages).

## 9. Verification & Testing
18 automated test suites verify all system boundaries:
- Unit: ActionGateway lifecycle, Cancellation engine, Service credit engine, SLA engine, Proactive issue detection engine.
- Integration: Tool dispatcher contracts, multi-tool pipelines, security rejection.
- E2E: End-to-end user workflows, human approval cycles, tenant scoping.
