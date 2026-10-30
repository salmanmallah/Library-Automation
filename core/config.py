import os
import logging
from typing import Union
from dataclasses import dataclass

@dataclass
class AppConfig:
    camera_index: Union[int, str] = "http://127.0.0.1:8080/video"
    api_base_url: str = "https://www.googleapis.com/books/v1/volumes"
    openlibrary_url: str = "https://openlibrary.org/api/books"
    api_timeout_seconds: int = 5
    api_max_retries: int = 2
    cooldown_seconds: float = 4.0
    worker_threads: int = 4
    csv_file_path: str = "library_catalog.csv"
    db_file_path: str = "library_catalog.db"
    use_sqlite: bool = False
    window_name: str = "Library Automation Scanner"
    host: str = "0.0.0.0"
    port: int = 8000
    open_browser: bool = True

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
