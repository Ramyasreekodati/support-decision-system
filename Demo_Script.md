# ParcelPilot AI Support Agent — 5-Minute Video Demo Script

## 1. Introduction & Architecture (0:00 - 1:00)
* **Opening:** *"Hello! This is the ParcelPilot AI Support Decision System built for the CalQuity assessment."*
* **The Problem:** *"B2B logistics support teams handle high-stakes customer inquiries with complex contract overrides, strict SLA deadlines, and monetary credits. An unconstrained chatbot risks hallucinations, data leaks, and compliance errors."*
* **The Solution Architecture:** *"We built a hybrid architecture: Google Gemini tool calling powers the reasoning and multi-step tool selection, while deterministic Python domain engines execute all calculations, policy hierarchy checks, and tenant isolation. The Streamlit UI sits on top as a thin client."*

---

## 2. Scenario 1: Policy Hierarchy & Contract Overrides (1:00 - 1:50)
* **Setup:** In the sidebar, select `Active Role: Support Admin` (Full Access).
* **Action:** Click the suggested demo prompt or type: *"Can Northstar cancel ORD-1001 without a cancellation fee?"*
* **What to highlight in UI:**
  * **Decision:** `CANCELLATION_ALLOWED` with Fee `₹0`.
  * **Agent Activity:** Point out the live tool trace (`get_order` → `search_documents` → `evaluate_cancellation`).
  * **Evidence Badges:** Point out the purple badge `CUSTOMER_SPECIFIC (Overrides Standard Policy)` citing `05_Northstar_Logistics_Enterprise_Agreement.pdf` overriding the standard ₹250 SOP fee.

---

## 3. Scenario 2: Uncertainty & Missing Fact Transparency (1:50 - 2:40)
* **Action:** Click or ask: *"Is ORD-2001 eligible for a service credit?"*
* **What to highlight in UI:**
  * **Decision:** `⚠️ UNKNOWN`.
  * **Explanation:** Show the **Operational Limitations** banner. Emphasize: *"The dataset is missing `pickup_actual_at`. The SOP strictly forbids promising credit when pickup timing is unrecorded. Instead of guessing, the system refuses to speculate and flags the missing field."*

---

## 4. Scenario 3: SLA Breach & Human-in-the-Loop Action Gateway (2:40 - 3:50)
* **Action:** Ask: *"What is the SLA status for TKT-501?"*
* **What to highlight in UI:**
  * **Decision:** `🚨 DEADLINE_ELAPSED` (15-minute P1 target elapsed at 2026-08-16 09:15 IST).
  * **Action Gateway Card:** Show the yellow **Action Requires Human Confirmation** card for `act_1`.
  * **Security Boundary:** *"The LLM does NOT have authority to mutate ticket states. It can only stage a `PREPARED` action."*
  * **Execution:** Click **[ Approve & Execute ]**.
  * **4-Point Live Revalidation:** Show the green JSON verification output confirming all 4 checks passed (`authorization`, `record_access`, `rule_state`, `payload_integrity` via SHA256 hash).

---

## 5. Scenario 4: Data-Layer Tenant Isolation (3:50 - 4:30)
* **Setup:** In the sidebar, switch `Active Role: Customer` and select `ACCT-002 — LumenWorks Inc.`
* **Action:** Ask: *"Can LumenWorks view Northstar's order ORD-1001?"*
* **What to highlight in UI:**
  * **Result:** Red `Access Denied` card.
  * **Security Proof:** *"Access control is enforced at the data store layer via `is_authorized()`, raising `PermissionError` before any prompt, rule engine, or document is reached."*

---

## 6. Conclusion & Product Vision (4:30 - 5:00)
* **Summary:** *"ParcelPilot delivers deterministic safety, cryptographic action governance, transparent evidence citations, and genuine tool-calling LLM reasoning."*
* **Submission Deliverables:** *"Repository includes clean modular architecture (`src/`), complete unit/e2e test suites (`tests/`), `Architecture_Note.md`, `Product_Note.md`, and `README.md`."*
