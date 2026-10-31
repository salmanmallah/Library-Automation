import unittest
from fastapi.testclient import TestClient

from core.config import AppConfig
from core.storage import StorageManager
from core.book_service import BookService
from core.scanner_engine import ScannerEngine
from core.database.session import SessionLocal
from core.database.models.catalog import Book
from web.app import create_app

class TestAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = AppConfig(csv_file_path="test_api_catalog.csv", db_file_path="test_api.db")
        cls.storage = StorageManager(cls.config)
        cls.book_service = BookService(cls.config)
        cls.engine = ScannerEngine(cls.config, cls.storage, cls.book_service)
        cls.app = create_app(cls.config, cls.storage, cls.book_service, cls.engine)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.engine.stop()

    def test_health_check(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["version"], "3.0.0")

    def test_auth_login_success(self):
        res = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@1234"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["role"], "super_admin")

    def test_auth_login_invalid_password(self):
        res = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "WrongPassword999"
        })
        self.assertEqual(res.status_code, 401)

    def test_get_catalog_books(self):
        res = self.client.get("/api/catalog/books?page=1&page_size=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_get_dashboard_analytics(self):
        res = self.client.get("/api/analytics/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("kpi", data)
        self.assertIn("total_titles", data["kpi"])
        self.assertIn("total_copies", data["kpi"])

    def test_export_catalog_csv(self):
        login_res = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@1234"
        })
        token = login_res.json()["access_token"]

        res = self.client.get("/api/analytics/export/csv", headers={
            "Authorization": f"Bearer {token}"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        self.assertIn("ISBN,Title,Authors", res.text)

    def test_manual_isbn_scan(self):
        test_isbn = "9780201485677"  # Refactoring
        # Clean up if already exists
        db = SessionLocal()
        b = db.query(Book).filter(Book.isbn == test_isbn).first()
        if b:
            db.delete(b)
            db.commit()
        db.close()
        self.storage.delete_book(test_isbn)

        res = self.client.post("/api/scanner/manual", json={
            "isbn": test_isbn
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("book", data)

if __name__ == "__main__":
    unittest.main()
