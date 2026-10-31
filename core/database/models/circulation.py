from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, TimestampMixin

class Loan(Base, TimestampMixin):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    copy_id: Mapped[int] = mapped_column(Integer, ForeignKey("book_copies.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    issued_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    
    issue_date: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    return_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Statuses: active, returned, overdue
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)
    renewal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    copy = relationship("BookCopy", back_populates="loans")
    member = relationship("User", foreign_keys=[member_id], back_populates="loans")
    issued_by = relationship("User", foreign_keys=[issued_by_id], back_populates="issued_loans")
    fines = relationship("Fine", back_populates="loan", cascade="all, delete-orphan")

    def to_dict(self):
        copy_barcode = self.copy.copy_barcode if self.copy else "N/A"
        book_title = self.copy.book.title if self.copy and self.copy.book else "Unknown Book"
        book_isbn = self.copy.book.isbn if self.copy and self.copy.book else "N/A"
        member_name = self.member.full_name if self.member else "Unknown Member"
        member_code = self.member.member_code if self.member else "N/A"
        issued_by_name = self.issued_by.full_name if self.issued_by else "System"

        # Dynamically evaluate overdue status if active
        now = datetime.now()
        effective_status = self.status
        if self.status == "active" and self.due_date and now > self.due_date:
            effective_status = "overdue"

        return {
            "id": self.id,
            "copy_id": self.copy_id,
            "copy_barcode": copy_barcode,
            "book_title": book_title,
            "book_isbn": book_isbn,
            "member_id": self.member_id,
            "member_name": member_name,
            "member_code": member_code,
            "issued_by_name": issued_by_name,
            "issue_date": self.issue_date.strftime("%Y-%m-%d %H:%M") if self.issue_date else None,
            "due_date": self.due_date.strftime("%Y-%m-%d") if self.due_date else None,
            "return_date": self.return_date.strftime("%Y-%m-%d %H:%M") if self.return_date else None,
            "status": effective_status,
            "renewal_count": self.renewal_count
        }

class Reservation(Base, TimestampMixin):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    reserved_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    expiry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Statuses: pending, fulfilled, cancelled, expired
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    book = relationship("Book", back_populates="reservations")
    member = relationship("User", back_populates="reservations")

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "book_title": self.book.title if self.book else "Unknown",
            "book_isbn": self.book.isbn if self.book else "",
            "member_id": self.member_id,
            "member_name": self.member.full_name if self.member else "Unknown",
            "member_code": self.member.member_code if self.member else "",
            "reserved_at": self.reserved_at.strftime("%Y-%m-%d %H:%M") if self.reserved_at else None,
            "expiry_date": self.expiry_date.strftime("%Y-%m-%d") if self.expiry_date else None,
            "status": self.status,
            "priority": self.priority
        }

class Fine(Base, TimestampMixin):
    __tablename__ = "fines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    loan_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("loans.id", ondelete="SET NULL"), index=True)
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Statuses: unpaid, partially_paid, paid, waived
    status: Mapped[str] = mapped_column(String(20), default="unpaid", index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="Overdue return fine")

    # Relationships
    loan = relationship("Loan", back_populates="fines")
    member = relationship("User", back_populates="fines")

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "member_id": self.member_id,
            "member_name": self.member.full_name if self.member else "Unknown",
            "member_code": self.member.member_code if self.member else "",
            "amount": self.amount,
            "paid_amount": self.paid_amount,
            "balance": max(0.0, self.amount - self.paid_amount),
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None
        }
