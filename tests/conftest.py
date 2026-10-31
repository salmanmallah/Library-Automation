import os
import tempfile
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from core.database.base import Base
from core.database.session import get_db
from core.database.seeder import seed_database
from core.database.models import User, Book, BookCopy, Shelf, Category, Loan, Fine, Reservation
from core.auth.security import hash_password, create_access_token
from core.config import AppConfig
from core.storage import StorageManager
from core.book_service import BookService
from core.camera import ThreadedCamera
from core.scanner_engine import ScannerEngine
from web.app import create_app
from unittest.mock import patch

@pytest.fixture(scope="session", autouse=True)
def mock_threaded_camera_stream():
    """Prevents OpenCV from attempting to open hardware webcams or hanging on network sockets during tests."""
    with patch.object(ThreadedCamera, "_start_stream", return_value=None):
        yield

@pytest.fixture(scope="session")
def test_engine():
    """Creates an isolated in-memory SQLite database engine shared across session threads."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provides a transactional database session rolled back after every individual test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestingSessionLocal()

    # Seed baseline taxonomy & accounts
    seed_database(session, csv_migration_path="non_existent.csv")

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Provides a FastAPI application instance with get_db overridden to use test_session."""
    config = AppConfig(
        database_url="sqlite:///:memory:",
        jwt_secret_key="test-secret-key-for-isolated-testing-only",
        institution_name="Test University Library"
    )
    storage = StorageManager(config)
    book_service = BookService(config)
    engine = ScannerEngine(config, storage, book_service)
    
    app = create_app(config, storage, book_service, engine)
    
    # Override get_db dependency
    app.dependency_overrides[get_db] = lambda: db_session
    
    yield app
    
    engine.stop()
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def client(test_app) -> Generator[TestClient, None, None]:
    """Provides a TestClient targeting the isolated test application."""
    with TestClient(test_app) as c:
        yield c

@pytest.fixture(scope="function")
def admin_token(db_session: Session) -> str:
    admin = db_session.query(User).filter(User.username == "admin").first()
    return create_access_token({"sub": str(admin.id), "role": admin.role, "name": admin.full_name})

@pytest.fixture(scope="function")
def librarian_token(db_session: Session) -> str:
    lib = db_session.query(User).filter(User.username == "librarian").first()
    return create_access_token({"sub": str(lib.id), "role": lib.role, "name": lib.full_name})

@pytest.fixture(scope="function")
def member_token(db_session: Session) -> str:
    mem = db_session.query(User).filter(User.username == "student1").first()
    return create_access_token({"sub": str(mem.id), "role": mem.role, "name": mem.full_name})
