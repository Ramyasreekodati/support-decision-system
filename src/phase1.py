import unittest
import pandas as pd
import pypdf
import os
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

# 4. Implement SecurityContext
@dataclass(frozen=True)
class SecurityContext:
    role: str
    account_scope: List[str]
    snapshot_time: datetime

    def __post_init__(self):
        # snapshot_time is immutable because frozen=True
        pass

class RetrievalMode(Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"

# 3. Create explicit document metadata
DOCUMENT_METADATA_DEFS = {
    "01_Support_Policy_v3_CURRENT.pdf": {
        "document_id": "doc_01",
        "filename": "01_Support_Policy_v3_CURRENT.pdf",
        "status": "CURRENT",
        "effective_date": "2026-05-01",
        "superseded_by": None,
        "customer_scope": ["General"],
        "domain": "support_policy",
        "applicability": "current"
    },
    "02_Support_Policy_v2_DEPRECATED.pdf": {
        "document_id": "doc_02",
        "filename": "02_Support_Policy_v2_DEPRECATED.pdf",
        "status": "DEPRECATED",
        "effective_date": "2025-01-01",
        "superseded_by": "01_Support_Policy_v3_CURRENT.pdf",
        "customer_scope": ["General"],
        "domain": "support_policy",
        "applicability": "historical"
    },
    "03_Cancellation_and_Service_Credit_SOP_v4.pdf": {
        "document_id": "doc_03",
        "filename": "03_Cancellation_and_Service_Credit_SOP_v4.pdf",
        "status": "CURRENT",
        "effective_date": "2026-06-15",
        "superseded_by": None,
        "customer_scope": ["General"],
        "domain": "sop",
        "applicability": "current"
    },
    "04_Product_Operations_Guide_and_Known_Issues.pdf": {
        "document_id": "doc_04",
        "filename": "04_Product_Operations_Guide_and_Known_Issues.pdf",
        "status": "CURRENT",
        "effective_date": "2026-08-14",
        "superseded_by": None,
        "customer_scope": ["General"],
        "domain": "product_guide",
        "applicability": "current"
    },
    "05_Northstar_Logistics_Enterprise_Agreement.pdf": {
        "document_id": "doc_05",
        "filename": "05_Northstar_Logistics_Enterprise_Agreement.pdf",
        "status": "ACTIVE",
        "effective_date": "2026-01-01",
        "superseded_by": None,
        "customer_scope": ["ACCT-001"],
        "domain": "customer_agreement",
        "applicability": "current"
    },
    "06_LumenWorks_Service_Agreement.pdf": {
        "document_id": "doc_06",
        "filename": "06_LumenWorks_Service_Agreement.pdf",
        "status": "ACTIVE",
        "effective_date": "2026-03-01",
        "superseded_by": None,
        "customer_scope": ["ACCT-002"],
        "domain": "customer_agreement",
        "applicability": "current"
    }
}

class DocumentStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.documents = []
        self._load_and_extract_pdfs()

    def _load_and_extract_pdfs(self):
        for filename, meta in DOCUMENT_METADATA_DEFS.items():
            path = os.path.join(self.data_dir, filename)
            text_content = ""
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        reader = pypdf.PdfReader(f)
                        for page in reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text_content += page_text + "\n"
                except Exception as e:
                    text_content = f"Error extracting PDF: {e}"
            else:
                text_content = "File not found"
            
            doc_record = {
                "metadata": meta,
                "content": text_content
            }
            self.documents.append(doc_record)

    # 5. Implement least-privilege authorization for documents
    def _is_authorized(self, context: SecurityContext, doc_scope: List[str]) -> bool:
        if context.role == "support_admin":
            return True
        if "General" in doc_scope:
            return True
        if context.role == "support_agent" or context.role == "customer":
            # Must overlap with assigned accounts
            for acc in context.account_scope:
                if acc in doc_scope:
                    return True
        return False

    # 6. Implement CURRENT/HISTORICAL retrieval mode model
    def retrieve(self, context: SecurityContext, mode: RetrievalMode) -> List[Dict[str, Any]]:
        if not isinstance(context, SecurityContext):
            raise ValueError("Invalid Security Context")
        
        results = []
        for doc in self.documents:
            meta = doc["metadata"]
            
            # Authorization Check
            if not self._is_authorized(context, meta["customer_scope"]):
                continue
                
            # Mode Check
            is_deprecated = meta["status"] == "DEPRECATED"
            if mode == RetrievalMode.CURRENT and is_deprecated:
                continue
                
            if mode == RetrievalMode.HISTORICAL and is_deprecated:
                # Add historical flag
                retrieved_doc = doc.copy()
                retrieved_doc["metadata"] = meta.copy()
                retrieved_doc["metadata"]["historical_label"] = "[HISTORICAL - NOT CURRENT]"
                results.append(retrieved_doc)
                continue
                
            results.append(doc)
            
        return results

class OperationalDataStore:
    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.xlsx = pd.ExcelFile(excel_path)
        self.accounts = pd.read_excel(self.xlsx, "accounts")
        self.orders = pd.read_excel(self.xlsx, "orders")
        self.tickets = pd.read_excel(self.xlsx, "tickets")
        
    # 7. Implement basic secure operational-data access contract
    def query_orders(self, context: SecurityContext, order_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(context, SecurityContext):
            raise ValueError("Invalid Security Context")
            
        order_row = self.orders[self.orders["order_id"] == order_id]
        if order_row.empty:
            return None
            
        order_dict = order_row.iloc[0].to_dict()
        account_id = order_dict["account_id"]
        
        # Access control
        if context.role == "support_admin":
            return order_dict
        if account_id in context.account_scope:
            return order_dict
            
        raise PermissionError("Unauthorized account access")

    def query_tickets(self, context: SecurityContext, ticket_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(context, SecurityContext):
            raise ValueError("Invalid Security Context")
            
        ticket_row = self.tickets[self.tickets["ticket_id"] == ticket_id]
        if ticket_row.empty:
            return None
            
        ticket_dict = ticket_row.iloc[0].to_dict()
        account_id = ticket_dict["account_id"]
        
        if context.role == "support_admin":
            return ticket_dict
        if account_id in context.account_scope:
            return ticket_dict
            
        raise PermissionError("Unauthorized account access")

# 8. Write unit tests
class TestPhase1Foundation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot_time = datetime.strptime("2026-08-16 11:00", "%Y-%m-%d %H:%M")
        cls.data_dir = "g:/ParcelPilot"
        cls.excel_path = os.path.join(cls.data_dir, "ParcelPilot_Assessment_Data.xlsx")
        
        cls.doc_store = DocumentStore(cls.data_dir)
        cls.data_store = OperationalDataStore(cls.excel_path)

    def test_invalid_security_context(self):
        with self.assertRaises(ValueError):
            self.data_store.query_orders("fake_context", "ORD-1001")
            
    def test_customer_cannot_access_another_account(self):
        customer_ctx = SecurityContext(role="customer", account_scope=["ACCT-001"], snapshot_time=self.snapshot_time)
        with self.assertRaises(PermissionError):
            self.data_store.query_orders(customer_ctx, "ORD-2001") # Belongs to ACCT-002
            
    def test_support_agent_cannot_access_unassigned_account(self):
        agent_ctx = SecurityContext(role="support_agent", account_scope=["ACCT-002"], snapshot_time=self.snapshot_time)
        with self.assertRaises(PermissionError):
            self.data_store.query_tickets(agent_ctx, "TKT-501") # Belongs to ACCT-001
            
    def test_support_admin_can_access_authorized_accounts(self):
        admin_ctx = SecurityContext(role="support_admin", account_scope=["ALL"], snapshot_time=self.snapshot_time)
        order = self.data_store.query_orders(admin_ctx, "ORD-1001")
        self.assertIsNotNone(order)
        self.assertEqual(order["account_id"], "ACCT-001")
        
    def test_snapshot_time_cannot_be_overridden_by_llm(self):
        ctx = SecurityContext(role="support_agent", account_scope=["ACCT-001"], snapshot_time=self.snapshot_time)
        # Attempt to modify frozen dataclass
        with self.assertRaises(Exception):
            ctx.snapshot_time = datetime.now()
            
    def test_deprecated_document_excluded_in_current_mode(self):
        ctx = SecurityContext(role="support_admin", account_scope=["ALL"], snapshot_time=self.snapshot_time)
        docs = self.doc_store.retrieve(ctx, RetrievalMode.CURRENT)
        for d in docs:
            self.assertNotEqual(d["metadata"]["status"], "DEPRECATED")
            
    def test_deprecated_document_available_in_historical_mode(self):
        ctx = SecurityContext(role="support_admin", account_scope=["ALL"], snapshot_time=self.snapshot_time)
        docs = self.doc_store.retrieve(ctx, RetrievalMode.HISTORICAL)
        deprecated_found = False
        for d in docs:
            if d["metadata"]["status"] == "DEPRECATED":
                deprecated_found = True
                self.assertIn("historical_label", d["metadata"])
                self.assertEqual(d["metadata"]["historical_label"], "[HISTORICAL - NOT CURRENT]")
        self.assertTrue(deprecated_found)
        
    def test_customer_cannot_retrieve_another_customers_agreement(self):
        customer_ctx = SecurityContext(role="customer", account_scope=["ACCT-001"], snapshot_time=self.snapshot_time)
        docs = self.doc_store.retrieve(customer_ctx, RetrievalMode.CURRENT)
        for d in docs:
            scope = d["metadata"]["customer_scope"]
            self.assertTrue("General" in scope or "ACCT-001" in scope)
            self.assertNotIn("ACCT-002", scope)

if __name__ == '__main__':
    unittest.main()
