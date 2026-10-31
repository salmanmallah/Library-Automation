from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.system import AuditLog
from core.database.models.user import User
from core.auth.dependencies import require_roles

router = APIRouter(prefix="/api/audit", tags=["Audit Logs"])

@router.get("/logs")
def get_audit_logs(
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_roles("super_admin", "library_admin")),
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    logs = query.order_by(AuditLog.id.desc()).limit(limit).all()
    return [l.to_dict() for l in logs]
