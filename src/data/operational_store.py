import pathlib
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any
from src.security.authorization import SecurityContext, is_authorized, IST

class OperationalDataStore:
    def __init__(self, excel_path: Optional[pathlib.Path] = None):
        self.excel_path = excel_path or (pathlib.Path(__file__).resolve().parent.parent.parent / "ParcelPilot_Assessment_Data.xlsx")
        self.orders = pd.DataFrame()
        self.tickets = pd.DataFrame()
        self.accounts = pd.DataFrame()
        self._snapshot_time = IST.localize(datetime(2026, 8, 16, 11, 0))
        self._load_data()

    def _load_data(self):
        try:
            readme = pd.read_excel(self.excel_path, sheet_name='README', header=None)
            snapshot_str = str(readme.iloc[1, 1])
            dt_str = snapshot_str.rsplit(' ', 1)[0]
            self._snapshot_time = IST.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
        except Exception:
            pass

        try:
            self.orders = pd.read_excel(self.excel_path, sheet_name='orders')
            self.tickets = pd.read_excel(self.excel_path, sheet_name='tickets')
            self.accounts = pd.read_excel(self.excel_path, sheet_name='accounts')
        except Exception:
            pass

    def get_snapshot_time(self) -> datetime:
        return self._snapshot_time

    def query_orders(self, context: SecurityContext, order_id: str) -> Optional[Dict[str, Any]]:
        if self.orders.empty:
            return None
        match = self.orders[self.orders['order_id'] == order_id]
        if match.empty:
            return None
        rec = match.iloc[0].to_dict()
        if not is_authorized(context, rec.get('account_id')):
            raise PermissionError(f"Unauthorized access to order {order_id} for scope {context.account_scope}")
        return rec

    def query_tickets(self, context: SecurityContext, ticket_id: str) -> Optional[Dict[str, Any]]:
        if self.tickets.empty:
            return None
        match = self.tickets[self.tickets['ticket_id'] == ticket_id]
        if match.empty:
            return None
        rec = match.iloc[0].to_dict()
        if not is_authorized(context, rec.get('account_id')):
            raise PermissionError(f"Unauthorized access to ticket {ticket_id} for scope {context.account_scope}")
        return rec
