from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd
from src.security.authorization import IST

@dataclass
class ServiceCreditDecision:
    eligibility: str
    credit_amount: Optional[int]
    applicable_rule: str
    conditions_checked: List[str]
    conditions_missing: List[str]
    credit_type: Optional[str]
    cap_status: str
    evidence: List[Dict[str, str]]
    conflict_detected: bool
    limitations: List[str]

class ServiceCreditEngine:
    def evaluate_service_credit(self, order_facts: dict, docs: List[dict], snapshot_time: datetime) -> ServiceCreditDecision:
        account_id = order_facts.get('account_id')
        carrier_fault = order_facts.get('carrier_fault')
        customer_fault = order_facts.get('customer_fault')
        carrier_fault_conflict = order_facts.get('carrier_fault_conflict', False)
        customer_fault_conflict = order_facts.get('customer_fault_conflict', False)
        shipment_fee = order_facts.get('shipment_fee_inr')
        
        window_end_raw = order_facts.get('pickup_window_end')
        evidence = []
        conditions_checked = []
        conditions_missing = []
        limitations = []
        
        if carrier_fault_conflict or customer_fault_conflict:
            limitations.append("Trusted sources contain conflicting fault information.")
            return ServiceCreditDecision("UNKNOWN", None, "conflict_resolution_required", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, True, limitations)

        if window_end is None:
            return ServiceCreditDecision("UNKNOWN", None, "none", [], ["pickup_window_end"], None, "UNKNOWN", [], False, ["Missing pickup window."])

        if pd.isna(actual_pickup) or actual_pickup is None:
            return ServiceCreditDecision("UNKNOWN", None, "none", [], ["pickup_actual_at"], None, "UNKNOWN", [], False, ["Pickup timing is unknown (pickup_actual_at is missing). The SOP explicitly forbids promising credit when pickup timing is unknown."])
            
        actual_pickup_dt = pd.to_datetime(actual_pickup)
        if actual_pickup_dt.tzinfo is None:
            actual_pickup_dt = actual_pickup_dt.tz_localize(IST)
        delay_hours = (actual_pickup_dt - window_end).total_seconds() / 3600.0
        conditions_checked.append(f"Pickup delay: {delay_hours:.2f} hours")
        conditions_missing = []
        limitations = []
        
        if carrier_fault_conflict or customer_fault_conflict:
            limitations.append("Trusted sources contain conflicting fault information.")
            return ServiceCreditDecision("UNKNOWN", None, "conflict_resolution_required", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, True, limitations)
            
        if pd.isna(carrier_fault) or carrier_fault is None:
            conditions_missing.append("carrier_fault")
        else:
            conditions_checked.append(f"Carrier fault: {carrier_fault}")
            
        if pd.isna(customer_fault) or customer_fault is None:
            conditions_missing.append("customer_fault")
        else:
            conditions_checked.append(f"Customer fault: {customer_fault}")
            
        if pd.isna(shipment_fee) or shipment_fee is None:
            conditions_missing.append("shipment_fee_inr")

        if not has_sop:
            limitations.append("Missing General Service Credit SOP.")
            return ServiceCreditDecision("UNKNOWN", None, "none", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
        else:
            evidence.append({"source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf", "rule": "General Service Credit SOP", "authority": "GENERAL_POLICY"})

        if account_id == 'ACCT-001':
            if not has_nw_agmt:
                limitations.append("Missing Northstar Agreement.")
                return ServiceCreditDecision("UNKNOWN", None, "missing_customer_agreement", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
            evidence.append({"source": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "rule": "Northstar terms", "authority": "CUSTOMER_SPECIFIC"})
            
        if account_id == 'ACCT-002':
            if not has_lw_agmt:
                limitations.append("Missing LumenWorks Agreement.")
                return ServiceCreditDecision("UNKNOWN", None, "missing_customer_agreement", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)
            evidence.append({"source": "06_LumenWorks_Service_Agreement.pdf", "rule": "LumenWorks fixed credit amount and threshold", "authority": "CUSTOMER_SPECIFIC"})

        if "carrier_fault" in conditions_missing or "customer_fault" in conditions_missing:
            limitations.append("Cannot verify fault.")
            return ServiceCreditDecision("UNKNOWN", None, "fault_verification_required", conditions_checked, conditions_missing, None, "UNKNOWN", evidence, False, limitations)

        if carrier_fault is False or customer_fault is True:
            return ServiceCreditDecision("NOT_ELIGIBLE", None, "fault_conditions_not_met", conditions_checked, conditions_missing, None, "NOT_APPLICABLE", evidence, False, limitations)

        if account_id == 'ACCT-001':
            if delay_hours >= 2.0:
                credit = int(0.20 * shipment_fee) if shipment_fee else None
                limitations.append("Assuming annual cap has not been exceeded since historical credit data is unavailable.")
                return ServiceCreditDecision("ELIGIBLE", credit, "northstar_service_credit_override", conditions_checked, conditions_missing, "PERCENTAGE", "UNKNOWN_HISTORICAL_CAP", evidence, False, limitations)
            else:
                return ServiceCreditDecision("NOT_ELIGIBLE", None, "delay_below_threshold", conditions_checked, conditions_missing, None, "NOT_APPLICABLE", evidence, False, limitations)
                
        elif account_id == 'ACCT-002':
            if delay_hours >= 3.0:
                return ServiceCreditDecision("ELIGIBLE", 250, "lumenworks_fixed_credit_override", conditions_checked, conditions_missing, "FIXED", "NO_CAP_SPECIFIED", evidence, False, limitations)
            else:
                return ServiceCreditDecision("NOT_ELIGIBLE", None, "delay_below_threshold", conditions_checked, conditions_missing, None, "NOT_APPLICABLE", evidence, False, limitations)
        else:
            if delay_hours >= 4.0:
                credit = int(0.10 * shipment_fee) if shipment_fee else None
                return ServiceCreditDecision("ELIGIBLE", credit, "general_service_credit_sop", conditions_checked, conditions_missing, "PERCENTAGE", "GENERAL_TERMS", evidence, False, limitations)
            else:
                return ServiceCreditDecision("NOT_ELIGIBLE", None, "delay_below_threshold", conditions_checked, conditions_missing, None, "NOT_APPLICABLE", evidence, False, limitations)
