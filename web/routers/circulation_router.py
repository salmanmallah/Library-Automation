from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.user import User
from core.auth.dependencies import get_current_user, require_roles
from core.services import circulation_service

router = APIRouter(prefix="/api/circulation", tags=["Circulation"])

class IssueRequest(BaseModel):
    copy_barcode: str = Field(..., min_length=3, max_length=50)
    member_identifier: str = Field(..., min_length=1, max_length=100)
    custom_loan_days: Optional[int] = Field(None, ge=1, le=90)

class ReturnRequest(BaseModel):
    copy_barcode: str = Field(..., min_length=3, max_length=50)

class ReservationRequest(BaseModel):
    book_id: int = Field(..., ge=1)

class FinePaymentRequest(BaseModel):
    amount: float = Field(..., gt=0.0)

@router.get("/loans")
def list_loans(
    status: Optional[str] = Query(None, description="active, overdue, returned"),
    member_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Non-staff members are strictly restricted to their own loans
    effective_member_id = member_id
    if current_user.role == "member":
        effective_member_id = current_user.id

    return circulation_service.get_loans(
        db=db,
        member_id=effective_member_id,
        status=status,
        query=q,
        limit=limit
    )

@router.post("/issue")
def issue_book(
    req: IssueRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    try:
        loan = circulation_service.issue_book(
            db=db,
            copy_barcode=req.copy_barcode,
            member_identifier=req.member_identifier,
            issued_by_id=current_user.id,
            custom_loan_days=req.custom_loan_days,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "message": "Book copy successfully issued.", "loan": loan.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/return")
def return_book(
    req: ReturnRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    try:
        loan, fine = circulation_service.return_book(
            db=db,
            copy_barcode=req.copy_barcode,
            processed_by_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        return {
            "success": True,
            "message": "Book copy successfully returned to shelf inventory.",
            "loan": loan.to_dict(),
            "fine_incurred": fine.to_dict() if fine else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/renew/{loan_id}")
def renew_loan(
    loan_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        is_staff = current_user.role in ("super_admin", "library_admin", "librarian")
        loan = circulation_service.renew_loan(
            db=db,
            loan_id=loan_id,
            user_id=current_user.id,
            is_staff=is_staff,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "message": "Loan successfully renewed.", "loan": loan.to_dict()}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/reservations")
def list_reservations(
    member_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    effective_id = member_id
    if current_user.role == "member":
        effective_id = current_user.id
    return circulation_service.get_reservations(db, member_id=effective_id)

@router.post("/reservations")
def place_reservation(
    req: ReservationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        res = circulation_service.create_reservation(
            db=db,
            book_id=req.book_id,
            member_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "message": "Reservation hold placed.", "reservation": res.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/fines")
def list_fines(
    member_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    effective_id = member_id
    if current_user.role == "member":
        effective_id = current_user.id
    return circulation_service.get_fines(db, member_id=effective_id)

@router.post("/fines/{fine_id}/pay")
def pay_fine(
    fine_id: int,
    req: FinePaymentRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    try:
        fine = circulation_service.pay_fine(
            db=db,
            fine_id=fine_id,
            amount=req.amount,
            processed_by_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "message": "Payment recorded.", "fine": fine.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
