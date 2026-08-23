# ParcelPilot AI Support Agent

## What problem does it solve?
ParcelPilot is an AI support agent designed to resolve Level 1 and Level 2 customer inquiries involving cancellation fees, service credits, and SLA tracking for B2B logistics clients (Northstar and LumenWorks). The system reduces human effort by autonomously answering policy questions and preparing ticket escalations, but strictly delegates execution and critical security checks to deterministic logic.

## How does it work?
The agent uses a hybrid architecture:
1. **The LLM** extracts user intent, translates unstructured queries into structured arguments, and formulates final human-readable answers.
2. **Deterministic Rules** execute all critical business logic, security validations, SLA calculations, and database retrieval.

The LLM is explicitly forbidden from making numerical calculations, altering SLA results, bypassing user authorization, or mutating the backend data. 

## Why is it trustworthy?
Trust is built on rigid separation of concerns:
* **Authorization is strictly enforced** by a mocked Security Context layer. Users can only retrieve orders and policies applicable to their specific account scope.
* **Source precedence is hardcoded**. When an enterprise agreement overrides standard operating procedures, the deterministic engine enforces the override—not the LLM.
* **Uncertainty is highlighted, not fabricated.** If a record lacks a pickup time, the system will not invent one. It outputs `UNKNOWN` and surfaces the specific limitation.
* **Escalations are sandboxed.** The agent prepares SLA escalations, but a human must definitively approve them before they are executed. Actions are idempotent and cryptographically revalidated at execution time.

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
To execute the complete 48-test deterministic verification suite:
```bash
# Windows/PowerShell
$env:PYTHONPATH="src"; python -m unittest src.phase2_verification src.phase3 src.phase4 src.phase5 e2e_tests

# Linux/Mac
PYTHONPATH="src" python -m unittest src.phase2_verification src.phase3 src.phase4 src.phase5 e2e_tests
```

## What are its limitations?
- **Authentication is mocked**: True OAuth/OIDC identity validation is stubbed via Streamlit's sidebar for assessment purposes.
- **Missing Data Fields**: Historical service-credit ledgers and `first_response_at` timestamps are missing from the assessment dataset. As a result, the system can determine that a `DEADLINE_ELAPSED` occurred, but cannot verify an actual SLA `BREACHED` without a timestamp.
- **Business Hours**: The provided documents do not define the specific corporate holiday or business hour calendar, so 24x7 calculations are used as a fallback. 
- **Mock LLM**: Live Google Gemini integration was tested with a MockLLM due to lack of authenticated API credentials in this sandbox.
