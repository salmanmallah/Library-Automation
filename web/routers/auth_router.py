from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.user import User
from core.auth.security import verify_password, hash_password, create_access_token
from core.auth.dependencies import get_current_user, require_roles
from core.services.audit_service import log_audit_event

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterMemberRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str
    member_code: str
    phone: Optional[str] = None
    department: Optional[str] = "General"
    max_borrow_limit: Optional[int] = 5

@router.post("/login")
def login(req: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == req.username.strip()) | (User.email == req.username.strip())
    ).first()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been suspended or deactivated. Contact Library Administration."
        )

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role, "name": user.full_name})
    
    # Set HTTP-only Cookie for security
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        secure=False  # Allow local development over HTTP
    )

    log_audit_event(
        db,
        action="USER_LOGIN",
        resource_type="USER",
        resource_id=str(user.id),
        details={"username": user.username, "role": user.role},
        user_id=user.id,
        ip_address=request.client.host if request.client else "Local"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user.to_dict()
    }

@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True, "message": "Successfully logged out."}

@router.post("/register-member")
def register_member(
    req: RegisterMemberRequest,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    # Check duplicate username, email, or member_code
    if db.query(User).filter(User.username == req.username.strip()).first():
        raise HTTPException(status_code=400, detail="Username is already in use.")
    if db.query(User).filter(User.email == req.email.strip()).first():
        raise HTTPException(status_code=400, detail="Email address is already in use.")
    if db.query(User).filter(User.member_code == req.member_code.strip()).first():
        raise HTTPException(status_code=400, detail="Member ID / Roll number is already registered.")

    new_member = User(
        username=req.username.strip(),
        email=req.email.strip(),
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
        role="member",
        member_code=req.member_code.strip(),
        phone=req.phone.strip() if req.phone else None,
        department=req.department.strip() if req.department else "General",
        is_active=True,
        max_borrow_limit=req.max_borrow_limit or 5
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    log_audit_event(
        db,
        action="MEMBER_REGISTERED",
        resource_type="USER",
        resource_id=str(new_member.id),
        details={"member_code": new_member.member_code, "name": new_member.full_name},
        user_id=current_user.id
    )

    return {"success": True, "member": new_member.to_dict()}
