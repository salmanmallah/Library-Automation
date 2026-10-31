from typing import Optional, List
from sqlalchemy import String, Integer, Text, ForeignKey, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, TimestampMixin

# Association table for Many-to-Many relationship between Books and Authors
book_authors = Table(
    "book_authors",
    Base.metadata,
    Column("book_id", Integer, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", Integer, ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True)
)

# Association table for Many-to-Many relationship between Books and Categories
book_categories = Table(
    "book_categories",
    Base.metadata,
    Column("book_id", Integer, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
)

class Author(Base, TimestampMixin):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text)

    books = relationship("Book", secondary=book_authors, back_populates="authors")

class Publisher(Base, TimestampMixin):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255))

    books = relationship("Book", back_populates="publisher")

class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    books = relationship("Book", secondary=book_categories, back_populates="categories")

class Book(Base, TimestampMixin):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    isbn: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(String(255))
    
    publisher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"))
    publish_date: Mapped[Optional[str]] = mapped_column(String(50))
    edition: Mapped[Optional[str]] = mapped_column(String(50))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)
    cover_image_url: Mapped[Optional[str]] = mapped_column(String(500), default="")
    language: Mapped[str] = mapped_column(String(20), default="English")

    # Relationships
    publisher = relationship("Publisher", back_populates="books")
    authors = relationship("Author", secondary=book_authors, back_populates="books")
    categories = relationship("Category", secondary=book_categories, back_populates="books")
    copies = relationship("BookCopy", back_populates="book", cascade="all, delete-orphan")
    reservations = relationship("Reservation", back_populates="book", cascade="all, delete-orphan")

    def to_dict(self):
        author_names = ", ".join(a.name for a in self.authors) if self.authors else "Unknown"
        category_names = ", ".join(c.name for c in self.categories) if self.categories else "General"
        publisher_name = self.publisher.name if self.publisher else "N/A"
        
        total_copies = len(self.copies) if self.copies else 0
        available_copies = sum(1 for c in self.copies if c.status == "available") if self.copies else 0

        return {
            "id": self.id,
            "isbn": self.isbn,
            "title": self.title,
            "subtitle": self.subtitle,
            "authors": author_names,
            "publisher": publisher_name,
            "publish_date": self.publish_date or "N/A",
            "edition": self.edition,
            "page_count": self.page_count,
            "categories": category_names,
            "description": self.description or "",
            "cover_image_url": self.cover_image_url or "",
            "language": self.language,
            "total_copies": total_copies,
            "available_copies": available_copies,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }
