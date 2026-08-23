# ParcelPilot AI Support Agent

## What problem does it solve?
ParcelPilot is an AI support agent designed to resolve Level 1 and Level 2 customer inquiries involving cancellation fees, service credits, and SLA tracking for B2B logistics clients (Northstar and LumenWorks). The system reduces human effort by autonomously answering policy questions and preparing ticket escalations, but strictly delegates execution and critical security checks to deterministic logic.

## How does it work?
The agent uses a hybrid architecture:
1. **The LLM Tool Agent** extracts user intent, translates unstructured queries into structured arguments, and chooses a sequence of distinct tools (`get_order`, `get_ticket`, `search_documents`, `evaluate_cancellation`, `evaluate_service_credit`, `evaluate_sla`, `prepare_escalation`).
2. **Deterministic Rules & Data Stores** execute all critical business logic, security validations, SLA calculations, and database retrieval.

The LLM is explicitly forbidden from making numerical calculations, altering SLA results, bypassing user authorization, or mutating backend data. 

## Why is it trustworthy?
Trust is built on rigid separation of concerns:
* **Authorization is strictly enforced** at the data/tool layer. Users can only retrieve orders, tickets, and policies applicable to their specific account scope.
* **Source precedence is hardcoded**. When an enterprise agreement overrides standard operating procedures, the deterministic engine enforces the override—not the LLM.
* **Uncertainty is highlighted, not fabricated.** If a record lacks a pickup time or contains conflicting fault reports, the system will not invent an answer. It outputs `UNKNOWN` and surfaces the specific limitation.
* **Escalations are sandboxed.** The agent prepares SLA escalations, but a human must definitively approve them before they are executed. Actions are idempotent and live-revalidated at execution time.
* **Dynamic Snapshot.** Reference time is parsed dynamically from the Excel workbook `README` sheet (`2026-08-16 11:00 Asia/Kolkata`).

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
4. **Run the UI simulation script (CLI):**
   ```bash
   python ui_simulation.py
   ```

## How do I test it?
To execute the complete 51-test deterministic verification suite:
```bash
# Windows/PowerShell
$env:PYTHONPATH="src"; python -m unittest src.phase2_verification src.phase3 src.phase4 src.phase5 e2e_tests

# Linux/Mac
PYTHONPATH="src" python -m unittest src.phase2_verification src.phase3 src.phase4 src.phase5 e2e_tests
```

## What are its limitations?
- **Authentication is mocked**: True OAuth/OIDC identity validation is stubbed via Streamlit's sidebar for assessment purposes.
- **Missing Data Fields**: Historical service-credit ledgers and `first_response_at` timestamps are missing for some tickets in the assessment dataset. As a result, the system determines that a `DEADLINE_ELAPSED` occurred, but cannot verify an actual SLA `BREACHED` without a timestamp.
- **Business Hours**: The provided documents do not define the specific corporate holiday or business hour calendar, so 24x7 calculations are used as a fallback for non-24x7 plans (`BUSINESS_TIME_CALCULATION_UNSPECIFIED`).
