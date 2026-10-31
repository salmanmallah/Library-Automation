from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.user import User
from core.auth.dependencies import require_roles
from core.services.audit_service import log_audit_event

router = APIRouter(prefix="/api/users", tags=["User & Member Management"])

class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    max_borrow_limit: Optional[int] = None

@router.get("")
def list_users(
    role: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if q:
        clean = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(clean),
                User.username.ilike(clean),
                User.email.ilike(clean),
                User.member_code.ilike(clean)
            )
        )
    users = query.order_by(User.id.desc()).limit(limit).all()
    return [u.to_dict() for u in users]

@router.get("/{user_id}")
def get_user_profile(
    user_id: int,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    data = user.to_dict()
    data["active_loans"] = [l.to_dict() for l in user.loans if l.status == "active"]
    data["total_loans_count"] = len(user.loans)
    data["unpaid_fines"] = [f.to_dict() for f in user.fines if f.status in ("unpaid", "partially_paid")]
    return data

@router.put("/{user_id}")
def update_user(
    user_id: int,
    req: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if req.full_name is not None:
        user.full_name = req.full_name.strip()
    if req.phone is not None:
        user.phone = req.phone.strip()
    if req.department is not None:
        user.department = req.department.strip()
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.max_borrow_limit is not None:
        user.max_borrow_limit = req.max_borrow_limit

    db.commit()
    db.refresh(user)

    log_audit_event(
        db,
        action="USER_UPDATED",
        resource_type="USER",
        resource_id=str(user.id),
        details={"username": user.username, "is_active": user.is_active},
        user_id=current_user.id,
        ip_address=request.client.host if request.client else "Local"
    )

    return {"success": True, "user": user.to_dict()}
