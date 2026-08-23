# Product Note: ParcelPilot Support System

## The User Problem
B2B logistics support teams face extensive cognitive load navigating conflicting client agreements and dense Standard Operating Procedures (SOPs). Mistakes in cancellation fees, missed SLAs, or incorrect service credits result in immediate financial loss and diminished customer trust.

## Our Approach: Trust & Reliability
We chose to explicitly focus on **Trust & Reliability** rather than maximizing automation. While an autonomous AI resolving tickets unassisted sounds appealing, in enterprise B2B environments, transparency and accuracy are paramount. 

Our product philosophy is that an AI should never hallucinate a decision it isn't authorized to make. By forcing the AI to visually surface its exact logic, the human agent retains ultimate accountability and confidence.

## What Was Intentionally Not Built
- **Proactive Detection:** We did not build a cron-job style background agent that scans for SLA breaches automatically. We prioritized building a flawless, secure, reactive query engine first. Proactive escalation requires a mature event-driven infrastructure.
- **RAG for Raw Policy Interpretation:** We avoided letting the LLM independently interpret numerical fee tables in RAG. Math and tiered rules are explicitly coded deterministically.

## Future Improvements
- **Live LLM Integration:** Connect the mocked interface directly to Google Gemini's tool-calling APIs.
- **Calendar-Aware SLAs:** Introduce a comprehensive business-hours calendar module to accurately calculate non-24x7 response times across multiple time zones.
- **Service Credit Ledgers:** Connect to an external ledger API to aggregate monthly service credits and enforce the ₹5,000 corporate cap.

## Measurable Success Metric
The primary metric to track for this product is **Mean Time to Resolution (MTTR)** for Level 1 Billing & SLA tickets. By instantly surfacing the calculated fees alongside explicitly cited PDF evidence, we expect human agents to resolve these tickets significantly faster without having to manually locate or read the Northstar/LumenWorks enterprise agreements.
