from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.user import User
from core.database.models.catalog import Category
from core.auth.dependencies import get_current_user, require_roles, get_optional_current_user
from core.services import catalog_service
from core.book_service import BookService
from core.config import AppConfig

router = APIRouter(prefix="/api/catalog", tags=["Catalog"])
book_service = BookService(AppConfig())

class BookCreateRequest(BaseModel):
    isbn: str
    title: str
    subtitle: Optional[str] = None
    authors: Optional[str] = None
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    page_count: Optional[int] = 0
    categories: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    initial_copies: Optional[int] = 1
    shelf_id: Optional[int] = None
    price: Optional[float] = 25.0

class BookUpdateRequest(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    authors: Optional[str] = None
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    page_count: Optional[int] = None
    categories: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None

@router.get("/books")
def list_books(
    q: Optional[str] = Query(None, description="Search term for title, isbn, author, publisher"),
    category_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("newest"),
    db: Session = Depends(get_db)
):
    books, total = catalog_service.get_books(
        db=db,
        query=q,
        category_id=category_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by
    )
    return {
        "items": books,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 1
    }

@router.get("/books/{book_id}")
def get_book_details(book_id: int, db: Session = Depends(get_db)):
    book = catalog_service.get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    data = book.to_dict()
    data["copies_list"] = [c.to_dict() for c in book.copies]
    return data

@router.post("/books")
def create_book(
    req: BookCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    book, is_created = catalog_service.create_or_update_book(
        db=db,
        data=req.model_dump(),
        initial_copies=req.initial_copies or 1,
        shelf_id=req.shelf_id,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else "Local"
    )
    return {"success": True, "is_created": is_created, "book": book.to_dict()}

@router.put("/books/{book_id}")
def update_book(
    book_id: int,
    req: BookUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    book = catalog_service.get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")

    update_dict = {k: v for k, v in req.model_dump().items() if v is not None}
    update_dict["isbn"] = book.isbn
    updated_book, _ = catalog_service.create_or_update_book(
        db=db,
        data=update_dict,
        initial_copies=0,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else "Local"
    )
    return {"success": True, "book": updated_book.to_dict()}

@router.delete("/books/{book_id}")
def delete_book(
    book_id: int,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    try:
        success = catalog_service.delete_book(
            db=db,
            book_id=book_id,
            user_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        if not success:
            raise HTTPException(status_code=404, detail="Book not found.")
        return {"success": True, "message": "Book and inventory copies deleted."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/lookup/{isbn}")
def lookup_online_isbn(isbn: str):
    """Queries external book providers without immediately saving to catalog."""
    record = book_service.fetch_by_isbn(isbn)
    if not record:
        raise HTTPException(status_code=404, detail="No metadata found online for this ISBN.")
    return {"success": True, "metadata": record.to_dict()}

@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(Category).order_by(Category.name.asc()).all()
    return [{"id": c.id, "name": c.name, "description": c.description} for c in cats]
