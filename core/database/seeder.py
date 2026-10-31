import os
import csv
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models.user import User
from .models.catalog import Author, Publisher, Category, Book, book_authors, book_categories
from .models.inventory import Shelf, BookCopy
from .models.circulation import Loan, Reservation, Fine
from .models.system import AuditLog, SystemSetting
from ..auth.security import hash_password

logger = logging.getLogger("LibraryAutomation.Seeder")

def seed_database(db: Session, csv_migration_path: str = "library_catalog.csv"):
    """Seeds initial administrative roles, standard taxonomy, shelves, and migrates legacy CSV books."""
    try:
        # 1. Seed System Settings
        default_settings = [
            ("institution_name", "MUET Central Library & Information Center", "Institutional Name"),
            ("default_loan_days", "14", "Standard loan duration in days"),
            ("fine_per_day", "1.0", "Fine accumulated per overdue day"),
            ("max_loans_per_member", "5", "Maximum active loans permitted per member"),
            ("max_renewals_per_loan", "2", "Maximum renewals allowed per loan"),
            ("reservation_expiry_days", "3", "Days before uncollected reservation expires")
        ]
        for key, val, desc in default_settings:
            existing = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not existing:
                db.add(SystemSetting(key=key, value=val, description=desc))
        db.commit()

        # 2. Seed Default Accounts
        # Super Admin
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@muet.edu.pk",
                hashed_password=hash_password("Admin@1234"),
                full_name="Chief Library Administrator",
                role="super_admin",
                member_code="ADMIN-001",
                department="Library Administration",
                is_active=True,
                max_borrow_limit=20
            )
            db.add(admin_user)
            logger.info("Seeded default Super Admin ('admin' / 'Admin@1234')")

        # Librarian
        librarian_user = db.query(User).filter(User.username == "librarian").first()
        if not librarian_user:
            librarian_user = User(
                username="librarian",
                email="librarian@muet.edu.pk",
                hashed_password=hash_password("Lib@1234"),
                full_name="Senior Circulation Librarian",
                role="librarian",
                member_code="LIB-101",
                department="Circulation Services",
                is_active=True,
                max_borrow_limit=10
            )
            db.add(librarian_user)
            logger.info("Seeded default Librarian ('librarian' / 'Lib@1234')")

        # Student / Member
        student_user = db.query(User).filter(User.username == "student1").first()
        if not student_user:
            student_user = User(
                username="student1",
                email="salman.mallah@student.muet.edu.pk",
                hashed_password=hash_password("Student@1234"),
                full_name="Salman Mallah",
                role="member",
                member_code="20SW01",
                department="Software Engineering",
                is_active=True,
                max_borrow_limit=5
            )
            db.add(student_user)
            logger.info("Seeded sample student member ('student1' / 'Student@1234')")

        db.commit()

        # 3. Seed Shelves
        shelves_data = [
            ("CS-STACK-A1", "1st Floor", "Computer Systems Stack", 60),
            ("SE-STACK-B2", "1st Floor", "Software Engineering Section", 50),
            ("EE-STACK-C1", "2nd Floor", "Electrical & Telecom Section", 45),
            ("MATH-STACK-D", "2nd Floor", "Basic Sciences & Mathematics", 40),
            ("REF-ROOM-01", "Ground Floor", "Reserved Reference Room", 30)
        ]
        created_shelves = {}
        for code, floor, sec, cap in shelves_data:
            sh = db.query(Shelf).filter(Shelf.shelf_code == code).first()
            if not sh:
                sh = Shelf(shelf_code=code, floor=floor, section=sec, capacity=cap)
                db.add(sh)
                db.flush()
            created_shelves[code] = sh
        db.commit()

        # 4. Seed Standard Categories
        categories_data = [
            ("Computer Science", "Algorithms, Systems, and Software Architecture"),
            ("Software Engineering", "Agile, Clean Code, Testing, and System Design"),
            ("Data Science & AI", "Machine Learning, Deep Learning, and Analytics"),
            ("Electrical Engineering", "Circuits, Telecommunications, and Embedded Systems"),
            ("General Fiction & Literature", "Novels, Classic Stories, and Children's Fiction")
        ]
        created_categories = {}
        for cname, cdesc in categories_data:
            cat = db.query(Category).filter(Category.name == cname).first()
            if not cat:
                cat = Category(name=cname, description=cdesc)
                db.add(cat)
                db.flush()
            created_categories[cname] = cat
        db.commit()

        # 5. Migrate Legacy CSV Books into Relational Schema if table is empty
        book_count = db.query(Book).count()
        if book_count == 0 and os.path.exists(csv_migration_path):
            logger.info(f"Migrating legacy CSV records from {csv_migration_path}...")
            with open(csv_migration_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    isbn = str(row.get("isbn", "")).strip().replace("-", "")
                    title = row.get("title", f"Book {isbn}").strip()
                    if not isbn:
                        continue

                    # Check if already exists
                    if db.query(Book).filter(Book.isbn == isbn).first():
                        continue

                    # Handle Publisher
                    pub_name = row.get("publisher", "General Publisher").strip()
                    publisher = db.query(Publisher).filter(Publisher.name == pub_name).first()
                    if not publisher and pub_name and pub_name != "N/A":
                        publisher = Publisher(name=pub_name)
                        db.add(publisher)
                        db.flush()

                    new_book = Book(
                        isbn=isbn,
                        title=title,
                        publisher_id=publisher.id if publisher else None,
                        publish_date=row.get("publish_date", "N/A"),
                        page_count=int(row.get("page_count") or 0),
                        description=row.get("description", ""),
                        cover_image_url=row.get("cover_image_url", ""),
                        language="English"
                    )
                    db.add(new_book)
                    db.flush()

                    # Handle Authors
                    raw_authors = row.get("authors", "")
                    if raw_authors:
                        for aname in raw_authors.split(","):
                            aname = aname.strip()
                            if not aname or aname == "Unknown":
                                continue
                            author = db.query(Author).filter(Author.name == aname).first()
                            if not author:
                                author = Author(name=aname)
                                db.add(author)
                                db.flush()
                            if author not in new_book.authors:
                                new_book.authors.append(author)

                    # Handle Category
                    cat_name = row.get("categories", "General Fiction & Literature").strip()
                    matched_cat = db.query(Category).filter(Category.name.ilike(f"%{cat_name}%")).first()
                    if not matched_cat:
                        matched_cat = created_categories.get("General Fiction & Literature")
                    if matched_cat and matched_cat not in new_book.categories:
                        new_book.categories.append(matched_cat)

                    # Automatically generate 3 physical copies for each migrated book!
                    default_shelf = created_shelves.get("CS-STACK-A1") or list(created_shelves.values())[0]
                    for copy_num in range(1, 4):
                        copy_bc = f"BC-{isbn}-{copy_num:02d}"
                        copy = BookCopy(
                            book_id=new_book.id,
                            copy_barcode=copy_bc,
                            shelf_id=default_shelf.id,
                            status="available",
                            condition="good",
                            price=25.0
                        )
                        db.add(copy)

            db.commit()
            logger.info("Legacy CSV migration to relational database completed successfully.")

        # If still no books in database, add standard initial benchmark books
        if db.query(Book).count() == 0:
            sample_books = [
                {
                    "isbn": "9780132350884",
                    "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
                    "authors": ["Robert C. Martin"],
                    "publisher": "Prentice Hall",
                    "publish_date": "2008",
                    "page_count": 464,
                    "category": "Software Engineering",
                    "description": "Even bad code can function. But if code isn't clean, it can bring a development organization to its knees.",
                    "cover_image_url": "https://covers.openlibrary.org/b/id/15126503-M.jpg",
                    "shelf": "SE-STACK-B2",
                    "copies": 4
                },
                {
                    "isbn": "9780201633610",
                    "title": "Design Patterns: Elements of Reusable Object-Oriented Software",
                    "authors": ["Erich Gamma", "Richard Helm", "Ralph Johnson", "John Vlissides"],
                    "publisher": "Addison-Wesley",
                    "publish_date": "1994",
                    "page_count": 395,
                    "category": "Computer Science",
                    "description": "Capturing a wealth of experience about the design of object-oriented software.",
                    "cover_image_url": "https://covers.openlibrary.org/b/id/14548483-M.jpg",
                    "shelf": "CS-STACK-A1",
                    "copies": 3
                }
            ]

            for binfo in sample_books:
                pub = db.query(Publisher).filter(Publisher.name == binfo["publisher"]).first()
                if not pub:
                    pub = Publisher(name=binfo["publisher"])
                    db.add(pub)
                    db.flush()

                book = Book(
                    isbn=binfo["isbn"],
                    title=binfo["title"],
                    publisher_id=pub.id,
                    publish_date=binfo["publish_date"],
                    page_count=binfo["page_count"],
                    description=binfo["description"],
                    cover_image_url=binfo["cover_image_url"]
                )
                db.add(book)
                db.flush()

                for aname in binfo["authors"]:
                    author = db.query(Author).filter(Author.name == aname).first()
                    if not author:
                        author = Author(name=aname)
                        db.add(author)
                        db.flush()
                    book.authors.append(author)

                cat = db.query(Category).filter(Category.name == binfo["category"]).first()
                if cat:
                    book.categories.append(cat)

                shelf = created_shelves.get(binfo["shelf"])
                for i in range(1, binfo["copies"] + 1):
                    copy = BookCopy(
                        book_id=book.id,
                        copy_barcode=f"BC-{book.isbn}-{i:02d}",
                        shelf_id=shelf.id if shelf else None,
                        status="available",
                        condition="good",
                        price=35.0
                    )
                    db.add(copy)

            db.commit()
            logger.info("Seeded initial benchmark books with multiple physical copies.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding database: {e}", exc_info=True)
