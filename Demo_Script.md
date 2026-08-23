# ParcelPilot Support System - 5 Minute Demo Script

## Introduction (0:00 - 1:00)
- **Context:** "Welcome to the ParcelPilot Support System. We've built an AI agent to help Level 1 and Level 2 support handle complex cancellation fees, service credits, and SLA escalations."
- **Core Principle:** "Our core engineering principle is that the LLM determines *what* to investigate, but strict deterministic Python rules decide *what the evidence means*. The LLM cannot do math or bypass policies."

## Scenario 1: Northstar Cancellation (1:00 - 1:45)
- **Setup:** Set the sidebar Role to `support_agent` and Account Scope to `ACCT-001 (Northstar)`.
- **Action:** Ask: *"Can I cancel ORD-1001?"*
- **Result:** The system determines a fee of **₹0**. 
- **Explanation:** Explain that the general SOP demands a fee, but the deterministic rule engine correctly applied the Northstar Enterprise Agreement override.

## Scenario 2: Unknown Service Credit (1:45 - 2:30)
- **Setup:** Keep the scope on Northstar.
- **Action:** Ask: *"Can ORD-2001 receive a credit?"*
- **Result:** The system yields **UNKNOWN**.
- **Explanation:** Highlight the `Limitations` warning. The system recognizes that the `pickup_actual_at` field is missing from the dataset. Instead of hallucinating a timeframe or blindly approving a credit, it refuses to act and alerts the human agent.

## Scenario 3: P1 Escalation (2:30 - 3:30)
- **Setup:** Change Role to `support_admin` (Scope: ALL).
- **Action:** Ask: *"SLA for TKT-501"*
- **Result:** The system yields **DEADLINE_ELAPSED** and prepares an action for human approval.
- **Explanation:** Emphasize that the system correctly calculates that the deadline has passed, but because `first_response_at` is missing in the dataset, it refuses to declare an absolute `BREACHED` state. However, it still enforces the strict rule that P1 tickets with elapsed deadlines **REQUIRE** escalation. 

## Scenario 4: Human Approval & Revalidation (3:30 - 4:15)
- **Action:** Click `Approve Escalation` on the pending TKT-501 action.
- **Result:** The action transitions to `EXECUTED successfully`.
- **Explanation:** Explain that clicking approve triggered a backend cryptographic revalidation of the user's security context before finalized execution, ensuring state integrity.

## Scenario 5: Cross-Account Security (4:15 - 5:00)
- **Setup:** Change Role to `customer` and Account Scope to `ACCT-002 (LumenWorks)`.
- **Action:** Ask: *"Cancel Northstar's ORD-1001"*
- **Result:** The system immediately blocks with an **UNAUTHORIZED** error.
- **Explanation:** Conclude the demo by highlighting that the AI agent does not enforce security—the deterministic `OperationalDataStore` physically restricts record access before the LLM can ever see it.
