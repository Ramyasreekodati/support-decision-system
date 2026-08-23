# ParcelPilot AI Support & Decision System

## What problem does it solve?
ParcelPilot is an AI support decision system designed to resolve Level 1 and Level 2 inquiries involving cancellation fees, service credits, SLA tracking, and proactive operational monitoring for B2B logistics clients (Northstar Logistics, LumenWorks, Beacon Retail, Axis Labs). The system reduces human effort by autonomously answering policy questions, identifying emerging queue risks, and staging ticket actions, while strictly delegating calculations and security checks to deterministic logic.

## How does it work?
The agent uses a hybrid architecture:
1. **The LLM Tool Agent** extracts user intent, translates unstructured queries into structured arguments, and orchestrates a sequence of 10 distinct tools:
   - `get_order`: Verified order facts with tenant isolation.
   - `get_ticket`: Verified support tickets and metrics.
   - `search_documents`: Retrieves current policies and customer agreements (filters deprecated v2).
   - `evaluate_cancellation`: Deterministic fee calculation and contract override enforcement.
   - `evaluate_service_credit`: Delay attribution and credit qualification.
   - `evaluate_sla`: Timezone-aware SLA countdown and breach verification.
   - `prepare_escalation`: Stages P1 escalation proposals with human confirmation.
   - `prepare_ticket_update`: Stages status/comment updates.
   - `prepare_followup_task`: Stages carrier dispute / billing tasks.
   - `get_proactive_insights`: Scans open queues for systemic risks and clusters.
2. **Deterministic Rules & Data Stores** execute all critical business logic, security validations, SLA calculations, and database retrieval.

The LLM is explicitly forbidden from fabricating numbers, overriding SLAs, bypassing user authorization, or mutating backend data directly.

## Key System Capabilities
* **Data-Layer Tenant Isolation:** Access control is enforced in `OperationalDataStore` via `is_authorized()`, raising `PermissionError` before any prompt, document, or calculation is triggered.
* **Legal Precedence Hierarchy:** Customer contracts (e.g. Northstar Agreement) strictly override general SOPs; deprecated policies are automatically excluded.
* **Transparent Uncertainty (`UNKNOWN`):** Missing timestamps or conflicting carrier reports surface as `UNKNOWN` with explicit limitation notes.
* **Human-in-the-Loop Action Gateway:** Actions are staged as `PREPARED` and executed only after explicit human confirmation with live 4-point revalidation (Auth, Record Access, Rule State, and SHA256 Payload Integrity).
* **Proactive Issue Detection (Problem 1):** Dedicated operations dashboard with real-time SLA countdowns, known-issue clustering (`KI-208`, `KI-211`), and cross-tenant outage alerts.
* **Dynamic Snapshot:** Reference timestamp is extracted from the Excel `README` sheet (`2026-08-16 11:00 Asia/Kolkata`).

## How do I run it?
1. **Clone the repository.**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the Streamlit application:**
   ```bash
   streamlit run app.py
   ```

## How do I test it?
To execute the comprehensive unit, integration, and end-to-end test suite:
```bash
pytest tests/
```

## Documentation Deliverables
- [`Architecture_Note.md`](Architecture_Note.md) — Technical architecture, tool schemas, data handling, and trade-offs.
- [`Product_Note.md`](Product_Note.md) — Problem 1 & Problem 2 implementation, product roadmap, and success metrics.
- [`Demo_Script.md`](Demo_Script.md) — Step-by-step 5-minute video walkthrough script.
