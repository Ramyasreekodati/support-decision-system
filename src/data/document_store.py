from enum import Enum
from typing import List, Dict, Any, Optional
import pathlib
import pypdf
from src.security.authorization import SecurityContext, is_authorized

class RetrievalMode(Enum):
    CURRENT = "CURRENT"
    ALL = "ALL"

class DocumentStore:
    def __init__(self, pdf_dir: Optional[pathlib.Path] = None):
        self.pdf_dir = pdf_dir or pathlib.Path(__file__).resolve().parent.parent.parent
        self.documents = []
        self._load_documents()

    def _load_documents(self):
        pdf_files = list(self.pdf_dir.glob("*.pdf"))
        for pdf_path in pdf_files:
            fn = pdf_path.name
            try:
                reader = pypdf.PdfReader(str(pdf_path))
                text = "\n".join([page.extract_text() or "" for page in reader.pages])
                
                account_id = None
                if "Northstar" in fn:
                    account_id = "ACCT-001"
                elif "LumenWorks" in fn:
                    account_id = "ACCT-002"
                
                is_deprecated = "DEPRECATED" in fn or "SUPERSEDED" in fn
                
                self.documents.append({
                    "content": text,
                    "metadata": {
                        "filename": fn,
                        "account_id": account_id,
                        "is_deprecated": is_deprecated,
                        "authority": "CUSTOMER_SPECIFIC" if "Agreement" in fn else "GENERAL_POLICY"
                    }
                })
            except Exception as e:
                pass

    def retrieve(self, context: SecurityContext, mode: RetrievalMode = RetrievalMode.CURRENT) -> List[Dict[str, Any]]:
        results = []
        for doc in self.documents:
            acc = doc["metadata"]["account_id"]
            if is_authorized(context, acc):
                results.append(doc)
                
        if mode == RetrievalMode.CURRENT:
            results = [d for d in results if not d["metadata"]["is_deprecated"]]
            
        return results
