# Product Note: ParcelPilot Support Decision System

## 1. Problem Context
B2B logistics operations teams manage high-value client contracts with complex contractual nuances, tiered cancellation penalties, and strict SLA deadlines. In high-volume support queues, manual contract lookup leads to high Mean Time to Resolution (MTTR), frequent billing disputes, and compliance breaches.

---

## 2. Additional Client Problems Addressed: Problem 1 & Problem 2

We implemented concrete solutions for **both** core client challenges:

### Problem 1: Proactive Issue Detection
Rather than remaining purely reactive, the system features an operational monitoring dashboard:
1. **Real-Time SLA Risk Watchlist:** Tracks open tickets relative to the frozen snapshot timestamp, automatically identifying breached tickets (`TKT-501`) and countdown risks.
2. **Known Issue Clustering:** Groups incoming tickets against operational defect definitions (`KI-208` CSV bulk upload failures, `KI-211` SwiftShip webhook sync delay, and platform-wide outages).
3. **Cross-Tenant Anomaly Detection:** Identifies systemic incidents impacting multiple enterprise accounts simultaneously.

### Problem 2: Trust & Reliability
1. **Deterministic Rule Enforcement:** Business logic (cancellation fees, delay attribution, SLA timers) is executed exclusively by auditable Python domain engines (`src/domain/`), preventing LLM hallucination.
2. **Explicit Evidence Provenance:** Every response outputs exact PDF citations classified by authority level:
   - `CUSTOMER_SPECIFIC (Overrides Standard Policy)` for enterprise contracts (e.g., Northstar Agreement).
   - `GENERAL_POLICY (Standard Precedence)` for baseline operating procedures (SOP v4).
3. **Transparent Handling of Missing Facts (`UNKNOWN`):** When critical data is missing (e.g., `pickup_actual_at` on order `ORD-2001` or undefined non-24x7 business hours), the system refuses to guess, explicitly returning `UNKNOWN` with limitation notes.
4. **Human-in-the-Loop Action Gateway:** The AI cannot mutate state directly. Actions (`ESCALATE_TICKET`, `UPDATE_TICKET`, `CREATE_TASK`) are staged as `PREPARED` proposals requiring human approval in the UI with live 4-point revalidation (Auth, Record Access, Live Rule State, and SHA256 Payload Hash integrity).
5. **Data-Layer Tenant Isolation:** Security boundaries are enforced in `OperationalDataStore` via `is_authorized()`, raising `PermissionError` before business rules or documents are accessed.

---

## 3. Product Roadmap: Future Development

1. **Dynamic Corporate Credit Ledgers:**
   - Integrate an external transactional ledger to track cumulative monthly service credits against the ₹5,000 corporate annual cap for Northstar.
2. **Calendar-Aware Business Hours Engine:**
   - Implement a configurable holiday and operating-hours calendar for Growth and Standard tiers (e.g., 9 AM - 6 PM IST on business days).
3. **Carrier Webhook Ingestion:**
   - Direct carrier API integrations (e.g., SwiftShip webhook listener) to refresh live order states automatically.

---

## 4. What Was Intentionally Left Out of the Submission

1. **Autonomous Mutation Authority:** We intentionally excluded autonomous execution tools from the LLM. Consequential mutations must be staged and confirmed by authorized human operators.
2. **Multi-Tenant Distributed Database Cluster:** We used Excel parsing with dynamic snapshot reconstruction to match the provided assessment data pack without introducing external cloud database dependencies.
3. **OAuth/SAML Provider Integration:** Authentication context is modeled via `SecurityContext` selectable via the UI sidebar.

---

## 5. Primary Metric to Judge Product Usefulness

### **First-Contact Decision Accuracy Rate (Target: > 99.5%)**
While **Mean Time to Resolution (MTTR)** will drop significantly (from ~18 minutes to < 2 minutes), the single most critical North Star metric is **First-Contact Decision Accuracy Rate**—the percentage of cancellation fee determinations and service credit calculations that require zero subsequent billing adjustments or dispute claims.

---

## 6. AI Tool Usage Disclosure

In developing this system:
* **LLM Tool Calling:** Integrated Google Gemini (`gemini-2.0-flash`) for natural language understanding and structured tool dispatching via formal JSON schemas.
* **AI Coding Assistants:** Used AI coding tools for codebase architecture scaffolding, test suite generation, and forensic audit of edge cases against the CalQuity specification.
