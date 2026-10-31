import io
import csv
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.catalog import Book
from core.database.models.user import User
from core.auth.dependencies import get_current_user, require_roles
from core.services import analytics_service

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Reports"])

@router.get("/dashboard")
def get_dashboard_data(db: Session = Depends(get_db)):
    """Returns real-time institutional KPIs and circulation metrics."""
    return analytics_service.get_dashboard_metrics(db)

@router.get("/export/csv")
def export_catalog_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian"))
):
    """
    Dynamically generates and exports a clean CSV of the entire catalog and physical inventory.
    Guarantees fresh database data whether using SQLite or PostgreSQL.
    """
    books = db.query(Book).order_by(Book.id.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ISBN",
        "Title",
        "Authors",
        "Publisher",
        "Publish Date",
        "Pages",
        "Categories",
        "Total Copies",
        "Available Copies",
        "Cover Image URL",
        "Created At"
    ])

    for b in books:
        authors = ", ".join(a.name for a in b.authors) if b.authors else "Unknown"
        categories = ", ".join(c.name for c in b.categories) if b.categories else "General"
        publisher = b.publisher.name if b.publisher else "N/A"
        total_copies = len(b.copies) if b.copies else 0
        available_copies = sum(1 for c in b.copies if c.status == "available") if b.copies else 0

        writer.writerow([
            b.isbn,
            b.title,
            authors,
            publisher,
            b.publish_date or "N/A",
            b.page_count,
            categories,
            total_copies,
            available_copies,
            b.cover_image_url or "",
            b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else ""
        ])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="institutional_library_catalog.csv"'}
    )
