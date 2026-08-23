# Product Note: ParcelPilot Support Decision System

## 1. Problem Context
B2B logistics operations teams manage high-value client contracts with complex contractual nuances, tiered cancellation penalties, and strict SLA deadlines. In high-volume support queues, manual contract lookup leads to high Mean Time to Resolution (MTTR), frequent billing disputes, and compliance breaches.

---

## 2. Additional Client Problem Selected: Problem 2 (Trust & Reliability)

We prioritized **Problem 2 (Trust & Reliability)** over raw reactive automation. In enterprise logistics, an incorrectly calculated cancellation fee or an unapproved ticket mutation creates immediate financial and legal liabilities.

### How Trust & Reliability is Addressed:
1. **Deterministic Rule Enforcement:** Business logic (cancellation fee math, delay thresholds, and SLA timers) is executed exclusively by auditable Python domain engines (`src/domain/`), not unconstrained LLM hallucinations.
2. **Explicit Evidence Provenance:** Every response outputs exact PDF citations classified by authority level:
   - `CUSTOMER_SPECIFIC (Overrides Standard Policy)` for enterprise contracts (e.g., Northstar Agreement).
   - `GENERAL_POLICY (Standard Precedence)` for baseline operating procedures (SOP v4).
3. **Transparent Handling of Missing Facts (`UNKNOWN`):** When critical data is missing (e.g., `pickup_actual_at` on order `ORD-2001` or undefined non-24x7 business hours), the system explicitly refuses to guess. It returns `UNKNOWN` and lists the exact missing facts.
4. **Human-in-the-Loop Action Gateway:** The AI cannot execute state-changing actions directly. It only stages proposals (`PREPARED`). Execution requires human confirmation in the UI followed by a live 4-point revalidation (Auth, Record Access, Live Rule State, and SHA256 Payload Hash integrity).
5. **Data-Layer Tenant Isolation:** Security boundaries are enforced in `OperationalDataStore` via `is_authorized()`, raising `PermissionError` before any business rules or documents are accessed.

---

## 3. Product Roadmap: Future Development (Including Problem 1)

If continuing to develop ParcelPilot, our prioritized roadmap includes:

1. **Problem 1 — Proactive Anomaly & Issue Detection (Near-Term Priority):**
   - Implement an asynchronous queue monitor that scans active shipments and support tickets every 60 seconds.
   - Detect emerging clusters (e.g., multiple CSV upload failures linked to `KI-208` or pickup confirmation delays linked to `KI-211`).
   - Automatically surface at-risk P1 tickets approaching the 15-minute / 30-minute threshold before breach occurs.
2. **Dynamic Corporate Credit Ledgers:**
   - Integrate an external transactional ledger to track cumulative monthly service credits against the ₹5,000 corporate annual cap for Northstar.
3. **Calendar-Aware Business Hours Engine:**
   - Implement a configurable holiday and operating-hours calendar for Growth and Standard tiers (e.g., 9 AM - 6 PM IST on business days).
4. **Webhook Event Sinks:**
   - Subscribe directly to carrier webhooks (e.g., SwiftShip API) to invalidate stale order states in real-time.

---

## 4. What Was Intentionally Left Out of the Submission

1. **Autonomous Mutation Authority:** We intentionally excluded any `execute_escalation` tool from the LLM's toolset. Actions must be staged and reviewed by authorized human operators.
2. **Multi-Tenant Distributed Database Cluster:** We used Excel parsing with dynamic snapshot reconstruction to match the provided assessment data pack without introducing external cloud database dependencies.
3. **OAuth/SAML Provider Integration:** Authentication context is modeled cleanly via `SecurityContext` selectable via the UI sidebar.

---

## 5. Primary Metric to Judge Product Usefulness

### **First-Contact Decision Accuracy Rate (Target: > 99.5%)**
While **Mean Time to Resolution (MTTR)** will drop significantly (from ~18 minutes to < 2 minutes), the single most critical North Star metric is **First-Contact Decision Accuracy Rate**—the percentage of cancellation fee determinations and service credit calculations that require zero subsequent billing adjustments or dispute claims.

---

## 6. AI Tool Usage Disclosure

In developing this system:
* **LLM Tool Calling:** Integrated Google Gemini (`gemini-2.0-flash`) for natural language understanding and structured tool dispatching via formal JSON schemas.
* **AI Coding Assistants:** Used AI coding tools for codebase architecture scaffolding, test suite generation, and forensic audit of edge cases against the CalQuity specification.
