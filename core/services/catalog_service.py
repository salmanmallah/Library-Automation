import logging
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import or_, desc, asc
from sqlalchemy.orm import Session
from ..database.models.catalog import Book, Author, Publisher, Category
from ..database.models.inventory import BookCopy, Shelf
from .audit_service import log_audit_event

logger = logging.getLogger("LibraryAutomation.CatalogService")

def get_books(
    db: Session,
    query: Optional[str] = None,
    category_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "newest"
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated books with search filtering and copy availability metrics."""
    q = db.query(Book)

    if query:
        clean_q = f"%{query.strip()}%"
        q = q.outerjoin(Book.authors).outerjoin(Book.publisher).filter(
            or_(
                Book.title.ilike(clean_q),
                Book.isbn.ilike(clean_q),
                Author.name.ilike(clean_q),
                Publisher.name.ilike(clean_q)
            )
        ).distinct()

    if category_id:
        q = q.join(Book.categories).filter(Category.id == category_id)

    total = q.count()

    if sort_by == "title":
        q = q.order_by(asc(Book.title))
    elif sort_by == "oldest":
        q = q.order_by(asc(Book.created_at))
    else:  # newest
        q = q.order_by(desc(Book.created_at))

    offset = max(0, (page - 1) * page_size)
    books = q.offset(offset).limit(page_size).all()
    return [b.to_dict() for b in books], total

def get_book_by_id(db: Session, book_id: int) -> Optional[Book]:
    return db.query(Book).filter(Book.id == book_id).first()

def get_book_by_isbn(db: Session, isbn: str) -> Optional[Book]:
    clean_isbn = str(isbn).strip().replace("-", "")
    return db.query(Book).filter(Book.isbn == clean_isbn).first()

def create_or_update_book(
    db: Session,
    data: Dict[str, Any],
    initial_copies: int = 1,
    shelf_id: Optional[int] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Tuple[Book, bool]:
    """
    Creates a new book (or updates existing) and automatically provisions initial physical copies.
    Returns (Book, is_created).
    """
    isbn = str(data.get("isbn", "")).strip().replace("-", "")
    existing = get_book_by_isbn(db, isbn)
    is_created = False

    if existing:
        book = existing
        # Update metadata if new values provided
        if "title" in data and data["title"]:
            book.title = data["title"]
        if "description" in data:
            book.description = data["description"]
        if "cover_image_url" in data and data["cover_image_url"]:
            book.cover_image_url = data["cover_image_url"]
    else:
        is_created = True
        # Resolve Publisher
        publisher_name = data.get("publisher", "General Publisher")
        publisher = None
        if publisher_name and publisher_name != "N/A":
            publisher = db.query(Publisher).filter(Publisher.name == publisher_name).first()
            if not publisher:
                publisher = Publisher(name=publisher_name)
                db.add(publisher)
                db.flush()

        book = Book(
            isbn=isbn,
            title=data.get("title", f"Book {isbn}"),
            subtitle=data.get("subtitle"),
            publisher_id=publisher.id if publisher else None,
            publish_date=str(data.get("publish_date", "N/A")),
            page_count=int(data.get("page_count") or 0),
            description=data.get("description", ""),
            cover_image_url=data.get("cover_image_url", ""),
            language=data.get("language", "English")
        )
        db.add(book)
        db.flush()

    # Link Authors
    authors_raw = data.get("authors")
    if authors_raw:
        if isinstance(authors_raw, str):
            authors_list = [a.strip() for a in authors_raw.split(",") if a.strip()]
        elif isinstance(authors_raw, list):
            authors_list = [str(a).strip() for a in authors_raw if str(a).strip()]
        else:
            authors_list = []

        for aname in authors_list:
            if aname in ("Unknown", "N/A"):
                continue
            author = db.query(Author).filter(Author.name == aname).first()
            if not author:
                author = Author(name=aname)
                db.add(author)
                db.flush()
            if author not in book.authors:
                book.authors.append(author)

    # Link Categories
    categories_raw = data.get("categories")
    if categories_raw:
        if isinstance(categories_raw, str):
            cat_list = [c.strip() for c in categories_raw.split(",") if c.strip()]
        elif isinstance(categories_raw, list):
            cat_list = [str(c).strip() for c in categories_raw if str(c).strip()]
        else:
            cat_list = []

        for cname in cat_list:
            cat = db.query(Category).filter(Category.name.ilike(f"%{cname}%")).first()
            if not cat:
                cat = Category(name=cname)
                db.add(cat)
                db.flush()
            if cat not in book.categories:
                book.categories.append(cat)

    # If new book, automatically provision requested initial physical copies
    if is_created and initial_copies > 0:
        default_shelf = None
        if shelf_id:
            default_shelf = db.query(Shelf).filter(Shelf.id == shelf_id).first()
        if not default_shelf:
            default_shelf = db.query(Shelf).first()

        for c_idx in range(1, initial_copies + 1):
            barcode = f"BC-{isbn}-{c_idx:02d}"
            # Check unique barcode
            dup_bc = db.query(BookCopy).filter(BookCopy.copy_barcode == barcode).first()
            if not dup_bc:
                copy = BookCopy(
                    book_id=book.id,
                    copy_barcode=barcode,
                    shelf_id=default_shelf.id if default_shelf else None,
                    status="available",
                    condition="good",
                    price=float(data.get("price") or 25.0)
                )
                db.add(copy)

    db.commit()
    db.refresh(book)

    log_audit_event(
        db,
        action="BOOK_CREATED" if is_created else "BOOK_UPDATED",
        resource_type="BOOK",
        resource_id=str(book.id),
        details={"isbn": book.isbn, "title": book.title, "copies_added": initial_copies if is_created else 0},
        user_id=user_id,
        ip_address=ip_address
    )

    return book, is_created

def delete_book(
    db: Session,
    book_id: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> bool:
    """Deletes a book and associated copies (if none are currently issued)."""
    book = get_book_by_id(db, book_id)
    if not book:
        return False

    # Prevent deletion if any copy is actively checked out
    for copy in book.copies:
        if copy.status == "issued":
            raise ValueError(f"Cannot delete '{book.title}': Copy {copy.copy_barcode} is currently issued to a member.")

    isbn = book.isbn
    title = book.title
    db.delete(book)
    db.commit()

    log_audit_event(
        db,
        action="BOOK_DELETED",
        resource_type="BOOK",
        resource_id=str(book_id),
        details={"isbn": isbn, "title": title},
        user_id=user_id,
        ip_address=ip_address
    )
    return True
