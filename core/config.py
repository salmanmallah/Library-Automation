import os
import logging
from typing import Union
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    # Institution Branding
    institution_name: str = os.getenv("INSTITUTION_NAME", "Institutional Central Library")
    
    # Camera & Vision Engine
    camera_index: Union[int, str] = os.getenv("CAMERA_INDEX", "http://127.0.0.1:8080/video")
    cooldown_seconds: float = float(os.getenv("COOLDOWN_SECONDS", "3.0"))
    worker_threads: int = int(os.getenv("WORKER_THREADS", "4"))
    window_name: str = "Library Automation Scanner"
    
    # External Metadata APIs
    openlibrary_url: str = "https://openlibrary.org/api/books"
    api_base_url: str = "https://www.googleapis.com/books/v1/volumes"
    api_timeout_seconds: int = 5
    api_max_retries: int = 2

    # Database Configuration (PostgreSQL / SQLite)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./library_catalog.db")
    db_file_path: str = os.getenv("SQLITE_PATH", "library_catalog.db")
    use_sqlite: bool = True
    csv_file_path: str = os.getenv("CSV_PATH", "library_catalog.csv")
    
    # Security & JWT Authentication
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "library-automation-super-secret-key-change-in-prod-2026")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))  # 24 hours
    
    # Circulation Policy & Business Rules
    default_loan_days: int = int(os.getenv("DEFAULT_LOAN_DAYS", "14"))
    fine_per_day: float = float(os.getenv("FINE_PER_DAY", "1.0"))
    max_loans_per_member: int = int(os.getenv("MAX_LOANS_PER_MEMBER", "5"))
    max_renewals_per_loan: int = int(os.getenv("MAX_RENEWALS_PER_LOAN", "2"))
    reservation_expiry_days: int = int(os.getenv("RESERVATION_EXPIRY_DAYS", "3"))

    # Server Networking
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    open_browser: bool = True
    debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")

def setup_logger(debug: bool = False) -> logging.Logger:
    """Configures and returns a centralized application logger."""
    level = logging.DEBUG if debug else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("LibraryAutomation")
