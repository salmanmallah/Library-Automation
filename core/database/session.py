import os
from typing import Generator, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .base import Base

def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./library_catalog.db")

def build_engine(url: Optional[str] = None):
    db_url = url or get_database_url()
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True
    )

engine = build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency providing a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(custom_engine=None):
    """Initializes all database tables registered with Base metadata."""
    from . import models  # Ensures all ORM models are registered
    target_engine = custom_engine or engine
    Base.metadata.create_all(bind=target_engine)
