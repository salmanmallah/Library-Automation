import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import AppConfig

logger = logging.getLogger("LibraryAutomation.BookService")

@dataclass
class BookRecord:
    isbn: str
    title: str
    authors: str
    publisher: str
    publish_date: str
    page_count: int
    categories: str
    description: str
    scanned_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class BookService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.session = self._create_resilient_session()

    def _create_resilient_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(
            total=self.config.api_max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_by_isbn(self, isbn: str) -> Optional[BookRecord]:
        """
        Fetches metadata for a given ISBN from Google Books API.
        Returns a BookRecord dataclass or None if not found or on error.
        """
        url = f"{self.config.api_base_url}?q=isbn:{isbn}"
        try:
            logger.debug(f"Querying Google Books API for ISBN: {isbn}")
            response = self.session.get(url, timeout=self.config.api_timeout_seconds)
            response.raise_for_status()
            data = response.json()

            items = data.get("items")
            if not items or len(items) == 0:
                logger.warning(f"No book found on Google Books for ISBN: {isbn}")
                return None

            volume_info = items[0].get("volumeInfo", {})

            # Format authors safely
            raw_authors = volume_info.get("authors", [])
            if isinstance(raw_authors, list):
                authors = ", ".join(raw_authors)
            else:
                authors = str(raw_authors) if raw_authors else "Unknown"

            # Format categories safely
            raw_categories = volume_info.get("categories", [])
            if isinstance(raw_categories, list):
                categories = ", ".join(raw_categories)
            else:
                categories = str(raw_categories) if raw_categories else "General"

            # Get clean description (truncate if abnormally large)
            description = volume_info.get("description", "No description provided.")
            if len(description) > 1000:
                description = description[:997] + "..."

            record = BookRecord(
                isbn=str(isbn),
                title=volume_info.get("title", "Unknown Title"),
                authors=authors or "Unknown",
                publisher=volume_info.get("publisher", "N/A"),
                publish_date=volume_info.get("publishedDate", "N/A"),
                page_count=int(volume_info.get("pageCount") or 0),
                categories=categories,
                description=description,
                scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            logger.info(f"Book fetched: '{record.title}' by {record.authors}")
            return record

        except requests.exceptions.Timeout:
            logger.error(f"Request timed out while querying ISBN {isbn}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error querying Google Books API for ISBN {isbn}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing book data for ISBN {isbn}: {e}", exc_info=True)
            return None
