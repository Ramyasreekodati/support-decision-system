from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd
from src.security.authorization import IST

@dataclass
class DecisionResult:
    decision: str
    amount: Optional[int]
    applicable_rule: str
    evidence: List[Dict[str, str]]
    limitations: List[str]
    requires_confirmation: bool = False

class CancellationEngine:
    def evaluate_cancellation(self, order_facts: dict, docs: List[dict], snapshot_time: datetime) -> DecisionResult:
        status = order_facts.get('order_status', order_facts.get('status'))
        created_at_raw = order_facts.get('booked_at', order_facts.get('order_created_at', order_facts.get('created_at')))
        account_id = order_facts.get('account_id')
        
        if pd.isna(created_at_raw) or created_at_raw is None:
            return DecisionResult("UNKNOWN", None, "none", [], ["Missing order booking timestamp."])

        created_at = pd.to_datetime(created_at_raw)
        if created_at.tzinfo is None:
            created_at = created_at.tz_localize(IST)
            
        elapsed_mins = (snapshot_time - created_at).total_seconds() / 60.0

        filenames = [d.get('metadata', {}).get('filename', '') for d in docs]
        has_sop = any("03_Cancellation_and_Service_Credit_SOP_v4" in fn for fn in filenames)
        has_northstar_agreement = any("05_Northstar_Logistics_Enterprise_Agreement" in fn for fn in filenames)
        has_lumenworks_agreement = any("06_LumenWorks_Service_Agreement" in fn for fn in filenames)
        
        evidence = []
        limitations = []
        if has_sop:
            evidence.append({"source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf", "rule": "General Cancellation SOP", "authority": "GENERAL_POLICY"})
        else:
            limitations.append("Missing General Cancellation SOP.")
            return DecisionResult("UNKNOWN", None, "none", evidence, limitations, False)

        if account_id == 'ACCT-001':
            if not has_northstar_agreement:
                limitations.append("Northstar account detected, but Northstar Enterprise Agreement is missing. Cannot reliably determine cancellation fee.")
                return DecisionResult("UNKNOWN", None, "missing_customer_agreement", evidence, limitations, False)
            evidence.append({"source": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "rule": "Northstar Waiver for BOOKED shipments", "authority": "CUSTOMER_SPECIFIC"})

        if account_id == 'ACCT-002':
            if not has_lumenworks_agreement:
                limitations.append("LumenWorks account detected, but LumenWorks Service Agreement is missing. Cannot reliably determine overrides.")
                return DecisionResult("UNKNOWN", None, "missing_customer_agreement", evidence, limitations, False)
            evidence.append({"source": "06_LumenWorks_Service_Agreement.pdf", "rule": "No special cancellation-fee waiver applies", "authority": "CUSTOMER_SPECIFIC"})

        if status == 'BOOKED':
            if account_id == 'ACCT-001':
                return DecisionResult("CANCELLATION_ALLOWED", 0, "northstar_cancellation_override", evidence, limitations, False)
            else:
                fee = 250 if elapsed_mins > 30 else 0
                return DecisionResult("CANCELLATION_ALLOWED", fee, "general_cancellation_sop", evidence, limitations, False)
        elif status == 'DRAFT':
            return DecisionResult("CANCELLATION_ALLOWED", 0, "general_cancellation_sop", evidence, limitations, False)
        else:
            return DecisionResult("CANCELLATION_NOT_ALLOWED", None, "general_cancellation_sop", evidence, limitations, False)
