from typing import Optional, List
from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Roles: super_admin, library_admin, librarian, member
    role: Mapped[str] = mapped_column(String(20), default="member", index=True, nullable=False)
    member_code: Mapped[Optional[str]] = mapped_column(String(30), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(25))
    department: Mapped[Optional[str]] = mapped_column(String(100), default="General")
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_borrow_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Relationships
    loans = relationship("Loan", foreign_keys="Loan.member_id", back_populates="member")
    issued_loans = relationship("Loan", foreign_keys="Loan.issued_by_id", back_populates="issued_by")
    reservations = relationship("Reservation", back_populates="member")
    fines = relationship("Fine", back_populates="member")
    audit_logs = relationship("AuditLog", back_populates="user")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "member_code": self.member_code,
            "phone": self.phone,
            "department": self.department,
            "is_active": self.is_active,
            "max_borrow_limit": self.max_borrow_limit,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }
