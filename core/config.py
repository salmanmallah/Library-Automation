import os
import logging
from dataclasses import dataclass

@dataclass
class AppConfig:
    camera_index: int = 0
    api_base_url: str = "https://www.googleapis.com/books/v1/volumes"
    api_timeout_seconds: int = 5
    api_max_retries: int = 3
    cooldown_seconds: float = 3.0
    csv_file_path: str = "library_catalog.csv"
    db_file_path: str = "library_catalog.db"
    use_sqlite: bool = False
    window_name: str = "Library Automation Scanner (ESC to Quit)"

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
