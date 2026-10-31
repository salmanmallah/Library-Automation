import unittest
from datetime import datetime, timedelta
from core.database.session import SessionLocal, init_db
from core.database.models.user import User
from core.database.models.catalog import Book
from core.database.models.inventory import BookCopy
from core.database.models.circulation import Loan, Fine, Reservation
from core.services import circulation_service, catalog_service
from core.auth.security import hash_password

class TestCirculationService(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = SessionLocal()

        # Create test member
        self.member = self.db.query(User).filter(User.username == "test_borrower").first()
        if not self.member:
            self.member = User(
                username="test_borrower",
                email="borrower@test.edu",
                hashed_password=hash_password("Pass123"),
                full_name="Alice Student",
                role="member",
                member_code="TEST-MEM-01",
                is_active=True,
                max_borrow_limit=2
            )
            self.db.add(self.member)
            self.db.commit()

        # Create test book & copy
        book_data = {
            "isbn": "9780131103627",
            "title": "The C Programming Language",
            "authors": "Brian W. Kernighan, Dennis M. Ritchie",
            "publisher": "Prentice Hall"
        }
        self.book, _ = catalog_service.create_or_update_book(self.db, book_data, initial_copies=1)
        self.copy = self.book.copies[0]

    def tearDown(self):
        self.db.close()

    def test_issue_and_return_workflow(self):
        # 1. Issue copy
        loan = circulation_service.issue_book(
            self.db,
            copy_barcode=self.copy.copy_barcode,
            member_identifier=self.member.member_code,
            custom_loan_days=14
        )
        self.assertEqual(loan.status, "active")
        self.assertEqual(loan.copy.status, "issued")
        self.assertIsNotNone(loan.due_date)

        # 2. Prevent issuing already issued copy
        with self.assertRaises(ValueError):
            circulation_service.issue_book(
                self.db,
                copy_barcode=self.copy.copy_barcode,
                member_identifier=self.member.member_code
            )

        # 3. Return copy on time
        returned_loan, fine = circulation_service.return_book(
            self.db,
            copy_barcode=self.copy.copy_barcode
        )
        self.assertEqual(returned_loan.status, "returned")
        self.assertEqual(self.copy.status, "available")
        self.assertIsNone(fine)  # On-time return incurs no fine

    def test_overdue_fine_calculation(self):
        # Issue loan
        loan = circulation_service.issue_book(
            self.db,
            copy_barcode=self.copy.copy_barcode,
            member_identifier=self.member.member_code,
            custom_loan_days=14
        )

        # Artificially set due_date to 5 days ago to simulate late return
        loan.due_date = datetime.now() - timedelta(days=5)
        self.db.commit()

        # Process return
        returned_loan, fine = circulation_service.return_book(
            self.db,
            copy_barcode=self.copy.copy_barcode
        )
        self.assertIsNotNone(fine)
        self.assertGreaterEqual(fine.amount, 5.0)  # 5 days * $1.0/day
        self.assertEqual(fine.status, "unpaid")

    def test_borrowing_limit_enforcement(self):
        # Member max limit is 2
        # Create second book
        b2, _ = catalog_service.create_or_update_book(
            self.db,
            {"isbn": "9780596007126", "title": "Head First Design Patterns"},
            initial_copies=1
        )
        # Create third book
        b3, _ = catalog_service.create_or_update_book(
            self.db,
            {"isbn": "9781491957660", "title": "Designing Data-Intensive Applications"},
            initial_copies=1
        )

        # Issue 1
        circulation_service.issue_book(self.db, self.copy.copy_barcode, self.member.member_code)
        # Issue 2
        circulation_service.issue_book(self.db, b2.copies[0].copy_barcode, self.member.member_code)

        # Issue 3 must be blocked!
        with self.assertRaises(ValueError) as ctx:
            circulation_service.issue_book(self.db, b3.copies[0].copy_barcode, self.member.member_code)
        self.assertIn("Borrowing limit reached", str(ctx.exception))

        # Cleanup
        circulation_service.return_book(self.db, self.copy.copy_barcode)
        circulation_service.return_book(self.db, b2.copies[0].copy_barcode)

if __name__ == "__main__":
    unittest.main()
