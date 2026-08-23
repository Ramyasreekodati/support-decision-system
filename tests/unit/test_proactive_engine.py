import pytest
from src.security.authorization import SecurityContext, IST
from src.data.operational_store import OperationalDataStore
from src.data.document_store import DocumentStore
from src.domain.proactive_engine import ProactiveEngine

@pytest.fixture
def stores():
    data_store = OperationalDataStore()
    doc_store = DocumentStore()
    engine = ProactiveEngine(data_store, doc_store)
    return data_store, doc_store, engine

def test_sla_watchlist_admin_scope(stores):
    data_store, doc_store, engine = stores
    context = SecurityContext(role="support_admin", account_scope=frozenset(["ALL"]), snapshot_time=data_store.get_snapshot_time())
    watchlist = engine.get_sla_watchlist(context)
    
    assert len(watchlist) > 0
    # TKT-501 (Northstar P1, 15m target, 30m elapsed) must be flagged as BREACHED
    tkt_501 = next((w for w in watchlist if w["ticket_id"] == "TKT-501"), None)
    assert tkt_501 is not None
    assert tkt_501["risk_status"] == "BREACHED"
    assert tkt_501["escalation_requirement"] == "REQUIRED"

def test_sla_watchlist_tenant_scoped(stores):
    data_store, doc_store, engine = stores
    context = SecurityContext(role="customer", account_scope=frozenset(["ACCT-001"]), snapshot_time=data_store.get_snapshot_time())
    watchlist = engine.get_sla_watchlist(context)
    
    # Must only return ACCT-001 tickets
    assert all(w["account_id"] == "ACCT-001" for w in watchlist)

def test_known_issue_clustering(stores):
    data_store, doc_store, engine = stores
    context = SecurityContext(role="support_admin", account_scope=frozenset(["ALL"]), snapshot_time=data_store.get_snapshot_time())
    clusters = engine.get_known_issue_clusters(context)
    
    cluster_ids = [c["cluster_id"] for c in clusters]
    assert "INC-01" in cluster_ids # HTTP 500 Outage
    assert "KI-208" in cluster_ids # CSV upload failure
    assert "KI-211" in cluster_ids # SwiftShip pickup lag

def test_systemic_insights_summary(stores):
    data_store, doc_store, engine = stores
    context = SecurityContext(role="support_admin", account_scope=frozenset(["ALL"]), snapshot_time=data_store.get_snapshot_time())
    insights = engine.get_systemic_insights(context)
    
    assert insights["total_open_tickets"] >= 5
    assert insights["sla_breached_count"] >= 1
    assert len(insights["clusters"]) >= 3
