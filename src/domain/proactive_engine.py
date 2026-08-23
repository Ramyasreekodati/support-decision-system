from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
from src.security.authorization import SecurityContext, is_authorized, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.domain.sla_engine import SLAEngine

class ProactiveEngine:
    """
    Proactive Issue Detection Engine (Problem 1).
    Scans tickets and operational data to detect:
    1. SLA breaches and countdown risks across the support queue.
    2. Emerging ticket clusters linked to known product issues (e.g. KI-208, KI-211).
    3. Cross-tenant anomalies and platform-wide outages.
    """
    def __init__(self, data_store: OperationalDataStore, doc_store: DocumentStore, sla_engine: Optional[SLAEngine] = None):
        self.data_store = data_store
        self.doc_store = doc_store
        self.sla_engine = sla_engine or SLAEngine()

    def get_sla_watchlist(self, context: SecurityContext) -> List[Dict[str, Any]]:
        """
        Analyzes all open tickets within authorization scope to build an SLA risk watchlist.
        """
        if self.data_store.tickets.empty:
            return []

        docs = self.doc_store.retrieve(context)
        snapshot_time = context.snapshot_time
        watchlist = []

        open_tickets = self.data_store.tickets[self.data_store.tickets['status'] == 'open']
        for _, row in open_tickets.iterrows():
            rec = row.to_dict()
            acc_id = rec.get('account_id')
            if not is_authorized(context, acc_id):
                continue

            # Merge plan info from accounts if present
            if not self.data_store.accounts.empty:
                acc_match = self.data_store.accounts[self.data_store.accounts['account_id'] == acc_id]
                if not acc_match.empty:
                    rec['support_plan'] = acc_match.iloc[0].get('plan', 'Enterprise')

            sla_decision = self.sla_engine.evaluate_sla(rec, docs, snapshot_time)
            
            created_at_dt = pd.to_datetime(rec.get('created_at')).tz_localize(IST) if pd.to_datetime(rec.get('created_at')).tzinfo is None else pd.to_datetime(rec.get('created_at'))
            elapsed_minutes = int((snapshot_time - created_at_dt).total_seconds() / 60.0)

            status_label = "ON_TRACK"
            urgency_score = 1
            if sla_decision.state in ["BREACHED", "DEADLINE_ELAPSED"]:
                status_label = "BREACHED"
                urgency_score = 4
            elif sla_decision.state == "BUSINESS_TIME_CALCULATION_UNSPECIFIED":
                status_label = "PENDING_SCHEDULE"
                urgency_score = 2
            elif sla_decision.deadline:
                mins_remaining = int((sla_decision.deadline - snapshot_time).total_seconds() / 60.0)
                if mins_remaining <= 15:
                    status_label = "AT_RISK"
                    urgency_score = 3

            watchlist.append({
                "ticket_id": rec.get("ticket_id"),
                "account_id": acc_id,
                "subject": rec.get("subject"),
                "channel": rec.get("channel"),
                "assigned_to": rec.get("assigned_to"),
                "created_at": str(rec.get("created_at")),
                "elapsed_minutes": elapsed_minutes,
                "target_minutes": sla_decision.target_minutes,
                "sla_state": sla_decision.state,
                "risk_status": status_label,
                "urgency_score": urgency_score,
                "escalation_requirement": sla_decision.escalation_requirement,
                "reason": sla_decision.limitations[0] if sla_decision.limitations else f"Target: {sla_decision.target_minutes}m"
            })

        return sorted(watchlist, key=lambda x: x["urgency_score"], reverse=True)

    def get_known_issue_clusters(self, context: SecurityContext) -> List[Dict[str, Any]]:
        """
        Clusters open tickets into known operational issues and systemic incidents.
        """
        if self.data_store.tickets.empty:
            return []

        clusters = [
            {
                "cluster_id": "INC-01",
                "title": "HTTP 500 Global Shipment Creation Outage",
                "known_issue_ref": "Platform Critical Outage",
                "keywords": ["http 500", "creation is failing", "creating any shipment"],
                "severity": "CRITICAL",
                "tickets": [],
                "impacted_accounts": set(),
                "recommended_action": "Trigger P1 Engineering Incident Response immediately."
            },
            {
                "cluster_id": "KI-208",
                "title": "Bulk CSV Upload Failure (Header / Large Batch)",
                "known_issue_ref": "KI-208 (Product Operations Guide)",
                "keywords": ["bulk upload", "csv", "4,200", "3,500"],
                "severity": "HIGH",
                "tickets": [],
                "impacted_accounts": set(),
                "recommended_action": "Advise customer to split batch into <2,500 rows and verify ISO header encoding per KI-208."
            },
            {
                "cluster_id": "KI-211",
                "title": "SwiftShip Driver Pickup Status Sync Delay",
                "known_issue_ref": "KI-211 (Product Operations Guide)",
                "keywords": ["swiftship", "booked after driver pickup", "collected the parcel"],
                "severity": "MEDIUM",
                "tickets": [],
                "impacted_accounts": set(),
                "recommended_action": "Inform customer of 15-30 min carrier webhook lag; verify via SwiftShip portal if >45 min."
            },
            {
                "cluster_id": "SEC-01",
                "title": "Security & Credential Exposure Incident",
                "known_issue_ref": "Security Policy SOP",
                "keywords": ["api key exposure", "screenshot", "production api key"],
                "severity": "CRITICAL",
                "tickets": [],
                "impacted_accounts": set(),
                "recommended_action": "Revoke exposed API key immediately and rotate enterprise credentials."
            }
        ]

        open_tickets = self.data_store.tickets[self.data_store.tickets['status'] == 'open']
        for _, row in open_tickets.iterrows():
            rec = row.to_dict()
            acc_id = rec.get('account_id')
            if not is_authorized(context, acc_id):
                continue

            text = f"{rec.get('subject', '')} {rec.get('description', '')}".lower()
            for c in clusters:
                if any(k in text for k in c["keywords"]):
                    c["tickets"].append({
                        "ticket_id": rec.get("ticket_id"),
                        "account_id": acc_id,
                        "subject": rec.get("subject"),
                        "assigned_to": rec.get("assigned_to"),
                        "created_at": str(rec.get("created_at"))
                    })
                    c["impacted_accounts"].add(acc_id)
                    break

        active_clusters = []
        for c in clusters:
            if c["tickets"]:
                active_clusters.append({
                    "cluster_id": c["cluster_id"],
                    "title": c["title"],
                    "known_issue_ref": c["known_issue_ref"],
                    "severity": c["severity"],
                    "ticket_count": len(c["tickets"]),
                    "impacted_accounts": sorted(list(c["impacted_accounts"])),
                    "tickets": c["tickets"],
                    "recommended_action": c["recommended_action"]
                })

        return active_clusters

    def get_systemic_insights(self, context: SecurityContext) -> Dict[str, Any]:
        """
        Aggregated proactive summary for operations management.
        """
        watchlist = self.get_sla_watchlist(context)
        clusters = self.get_known_issue_clusters(context)

        total_open = len(watchlist)
        breached_count = sum(1 for w in watchlist if w["risk_status"] == "BREACHED")
        at_risk_count = sum(1 for w in watchlist if w["risk_status"] == "AT_RISK")
        critical_clusters = sum(1 for c in clusters if c["severity"] == "CRITICAL")

        return {
            "snapshot_time": context.snapshot_time.strftime("%d %b %Y · %H:%M %Z"),
            "total_open_tickets": total_open,
            "sla_breached_count": breached_count,
            "sla_at_risk_count": at_risk_count,
            "active_clusters_count": len(clusters),
            "critical_incident_clusters": critical_clusters,
            "watchlist": watchlist,
            "clusters": clusters
        }
