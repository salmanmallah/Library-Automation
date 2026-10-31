import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import or_, and_, desc
from sqlalchemy.orm import Session

from ..database.models.circulation import Loan, Reservation, Fine
from ..database.models.inventory import BookCopy
from ..database.models.catalog import Book
from ..database.models.user import User
from ..database.models.system import SystemSetting
from .audit_service import log_audit_event

logger = logging.getLogger("LibraryAutomation.Circulation")

def get_setting_int(db: Session, key: str, default: int) -> int:
    st = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if st and st.value.isdigit():
        return int(st.value)
    return default

def get_setting_float(db: Session, key: str, default: float) -> float:
    st = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if st:
        try:
            return float(st.value)
        except ValueError:
            pass
    return default

def get_loans(
    db: Session,
    member_id: Optional[int] = None,
    status: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    q = db.query(Loan).join(Loan.copy).join(BookCopy.book).join(Loan.member)

    if member_id:
        q = q.filter(Loan.member_id == member_id)

    now = datetime.now()
    if status == "active":
        q = q.filter(Loan.status == "active")
    elif status == "overdue":
        q = q.filter(Loan.status == "active", Loan.due_date < now)
    elif status == "returned":
        q = q.filter(Loan.status == "returned")

    if query:
        clean_q = f"%{query.strip()}%"
        q = q.filter(
            or_(
                BookCopy.copy_barcode.ilike(clean_q),
                Book.title.ilike(clean_q),
                Book.isbn.ilike(clean_q),
                User.full_name.ilike(clean_q),
                User.member_code.ilike(clean_q)
            )
        )

    loans = q.order_by(desc(Loan.id)).limit(limit).all()
    return [l.to_dict() for l in loans]

def issue_book(
    db: Session,
    copy_barcode: str,
    member_identifier: str,
    issued_by_id: Optional[int] = None,
    custom_loan_days: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Loan:
    """
    Issues a physical book copy to an eligible registered member.
    Enforces borrowing limit, active member verification, fine threshold, and copy availability.
    """
    clean_barcode = copy_barcode.strip()
    clean_ident = member_identifier.strip()

    # 1. Resolve Member (by member_code, username, or id)
    member = db.query(User).filter(
        or_(
            User.member_code == clean_ident,
            User.username == clean_ident,
            User.email == clean_ident,
            User.id == int(clean_ident) if clean_ident.isdigit() else False
        )
    ).first()

    if not member:
        raise ValueError(f"Member '{clean_ident}' not found in registry.")
    if not member.is_active:
        raise ValueError(f"Member '{member.full_name}' account is suspended or inactive.")

    # 2. Check Member Active Loan Limit
    active_loans_count = db.query(Loan).filter(
        Loan.member_id == member.id,
        Loan.status == "active"
    ).count()

    max_limit = member.max_borrow_limit or get_setting_int(db, "max_loans_per_member", 5)
    if active_loans_count >= max_limit:
        raise ValueError(
            f"Borrowing limit reached: '{member.full_name}' currently has {active_loans_count} "
            f"active loans (maximum permitted: {max_limit})."
        )

    # 3. Check for High Outstanding Unpaid Fines
    unpaid_fines = db.query(Fine).filter(
        Fine.member_id == member.id,
        Fine.status.in_(["unpaid", "partially_paid"])
    ).all()
    total_unpaid = sum(f.amount - f.paid_amount for f in unpaid_fines)
    if total_unpaid > 100.0:  # Fine threshold
        raise ValueError(
            f"Member '{member.full_name}' has outstanding unpaid fines of ${total_unpaid:.2f}. "
            "Please clear pending fines before issuing new books."
        )

    # 4. Resolve Book Copy
    copy = db.query(BookCopy).filter(
        or_(
            BookCopy.copy_barcode == clean_barcode,
            BookCopy.id == int(clean_barcode) if clean_barcode.isdigit() else False
        )
    ).first()

    if not copy:
        raise ValueError(f"Book copy with barcode '{clean_barcode}' does not exist.")
    if copy.status != "available":
        raise ValueError(f"Book copy '{copy.copy_barcode}' is currently {copy.status.upper()} and cannot be issued.")

    # 5. Compute Loan Durations
    loan_days = custom_loan_days or get_setting_int(db, "default_loan_days", 14)
    now = datetime.now()
    due_date = now + timedelta(days=loan_days)

    loan = Loan(
        copy_id=copy.id,
        member_id=member.id,
        issued_by_id=issued_by_id,
        issue_date=now,
        due_date=due_date,
        status="active",
        renewal_count=0
    )
    copy.status = "issued"
    db.add(loan)
    db.commit()
    db.refresh(loan)

    log_audit_event(
        db,
        action="BOOK_ISSUED",
        resource_type="LOAN",
        resource_id=str(loan.id),
        details={
            "copy_barcode": copy.copy_barcode,
            "book_title": copy.book.title,
            "member_name": member.full_name,
            "member_code": member.member_code,
            "due_date": due_date.strftime("%Y-%m-%d")
        },
        user_id=issued_by_id,
        ip_address=ip_address
    )

    return loan

def return_book(
    db: Session,
    copy_barcode: str,
    processed_by_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Tuple[Loan, Optional[Fine]]:
    """
    Processes book return, updates copy status, computes overdue fines if late,
    and fulfills or checks waiting reservation queues.
    """
    clean_barcode = copy_barcode.strip()
    copy = db.query(BookCopy).filter(
        or_(
            BookCopy.copy_barcode == clean_barcode,
            BookCopy.id == int(clean_barcode) if clean_barcode.isdigit() else False
        )
    ).first()

    if not copy:
        raise ValueError(f"Book copy with barcode '{clean_barcode}' not found.")

    # Find active loan
    loan = db.query(Loan).filter(
        Loan.copy_id == copy.id,
        Loan.status == "active"
    ).first()

    if not loan:
        raise ValueError(f"Copy '{copy.copy_barcode}' ({copy.book.title}) is not currently marked as active loan.")

    now = datetime.now()
    loan.return_date = now
    loan.status = "returned"

    # Overdue fine calculation
    fine_record = None
    if loan.due_date and now.date() > loan.due_date.date():
        days_late = (now.date() - loan.due_date.date()).days
        fine_rate = get_setting_float(db, "fine_per_day", 1.0)
        fine_amount = round(days_late * fine_rate, 2)
        if fine_amount > 0:
            fine_record = Fine(
                loan_id=loan.id,
                member_id=loan.member_id,
                amount=fine_amount,
                paid_amount=0.0,
                status="unpaid",
                reason=f"Overdue return by {days_late} day(s) at ${fine_rate}/day."
            )
            db.add(fine_record)

    # Check for pending reservations on this book
    pending_res = db.query(Reservation).filter(
        Reservation.book_id == copy.book_id,
        Reservation.status == "pending"
    ).order_by(Reservation.priority.asc(), Reservation.reserved_at.asc()).first()

    if pending_res:
        copy.status = "reserved"
        pending_res.status = "fulfilled"
        logger.info(f"Copy {copy.copy_barcode} marked as RESERVED for member {pending_res.member.full_name}.")
    else:
        copy.status = "available"

    db.commit()
    db.refresh(loan)
    if fine_record:
        db.refresh(fine_record)

    log_audit_event(
        db,
        action="BOOK_RETURNED",
        resource_type="LOAN",
        resource_id=str(loan.id),
        details={
            "copy_barcode": copy.copy_barcode,
            "book_title": copy.book.title,
            "member_name": loan.member.full_name,
            "days_late": (now.date() - loan.due_date.date()).days if now.date() > loan.due_date.date() else 0,
            "fine_incurred": fine_record.amount if fine_record else 0.0
        },
        user_id=processed_by_id,
        ip_address=ip_address
    )

    return loan, fine_record

def renew_loan(
    db: Session,
    loan_id: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Loan:
    """Renews an active loan unless reservation queue or renewal limit is reached."""
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan or loan.status != "active":
        raise ValueError(f"Active loan with ID {loan_id} not found.")

    max_renewals = get_setting_int(db, "max_renewals_per_loan", 2)
    if loan.renewal_count >= max_renewals:
        raise ValueError(f"Renewal limit reached: Loan has already been renewed {loan.renewal_count} times.")

    # Check if another member has reserved this book title
    book_id = loan.copy.book_id
    has_res = db.query(Reservation).filter(
        Reservation.book_id == book_id,
        Reservation.member_id != loan.member_id,
        Reservation.status == "pending"
    ).count()

    if has_res > 0:
        raise ValueError("Cannot renew: Another member has placed a reservation hold on this book title.")

    loan_days = get_setting_int(db, "default_loan_days", 14)
    now = datetime.now()
    # If already past due, calculate from today, else extend current due date
    base_date = max(loan.due_date, now)
    loan.due_date = base_date + timedelta(days=loan_days)
    loan.renewal_count += 1

    db.commit()
    db.refresh(loan)

    log_audit_event(
        db,
        action="LOAN_RENEWED",
        resource_type="LOAN",
        resource_id=str(loan.id),
        details={"renewal_count": loan.renewal_count, "new_due_date": loan.due_date.strftime("%Y-%m-%d")},
        user_id=user_id,
        ip_address=ip_address
    )
    return loan

def create_reservation(
    db: Session,
    book_id: int,
    member_id: int,
    ip_address: Optional[str] = None
) -> Reservation:
    """Places a hold reservation on an unavailable book title."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise ValueError("Book does not exist.")

    member = db.query(User).filter(User.id == member_id).first()
    if not member or not member.is_active:
        raise ValueError("Active member account required for reservations.")

    # Check if member already has pending reservation for this title
    existing = db.query(Reservation).filter(
        Reservation.book_id == book_id,
        Reservation.member_id == member_id,
        Reservation.status == "pending"
    ).first()
    if existing:
        raise ValueError("You already have a pending reservation for this book.")

    expiry_days = get_setting_int(db, "reservation_expiry_days", 7)
    now = datetime.now()
    expiry = now + timedelta(days=expiry_days)

    pending_count = db.query(Reservation).filter(
        Reservation.book_id == book_id,
        Reservation.status == "pending"
    ).count()

    res = Reservation(
        book_id=book.id,
        member_id=member.id,
        reserved_at=now,
        expiry_date=expiry,
        status="pending",
        priority=pending_count + 1
    )
    db.add(res)
    db.commit()
    db.refresh(res)

    log_audit_event(
        db,
        action="RESERVATION_PLACED",
        resource_type="RESERVATION",
        resource_id=str(res.id),
        details={"book_title": book.title, "priority": res.priority},
        user_id=member_id,
        ip_address=ip_address
    )
    return res

def get_reservations(db: Session, member_id: Optional[int] = None) -> List[Dict[str, Any]]:
    q = db.query(Reservation).join(Reservation.book).join(Reservation.member)
    if member_id:
        q = q.filter(Reservation.member_id == member_id)
    res_list = q.order_by(Reservation.id.desc()).all()
    return [r.to_dict() for r in res_list]

def get_fines(db: Session, member_id: Optional[int] = None) -> List[Dict[str, Any]]:
    q = db.query(Fine).join(Fine.member)
    if member_id:
        q = q.filter(Fine.member_id == member_id)
    fines = q.order_by(Fine.id.desc()).all()
    return [f.to_dict() for f in fines]

def pay_fine(
    db: Session,
    fine_id: int,
    amount: float,
    processed_by_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Fine:
    fine = db.query(Fine).filter(Fine.id == fine_id).first()
    if not fine:
        raise ValueError("Fine record not found.")

    if amount <= 0:
        raise ValueError("Payment amount must be positive.")

    fine.paid_amount += amount
    if fine.paid_amount >= fine.amount:
        fine.status = "paid"
        fine.paid_amount = fine.amount
    else:
        fine.status = "partially_paid"

    db.commit()
    db.refresh(fine)

    log_audit_event(
        db,
        action="FINE_PAYMENT",
        resource_type="FINE",
        resource_id=str(fine.id),
        details={"paid": amount, "total": fine.amount, "status": fine.status},
        user_id=processed_by_id,
        ip_address=ip_address
    )
    return fine
