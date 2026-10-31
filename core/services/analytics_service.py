from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session

from ..database.models.catalog import Book, Category, book_categories
from ..database.models.inventory import BookCopy
from ..database.models.circulation import Loan, Fine
from ..database.models.user import User
from ..database.models.system import AuditLog

def get_dashboard_metrics(db: Session) -> Dict[str, Any]:
    """Computes real-time institutional metrics across catalog, inventory, and circulation."""
    now = datetime.now()

    # Total Book Titles
    total_books = db.query(func.count(Book.id)).scalar() or 0

    # Total Physical Copies
    total_copies = db.query(func.count(BookCopy.id)).scalar() or 0

    # Available Copies
    available_copies = db.query(func.count(BookCopy.id)).filter(BookCopy.status == "available").scalar() or 0

    # Active Checked-Out Loans
    issued_loans = db.query(func.count(Loan.id)).filter(Loan.status == "active").scalar() or 0

    # Overdue Loans
    overdue_loans = db.query(func.count(Loan.id)).filter(
        Loan.status == "active",
        Loan.due_date < now
    ).scalar() or 0

    # Registered Active Members
    registered_members = db.query(func.count(User.id)).filter(
        User.role == "member",
        User.is_active == True
    ).scalar() or 0

    # Outstanding Fines
    unpaid_fines_records = db.query(Fine).filter(Fine.status.in_(["unpaid", "partially_paid"])).all()
    unpaid_fines_total = sum(f.amount - f.paid_amount for f in unpaid_fines_records)

    # Category Distribution
    categories = db.query(
        Category.name,
        func.count(book_categories.c.book_id).label("count")
    ).outerjoin(book_categories, Category.id == book_categories.c.category_id).group_by(Category.id).all()
    
    category_data = [{"name": c[0], "count": c[1]} for c in categories]

    # Recent Transactions
    recent_loans_query = db.query(Loan).order_by(desc(Loan.id)).limit(6).all()
    recent_transactions = [l.to_dict() for l in recent_loans_query]

    # Popular Borrowed Books
    popular_books_query = db.query(
        Book.title,
        Book.isbn,
        func.count(Loan.id).label("borrow_count")
    ).join(BookCopy, Book.id == BookCopy.book_id).join(Loan, BookCopy.id == Loan.copy_id).group_by(Book.id).order_by(desc("borrow_count")).limit(5).all()

    popular_books = [
        {"title": pb[0], "isbn": pb[1], "borrow_count": pb[2]} for pb in popular_books_query
    ]

    # Recent System Audit Logs
    recent_audits_query = db.query(AuditLog).order_by(desc(AuditLog.id)).limit(5).all()
    recent_audits = [a.to_dict() for a in recent_audits_query]

    return {
        "kpi": {
            "total_titles": total_books,
            "total_copies": total_copies,
            "available_copies": available_copies,
            "issued_loans": issued_loans,
            "overdue_loans": overdue_loans,
            "registered_members": registered_members,
            "unpaid_fines": round(unpaid_fines_total, 2)
        },
        "category_distribution": category_data,
        "recent_transactions": recent_transactions,
        "popular_books": popular_books,
        "recent_audits": recent_audits
    }
