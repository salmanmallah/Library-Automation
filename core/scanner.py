import time
import logging
import cv2
import pyzbar.pyzbar as pyzbar

from .config import AppConfig
from .isbn_utils import validate_and_normalize_isbn
from .book_service import BookService
from .storage import StorageManager
from .visualizer import HUDVisualizer

logger = logging.getLogger("LibraryAutomation.Scanner")

class BarcodeScanner:
    def __init__(self, config: AppConfig, storage: StorageManager, book_service: BookService):
        self.config = config
        self.storage = storage
        self.book_service = book_service
        self.visualizer = HUDVisualizer()

        self.last_scanned_isbn = None
        self.last_scanned_time = 0.0
        self.running = False

    def process_barcode_data(self, raw_data: bytes, polygon=None, frame=None):
        isbn = validate_and_normalize_isbn(raw_data)
        if not isbn:
            logger.debug(f"Non-ISBN barcode detected: {raw_data}")
            return

        current_time = time.time()
        # Cooldown check to prevent repeated requests
        if isbn == self.last_scanned_isbn and (current_time - self.last_scanned_time) < self.config.cooldown_seconds:
            return

        self.last_scanned_isbn = isbn
        self.last_scanned_time = current_time

        logger.info(f"Detected valid ISBN: {isbn}")

        # Check if already in catalog
        if self.storage.is_registered(isbn):
            logger.info(f"ISBN {isbn} already exists in library catalog.")
            self.visualizer.set_status(f"Already Registered: ISBN {isbn}", "warning")
            return

        # Fetch book details
        self.visualizer.set_status(f"Fetching metadata for ISBN {isbn}...", "info")
        record = self.book_service.fetch_by_isbn(isbn)

        if record:
            saved = self.storage.save_book(record)
            if saved:
                msg = f"Saved: {record.title[:30]}..." if len(record.title) > 30 else f"Saved: {record.title}"
                self.visualizer.set_status(msg, "success")
            else:
                self.visualizer.set_status(f"Error saving ISBN {isbn}", "error")
        else:
            self.visualizer.set_status(f"No details found for ISBN {isbn}", "error")

    def run(self):
        """Starts video capture and real-time processing loop."""
        logger.info(f"Opening camera index {self.config.camera_index}...")
        cam = cv2.VideoCapture(self.config.camera_index)

        if not cam.isOpened():
            logger.critical(f"Unable to open camera index {self.config.camera_index}. Please check device connection.")
            return False

        self.running = True
        logger.info("Scanner started successfully. Press ESC or Q in the window to quit.")

        try:
            while self.running:
                ret, frame = cam.read()
                if not ret or frame is None:
                    logger.warning("Failed to grab video frame. Retrying in 100ms...")
                    time.sleep(0.1)
                    continue

                decoded_objects = pyzbar.decode(frame)

                for obj in decoded_objects:
                    # Draw polygon around barcode
                    self.visualizer.draw_barcode_polygon(frame, obj.polygon)
                    # Process detected barcode
                    self.process_barcode_data(obj.data, obj.polygon, frame)

                # Render HUD overlay
                frame = self.visualizer.draw_hud(frame)

                cv2.imshow(self.config.window_name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q'), ord('Q')):
                    logger.info("Exit key pressed by user.")
                    break

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Stopping...")
        finally:
            self.running = False
            cam.release()
            cv2.destroyAllWindows()
            logger.info("Camera released and display windows closed.")

        return True
