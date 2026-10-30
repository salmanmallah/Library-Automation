#!/usr/bin/env python3
"""
Library Automation - Barcode / QR Book Cataloging System
Production-grade scanner for automated library book inventory.
"""

import sys
import signal
import argparse
from core.config import AppConfig, setup_logger
from core.storage import StorageManager
from core.book_service import BookService

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Library Automation: Real-time ISBN Barcode Scanner & Google Books Cataloger"
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera device index (default: 0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="library_catalog.csv",
        help="Path to CSV catalog file (default: library_catalog.csv)"
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        help="Store records in SQLite database instead of CSV"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="library_catalog.db",
        help="Path to SQLite database file (default: library_catalog.db)"
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=3.0,
        help="Cooldown in seconds before re-scanning the same ISBN (default: 3.0)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Google Books API request timeout in seconds (default: 5)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging"
    )
    return parser.parse_args()

def main():
    args = parse_arguments()
    logger = setup_logger(debug=args.debug)

    logger.info("Initializing Library Automation System...")

    try:
        from core.scanner import BarcodeScanner
    except ImportError as e:
        logger.critical(
            "Missing required dependencies (e.g., opencv-python or pyzbar). "
            "Please run: pip install -r requirements.txt"
        )
        logger.debug(f"Import details: {e}")
        sys.exit(1)

    config = AppConfig(
        camera_index=args.camera,
        csv_file_path=args.output,
        use_sqlite=args.use_sqlite,
        db_file_path=args.db_path,
        cooldown_seconds=args.cooldown,
        api_timeout_seconds=args.timeout
    )

    try:
        storage = StorageManager(config)
        book_service = BookService(config)
        scanner = BarcodeScanner(config, storage, book_service)

        # Handle SIGINT and SIGTERM gracefully
        def signal_handler(sig, frame):
            logger.info("Termination signal received. Exiting gracefully...")
            scanner.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        success = scanner.run()
        if not success:
            sys.exit(1)

    except Exception as e:
        logger.critical(f"Fatal error initializing application: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
