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
    cover_image_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class BookService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.session = self._create_resilient_session()

    def _create_resilient_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "LibraryAutomationSystem/2.0 (BookScanner; Windows NT 10.0)"
        })
        retries = Retry(
            total=1,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_by_isbn(self, isbn: str) -> Optional[BookRecord]:
        """
        Fetches metadata for an ISBN using OpenLibrary first, with Google Books fallback.
        Guarantees fast response without blocking threads. Returns None if not found.
        """
        clean_isbn = str(isbn).strip().replace("-", "")

        # 1. Try OpenLibrary API (fast, reliable, free covers, no 429 locks)
        record = self._fetch_openlibrary(clean_isbn)
        if record:
            return record

        # 2. Try Google Books API as fallback
        record = self._fetch_google_books(clean_isbn)
        if record:
            return record

        logger.info(f"Book not found in online catalogs for ISBN {clean_isbn}.")
        return None

    def _fetch_openlibrary(self, isbn: str) -> Optional[BookRecord]:
        try:
            url = f"{self.config.openlibrary_url}?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
            logger.debug(f"Querying OpenLibrary for ISBN: {isbn}")
            res = self.session.get(url, timeout=self.config.api_timeout_seconds)
            if res.status_code != 200:
                return None

            data = res.json()
            key = f"ISBN:{isbn}"
            if key not in data:
                return None

            info = data[key]
            title = info.get("title", f"Book {isbn}")
            
            authors_list = [a.get("name") for a in info.get("authors", []) if "name" in a]
            authors = ", ".join(authors_list) if authors_list else "Unknown"

            publishers_list = [p.get("name") for p in info.get("publishers", []) if "name" in p]
            publisher = ", ".join(publishers_list) if publishers_list else "N/A"

            publish_date = str(info.get("publish_date", "N/A"))
            page_count = int(info.get("number_of_pages") or 0)

            subjects_list = [s.get("name") for s in info.get("subjects", []) if isinstance(s, dict) and "name" in s][:3]
            categories = ", ".join(subjects_list) if subjects_list else "General"

            covers = info.get("cover", {})
            cover_url = covers.get("medium") or covers.get("large") or covers.get("small") or ""

            description = "N/A"
            notes = info.get("notes")
            if notes and isinstance(notes, str):
                description = notes[:500]

            record = BookRecord(
                isbn=isbn,
                title=title,
                authors=authors,
                publisher=publisher,
                publish_date=publish_date,
                page_count=page_count,
                categories=categories,
                description=description,
                scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                cover_image_url=cover_url
            )
            logger.info(f"OpenLibrary matched: '{record.title}' by {record.authors}")
            return record

        except Exception as e:
            logger.debug(f"OpenLibrary query skipped/failed for {isbn}: {e}")
            return None

    def _fetch_google_books(self, isbn: str) -> Optional[BookRecord]:
        try:
            url = f"{self.config.api_base_url}?q=isbn:{isbn}"
            logger.debug(f"Querying Google Books for ISBN: {isbn}")
            res = self.session.get(url, timeout=self.config.api_timeout_seconds)
            if res.status_code != 200:
                return None

            data = res.json()
            items = data.get("items", [])
            if not items:
                return None

            volume_info = items[0].get("volumeInfo", {})
            raw_authors = volume_info.get("authors", [])
            authors = ", ".join(raw_authors) if isinstance(raw_authors, list) else str(raw_authors)

            raw_categories = volume_info.get("categories", [])
            categories = ", ".join(raw_categories) if isinstance(raw_categories, list) else str(raw_categories)

            desc = volume_info.get("description", "No description provided.")
            if len(desc) > 500:
                desc = desc[:497] + "..."

            image_links = volume_info.get("imageLinks", {})
            cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
            if cover_url.startswith("http://"):
                cover_url = "https://" + cover_url[7:]

            record = BookRecord(
                isbn=isbn,
                title=volume_info.get("title", f"Book {isbn}"),
                authors=authors or "Unknown",
                publisher=volume_info.get("publisher", "N/A"),
                publish_date=volume_info.get("publishedDate", "N/A"),
                page_count=int(volume_info.get("pageCount") or 0),
                categories=categories or "General",
                description=desc,
                scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                cover_image_url=cover_url
            )
            logger.info(f"Google Books matched: '{record.title}' by {record.authors}")
            return record

        except Exception as e:
            logger.debug(f"Google Books query failed for {isbn}: {e}")
            return None
