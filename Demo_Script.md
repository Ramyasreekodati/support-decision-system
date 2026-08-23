# ParcelPilot AI Support & Decision System — 5-Minute Video Demo Script

## 1. Introduction & Architecture (0:00 - 0:50)
* **Opening:** *"Hello! This is the ParcelPilot Support and Decision System built for the CalQuity AI Engineer Assessment."*
* **The Problem:** *"B2B logistics operations teams deal with fragmented sources—tiered enterprise contracts, SLA penalty clauses, and messy real-world operational data. A simple chatbot introduces hallucinations and security risks."*
* **Our Architecture:** *"We built a hybrid system: LLM tool calling (Gemini) handles natural-language intent and multi-step tool orchestration, while deterministic domain engines execute mathematical rules, contract precedence, and data-layer access control. Streamlit serves as our thin client."*

---

## 2. Scenario 1: Policy Hierarchy & Contract Overrides (0:50 - 1:40)
* **Setup:** In the sidebar, select `Active Role: Support Admin` (Full Access).
* **Action:** Click the suggested demo query: *"Can Northstar cancel ORD-1001 without a cancellation fee?"*
* **What to highlight in UI:**
  * **Decision:** `CANCELLATION_ALLOWED` with Fee `₹0`.
  * **Agent Activity:** Expand tool trace showing `get_order` → `search_documents` → `evaluate_cancellation`.
  * **Evidence Badges:** Point out the purple badge `CUSTOMER_SPECIFIC (Overrides Standard Policy)` citing `05_Northstar_Logistics_Enterprise_Agreement.pdf` overriding the standard ₹250 fee in general SOP v4.

---

## 3. Scenario 2: Uncertainty & Missing Fact Transparency (1:40 - 2:25)
* **Action:** Click or ask: *"Is ORD-2001 eligible for a service credit?"*
* **What to highlight in UI:**
  * **Decision:** `⚠️ UNKNOWN`.
  * **Explanation:** Show the **Operational Limitations** banner. Emphasize: *"The dataset is missing `pickup_actual_at`. The SOP strictly forbids promising credit when pickup timing is unrecorded. Instead of guessing, the system refuses to speculate and flags the missing field."*

---

## 4. Scenario 3: SLA Breach & Human-in-the-Loop Action Gateway (2:25 - 3:20)
* **Action:** Ask: *"What is the SLA status for TKT-501?"*
* **What to highlight in UI:**
  * **Decision:** `🚨 DEADLINE_ELAPSED` (15-minute P1 target elapsed at 2026-08-16 09:15 IST).
  * **Action Gateway Card:** Show the amber **Action Requires Human Confirmation** card for `act_1`.
  * **Security Boundary:** *"The LLM does NOT have authority to mutate ticket states. It can only stage a `PREPARED` action."*
  * **Execution:** Click **[ Approve & Execute ]**.
  * **4-Point Live Revalidation:** Show the green JSON verification output confirming all 4 checks passed (`authorization`, `record_access`, `rule_state`, `payload_integrity` via SHA256 hash).

---

## 5. Scenario 4: Data-Layer Tenant Isolation (3:20 - 4:00)
* **Setup:** In the sidebar, switch `Active Role: Customer` and select `ACCT-002 — LumenWorks Inc.`
* **Action:** Ask: *"Can LumenWorks view Northstar's order ORD-1001?"*
* **What to highlight in UI:**
  * **Result:** Red `Access Denied` card.
  * **Security Proof:** *"Access control is enforced at the data store layer via `is_authorized()`, raising `PermissionError` before any prompt, rule engine, or document is reached."*

---

## 6. Scenario 5: Proactive Operations Dashboard (Problem 1) (4:00 - 4:40)
* **Action:** Click the top tab **"📊 Proactive Operations Dashboard (Problem 1)"**.
* **What to highlight in UI:**
  * **Top Metrics:** 5 Open Tickets, 1 SLA Breached, Active Issue Clusters.
  * **SLA Risk Watchlist:** Show `TKT-501` highlighted with `🚨 SLA BREACHED` and other tickets on track.
  * **Known Issue Clustering:** Point out `KI-208` (Bulk CSV Upload failures) and `KI-211` (SwiftShip pickup webhook delay), showing how the system clusters tickets and suggests immediate operational action.

---

## 7. Conclusion & Deliverables (4:40 - 5:00)
* **Summary:** *"ParcelPilot addresses both core client problems: reactive trust & reliability through deterministic governance, and proactive issue detection via operational clustering."*
* **Deliverables:** *"Codebase with 10 distinct tools, 18 automated test suites with 100% pass rate, `Architecture_Note.md`, `Product_Note.md`, and `README.md`."*
