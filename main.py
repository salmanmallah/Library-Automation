#!/usr/bin/env python3
"""
Library Automation - Web-based Real-time Barcode / QR Book Cataloging System
High-performance zero-lag inventory scanner with modern reactive web interface.
"""

import os
import sys
import signal
import argparse
import subprocess
import threading
import webbrowser
import uvicorn

from core.config import AppConfig, setup_logger
from core.storage import StorageManager
from core.book_service import BookService

def parse_camera_source(val: str):
    """Parses camera source: integer device index or network stream URL."""
    try:
        return int(val)
    except ValueError:
        return val

def auto_setup_adb_port_forward():
    """Attempts to forward port 8080 if an ADB device is connected."""
    try:
        res = subprocess.run(
            ["adb", "forward", "tcp:8080", "tcp:8080"],
            capture_output=True,
            text=True,
            timeout=3
        )
        if res.returncode == 0:
            print("[ADB Helper] Successfully established ADB port forward tcp:8080 -> tcp:8080")
    except Exception:
        pass

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Library Automation v2.0: Zero-Lag Barcode Scanner & Web Cataloger"
    )
    parser.add_argument(
        "--camera",
        type=parse_camera_source,
        default="http://127.0.0.1:8080/video",
        help="Camera device index (e.g. 0) or stream URL (default: http://127.0.0.1:8080/video)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web server port (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Web server bind host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open web browser on startup"
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
        "--debug",
        action="store_true",
        help="Enable verbose debug logging"
    )
    return parser.parse_args()

def main():
    args = parse_arguments()
    logger = setup_logger(debug=args.debug)

    logger.info("Initializing Library Automation Web System v2.0...")

    # Check for ADB forward if using default mobile port 8080
    if str(args.camera).endswith("8080/video"):
        auto_setup_adb_port_forward()

    try:
        from core.scanner_engine import ScannerEngine
        from web.app import create_app
    except ImportError as e:
        logger.critical(
            f"Missing required dependencies: {e}. "
            "Please run: pip install -r requirements.txt"
        )
        sys.exit(1)

    config = AppConfig(
        camera_index=args.camera,
        csv_file_path=args.output,
        use_sqlite=args.use_sqlite,
        db_file_path=args.db_path,
        cooldown_seconds=args.cooldown,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser
    )

    storage = StorageManager(config)
    book_service = BookService(config)
    engine = ScannerEngine(config, storage, book_service)
    app = create_app(config, storage, book_service, engine)

    # Browser auto-launcher
    if not args.no_browser:
        def open_browser():
            import time
            time.sleep(1.2)
            url = f"http://localhost:{args.port}"
            logger.info(f"Opening web dashboard at {url}...")
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    def signal_handler(sig, frame):
        logger.info("Termination signal received. Shutting down scanner...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\n" + "=" * 60)
    print(f"  LIBRARY AUTOMATION SYSTEM ACTIVE")
    print(f"  Web Dashboard: http://localhost:{args.port}")
    print(f"  Live Camera:   {config.camera_index}")
    print("=" * 60 + "\n")

    # Run Uvicorn ASGI server
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info" if not args.debug else "debug"
    )

if __name__ == "__main__":
    main()
