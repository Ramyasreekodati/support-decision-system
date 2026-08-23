from dataclasses import dataclass
from datetime import datetime
from typing import FrozenSet, Optional
import pytz

IST = pytz.timezone("Asia/Kolkata")

@dataclass(frozen=True)
class SecurityContext:
    """Immutable session security context."""
    role: str
    account_scope: FrozenSet[str]
    snapshot_time: datetime

def is_authorized(context: SecurityContext, resource_account_id: Optional[str]) -> bool:
    """Enforces tenant boundary at data/tool layers."""
    if context.role == "support_admin":
        return True
    if "ALL" in context.account_scope:
        return True
    if resource_account_id is None:
        return True
    return resource_account_id in context.account_scope
