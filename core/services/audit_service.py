import json
import logging
from typing import Optional, Any
from sqlalchemy.orm import Session
from ..database.models.system import AuditLog

logger = logging.getLogger("LibraryAutomation.Audit")

def log_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Any] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
):
    """Records an immutable security, circulation, or inventory action in the audit log."""
    try:
        details_str = json.dumps(details) if isinstance(details, (dict, list)) else str(details or "")
        audit = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details_str,
            ip_address=ip_address
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record audit log for {action}: {e}")
        db.rollback()
