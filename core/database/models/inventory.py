from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, TimestampMixin

class Shelf(Base, TimestampMixin):
    __tablename__ = "shelves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shelf_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    floor: Mapped[str] = mapped_column(String(50), default="Ground Floor")
    section: Mapped[str] = mapped_column(String(100), default="General Stack")
    capacity: Mapped[int] = mapped_column(Integer, default=50)

    copies = relationship("BookCopy", back_populates="shelf")

    def to_dict(self):
        current_count = len(self.copies) if self.copies else 0
        return {
            "id": self.id,
            "shelf_code": self.shelf_code,
            "floor": self.floor,
            "section": self.section,
            "capacity": self.capacity,
            "current_count": current_count
        }

class BookCopy(Base, TimestampMixin):
    __tablename__ = "book_copies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    copy_barcode: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    shelf_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("shelves.id", ondelete="SET NULL"), index=True)
    
    # Statuses: available, issued, reserved, maintenance, lost
    status: Mapped[str] = mapped_column(String(25), default="available", index=True, nullable=False)
    # Conditions: new, good, fair, damaged
    condition: Mapped[str] = mapped_column(String(25), default="good")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    book = relationship("Book", back_populates="copies")
    shelf = relationship("Shelf", back_populates="copies")
    loans = relationship("Loan", back_populates="copy", cascade="all, delete-orphan")

    def to_dict(self):
        shelf_info = self.shelf.shelf_code if self.shelf else "Unassigned"
        book_title = self.book.title if self.book else "Unknown Book"
        book_isbn = self.book.isbn if self.book else ""

        return {
            "id": self.id,
            "book_id": self.book_id,
            "book_title": book_title,
            "book_isbn": book_isbn,
            "copy_barcode": self.copy_barcode,
            "shelf_id": self.shelf_id,
            "shelf_code": shelf_info,
            "status": self.status,
            "condition": self.condition,
            "price": self.price,
            "acquired_at": self.acquired_at.strftime("%Y-%m-%d %H:%M:%S") if self.acquired_at else None
        }
