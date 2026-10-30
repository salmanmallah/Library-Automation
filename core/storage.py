import csv
import os
import sqlite3
import threading
import logging
from typing import Set, List, Dict, Any, Optional
from .config import AppConfig
from .book_service import BookRecord

logger = logging.getLogger("LibraryAutomation.Storage")

class StorageManager:
    FIELDNAMES = [
        "isbn",
        "title",
        "authors",
        "publisher",
        "publish_date",
        "page_count",
        "categories",
        "description",
        "cover_image_url",
        "scanned_at"
    ]

    def __init__(self, config: AppConfig):
        self.config = config
        self.lock = threading.Lock()
        self.registered_isbns: Set[str] = set()

        if self.config.use_sqlite:
            self._init_sqlite()
        else:
            self._init_csv()

    def _init_sqlite(self):
        """Initializes SQLite table and populates in-memory cache."""
        try:
            conn = sqlite3.connect(self.config.db_file_path)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS books (
                        isbn TEXT PRIMARY KEY,
                        title TEXT,
                        authors TEXT,
                        publisher TEXT,
                        publish_date TEXT,
                        page_count INTEGER,
                        categories TEXT,
                        description TEXT,
                        cover_image_url TEXT,
                        scanned_at TEXT
                    )
                """)
                conn.commit()
                cursor.execute("SELECT isbn FROM books")
                self.registered_isbns = {row[0] for row in cursor.fetchall()}
            finally:
                conn.close()
            logger.info(f"SQLite database initialized ({len(self.registered_isbns)} books loaded).")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}", exc_info=True)

    def _init_csv(self):
        """Initializes CSV file headers and populates in-memory cache."""
        file_path = self.config.csv_file_path
        try:
            if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                    writer.writeheader()
                logger.info(f"Created new CSV catalog at {file_path}")
            else:
                rows = []
                with open(file_path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames or []
                    for row in reader:
                        isbn_val = row.get("isbn")
                        if isbn_val:
                            self.registered_isbns.add(str(isbn_val).strip())
                            rows.append(row)

                # Migrate header if cover_image_url is missing
                if "cover_image_url" not in fieldnames:
                    with open(file_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES, extrasaction='ignore')
                        writer.writeheader()
                        for r in rows:
                            if "cover_image_url" not in r:
                                r["cover_image_url"] = ""
                            writer.writerow(r)
                    logger.info("Migrated CSV header with cover_image_url column.")

                logger.info(f"CSV catalog loaded ({len(self.registered_isbns)} books in registry).")
        except Exception as e:
            logger.error(f"Failed to initialize CSV storage: {e}", exc_info=True)

    def is_registered(self, isbn: str) -> bool:
        """Fast in-memory check."""
        with self.lock:
            return isbn in self.registered_isbns

    def get_all_books(self) -> List[Dict[str, Any]]:
        """Returns all registered books, newest first."""
        with self.lock:
            if self.config.use_sqlite:
                return self._get_all_sqlite()
            else:
                return self._get_all_csv()

    def _get_all_csv(self) -> List[Dict[str, Any]]:
        file_path = self.config.csv_file_path
        if not os.path.exists(file_path):
            return []
        books = []
        try:
            with open(file_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    books.append(row)
            books.reverse()  # Newest first
            return books
        except Exception as e:
            logger.error(f"Error reading CSV books: {e}")
            return []

    def _get_all_sqlite(self) -> List[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self.config.db_file_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM books ORDER BY scanned_at DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"Error reading SQLite books: {e}")
            return []

    def save_book(self, record: BookRecord) -> bool:
        """Thread-safe saving to persistent storage and cache."""
        with self.lock:
            if record.isbn in self.registered_isbns:
                logger.warning(f"ISBN {record.isbn} is already registered.")
                return False

            success = False
            if self.config.use_sqlite:
                success = self._save_to_sqlite(record)
            else:
                success = self._save_to_csv(record)

            if success:
                self.registered_isbns.add(record.isbn)
            return success

    def _save_to_csv(self, record: BookRecord) -> bool:
        try:
            file_path = self.config.csv_file_path
            file_exists = os.path.exists(file_path) and os.stat(file_path).st_size > 0

            with open(file_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES, extrasaction='ignore')
                if not file_exists:
                    writer.writeheader()
                writer.writerow(record.to_dict())
            logger.info(f"Saved '{record.title}' to CSV catalog.")
            return True
        except Exception as e:
            logger.error(f"Error saving book to CSV: {e}", exc_info=True)
            return False

    def _save_to_sqlite(self, record: BookRecord) -> bool:
        conn = None
        try:
            conn = sqlite3.connect(self.config.db_file_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO books (
                    isbn, title, authors, publisher, publish_date, 
                    page_count, categories, description, cover_image_url, scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.isbn,
                record.title,
                record.authors,
                record.publisher,
                record.publish_date,
                record.page_count,
                record.categories,
                record.description,
                record.cover_image_url,
                record.scanned_at
            ))
            conn.commit()
            logger.info(f"Saved '{record.title}' to SQLite database.")
            return True
        except Exception as e:
            logger.error(f"Error saving book to SQLite: {e}", exc_info=True)
            return False
        finally:
            if conn:
                conn.close()

    def delete_book(self, isbn: str) -> bool:
        with self.lock:
            isbn = str(isbn).strip()
            if isbn not in self.registered_isbns:
                return False

            if self.config.use_sqlite:
                try:
                    conn = sqlite3.connect(self.config.db_file_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM books WHERE isbn = ?", (isbn,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"Error deleting book from SQLite: {e}")
                    return False
            else:
                try:
                    all_books = self._get_all_csv()
                    filtered = [b for b in all_books if b.get("isbn") != isbn]
                    filtered.reverse()
                    file_path = self.config.csv_file_path
                    with open(file_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                        writer.writeheader()
                        for b in filtered:
                            writer.writerow(b)
                except Exception as e:
                    logger.error(f"Error deleting book from CSV: {e}")
                    return False

            self.registered_isbns.discard(isbn)
            return True
