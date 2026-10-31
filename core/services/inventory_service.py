import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from ..database.models.inventory import BookCopy, Shelf
from ..database.models.catalog import Book
from .audit_service import log_audit_event

logger = logging.getLogger("LibraryAutomation.InventoryService")

def get_copies(
    db: Session,
    book_id: Optional[int] = None,
    shelf_id: Optional[int] = None,
    status: Optional[str] = None,
    query: Optional[str] = None
) -> List[Dict[str, Any]]:
    q = db.query(BookCopy).join(BookCopy.book).outerjoin(BookCopy.shelf)

    if book_id:
        q = q.filter(BookCopy.book_id == book_id)
    if shelf_id:
        q = q.filter(BookCopy.shelf_id == shelf_id)
    if status:
        q = q.filter(BookCopy.status == status)
    if query:
        clean_q = f"%{query.strip()}%"
        q = q.filter(
            (BookCopy.copy_barcode.ilike(clean_q)) |
            (Book.title.ilike(clean_q)) |
            (Book.isbn.ilike(clean_q))
        )

    copies = q.order_by(BookCopy.id.desc()).all()
    return [c.to_dict() for c in copies]

def add_copy(
    db: Session,
    book_id: int,
    shelf_id: Optional[int] = None,
    condition: str = "good",
    price: float = 0.0,
    custom_barcode: Optional[str] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> BookCopy:
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise ValueError(f"Book ID {book_id} does not exist.")

    if custom_barcode:
        barcode = custom_barcode.strip()
        existing = db.query(BookCopy).filter(BookCopy.copy_barcode == barcode).first()
        if existing:
            raise ValueError(f"Barcode '{barcode}' is already assigned to another copy.")
    else:
        # Generate next copy number
        current_count = len(book.copies)
        barcode = f"BC-{book.isbn}-{current_count + 1:02d}"
        # Ensure uniqueness
        while db.query(BookCopy).filter(BookCopy.copy_barcode == barcode).first():
            current_count += 1
            barcode = f"BC-{book.isbn}-{current_count + 1:02d}"

    copy = BookCopy(
        book_id=book.id,
        copy_barcode=barcode,
        shelf_id=shelf_id,
        status="available",
        condition=condition,
        price=price
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)

    log_audit_event(
        db,
        action="COPY_ADDED",
        resource_type="COPY",
        resource_id=str(copy.id),
        details={"barcode": copy.copy_barcode, "book_title": book.title, "shelf_id": shelf_id},
        user_id=user_id,
        ip_address=ip_address
    )
    return copy

def update_copy(
    db: Session,
    copy_id: int,
    status: Optional[str] = None,
    condition: Optional[str] = None,
    shelf_id: Optional[int] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> BookCopy:
    copy = db.query(BookCopy).filter(BookCopy.id == copy_id).first()
    if not copy:
        raise ValueError(f"Copy ID {copy_id} not found.")

    if status and copy.status == "issued" and status != "issued":
        raise ValueError("Cannot manually change status of a currently issued copy. Process Return first.")

    if status:
        copy.status = status
    if condition:
        copy.condition = condition
    if shelf_id is not None:
        copy.shelf_id = shelf_id

    db.commit()
    db.refresh(copy)

    log_audit_event(
        db,
        action="COPY_UPDATED",
        resource_type="COPY",
        resource_id=str(copy.id),
        details={"barcode": copy.copy_barcode, "status": copy.status, "condition": copy.condition},
        user_id=user_id,
        ip_address=ip_address
    )
    return copy

def delete_copy(
    db: Session,
    copy_id: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> bool:
    copy = db.query(BookCopy).filter(BookCopy.id == copy_id).first()
    if not copy:
        return False
    if copy.status == "issued":
        raise ValueError("Cannot delete copy that is actively issued.")

    barcode = copy.copy_barcode
    db.delete(copy)
    db.commit()

    log_audit_event(
        db,
        action="COPY_DELETED",
        resource_type="COPY",
        resource_id=str(copy_id),
        details={"barcode": barcode},
        user_id=user_id,
        ip_address=ip_address
    )
    return True

def get_shelves(db: Session) -> List[Dict[str, Any]]:
    shelves = db.query(Shelf).order_by(Shelf.shelf_code.asc()).all()
    return [s.to_dict() for s in shelves]

def create_shelf(
    db: Session,
    shelf_code: str,
    floor: str = "Ground Floor",
    section: str = "General",
    capacity: int = 50,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Shelf:
    code = shelf_code.strip().upper()
    existing = db.query(Shelf).filter(Shelf.shelf_code == code).first()
    if existing:
        raise ValueError(f"Shelf '{code}' already exists.")

    shelf = Shelf(shelf_code=code, floor=floor, section=section, capacity=capacity)
    db.add(shelf)
    db.commit()
    db.refresh(shelf)

    log_audit_event(
        db,
        action="SHELF_CREATED",
        resource_type="SHELF",
        resource_id=str(shelf.id),
        details={"shelf_code": shelf.shelf_code, "capacity": shelf.capacity},
        user_id=user_id,
        ip_address=ip_address
    )
    return shelf
