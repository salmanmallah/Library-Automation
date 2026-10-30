import time
import queue
import base64
import logging
import threading
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List, Set
import cv2
import numpy as np
import pyzbar.pyzbar as pyzbar

from .config import AppConfig
from .camera import ThreadedCamera
from .storage import StorageManager
from .book_service import BookService, BookRecord
from .isbn_utils import validate_and_normalize_isbn

logger = logging.getLogger("LibraryAutomation.Engine")

def crop_barcode_b64(frame: np.ndarray, pts: np.ndarray, padding: int = 15) -> str:
    """Crops the physical barcode region from frame and returns a base64 JPEG data URL."""
    try:
        fh, fw = frame.shape[:2]
        x, y, w, h = cv2.boundingRect(pts)
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(fw, x + w + padding)
        y2 = min(fh, y + h + padding)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
            return ""

        # Limit max width to 320px for optimal network & UI payload
        if crop.shape[1] > 320:
            scale = 320.0 / crop.shape[1]
            crop = cv2.resize(crop, (320, int(crop.shape[0] * scale)))

        ret, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret:
            b64_str = base64.b64encode(buffer).decode("utf-8")
            return f"data:image/jpeg;base64,{b64_str}"
    except Exception as e:
        logger.debug(f"Error cropping barcode thumbnail: {e}")
    return ""

class ScannerEngine:
    """
    High-throughput multi-barcode concurrent scanner engine.
    Supports capturing physical barcode snapshots (Samsung/Lens style),
    stable viewfinder brackets, and parallel queue resolution for MUET Central Library.
    """
    def __init__(self, config: AppConfig, storage: StorageManager, book_service: BookService):
        self.config = config
        self.storage = storage
        self.book_service = book_service

        self.camera = ThreadedCamera(config.camera_index)
        self.running = True

        # Independent per-ISBN cooldown tracking: isbn -> timestamp
        self.scanned_cooldowns: Dict[str, float] = {}
        self.cooldown_lock = threading.Lock()

        # In-flight queue tracker: prevents re-queueing while book is being queried
        self.in_flight_isbns: Set[str] = set()
        self.in_flight_lock = threading.Lock()

        # Multi-frame consensus tracker per-ISBN: isbn -> list of timestamps
        self.candidate_history: Dict[str, List[float]] = {}
        self.consensus_threshold = 2  # Must be read in at least 2 distinct frames
        self.consensus_window = 0.8   # Within 0.8 seconds

        # Thread-safe FIFO queue for network verification
        self.isbn_queue: queue.Queue = queue.Queue(maxsize=100)

        # Active barcode detections in current frame for clean stabilized AR rendering
        self.active_detections: List[Dict[str, Any]] = []
        self.detection_lock = threading.Lock()

        # Callbacks for WebSocket notifications
        self.event_callbacks: List[Callable[[Dict[str, Any]], None]] = []

        # Start multi-threaded worker pool for parallel API resolution
        self.worker_threads: List[threading.Thread] = []
        for i in range(self.config.worker_threads):
            t = threading.Thread(target=self._isbn_worker_loop, name=f"MUET-Worker-{i+1}", daemon=True)
            t.start()
            self.worker_threads.append(t)
        logger.info(f"Initialized {len(self.worker_threads)} concurrent ISBN worker threads for MUET Central Library.")

        # Start detection loop
        self.scanner_thread = threading.Thread(target=self._detection_loop, name="ScannerDetectionLoop", daemon=True)
        self.scanner_thread.start()

    def register_callback(self, cb: Callable[[Dict[str, Any]], None]):
        self.event_callbacks.append(cb)

    def unregister_callback(self, cb: Callable[[Dict[str, Any]], None]):
        if cb in self.event_callbacks:
            self.event_callbacks.remove(cb)

    def _broadcast_event(self, event_data: Dict[str, Any]):
        for cb in self.event_callbacks:
            try:
                cb(event_data)
            except Exception as e:
                logger.debug(f"Error in event callback: {e}")

    def _detection_loop(self):
        """Processes video frames, detects all barcodes, captures snapshots, and queues candidates."""
        while self.running:
            if self.camera.is_paused:
                time.sleep(0.1)
                continue

            ret, frame = self.camera.read()
            if not ret or frame is None:
                time.sleep(0.03)
                continue

            try:
                decoded_objects = pyzbar.decode(frame)
                current_time = time.time()

                # Clean up expired consensus candidates
                cutoff = current_time - self.consensus_window
                for c_isbn in list(self.candidate_history.keys()):
                    self.candidate_history[c_isbn] = [t for t in self.candidate_history[c_isbn] if t >= cutoff]
                    if not self.candidate_history[c_isbn]:
                        del self.candidate_history[c_isbn]

                new_detections = []

                # Clean up expired cooldowns periodically
                with self.cooldown_lock:
                    cooldown_cutoff = current_time - (self.config.cooldown_seconds * 2)
                    for k in list(self.scanned_cooldowns.keys()):
                        if self.scanned_cooldowns[k] < cooldown_cutoff:
                            del self.scanned_cooldowns[k]

                # Process all detected barcodes in this single frame
                for obj in decoded_objects:
                    raw_data = obj.data
                    isbn = validate_and_normalize_isbn(raw_data)
                    pts = np.array([point for point in obj.polygon], dtype=np.int32)

                    # Compute a stable axis-aligned bounding box (eliminates shape jumping/warping)
                    bx, by, bw, bh = cv2.boundingRect(pts)

                    status = "non_book"
                    if isbn:
                        if self.storage.is_registered(isbn):
                            status = "registered"
                        else:
                            with self.in_flight_lock:
                                if isbn in self.in_flight_isbns:
                                    status = "verifying"
                                else:
                                    status = "candidate"

                    new_detections.append({
                        "rect": (bx, by, bw, bh),
                        "isbn": isbn or "Non-Book Barcode",
                        "status": status,
                        "timestamp": current_time
                    })

                    # If valid ISBN and not yet registered or in-flight
                    if isbn and status not in ("registered", "verifying"):
                        with self.cooldown_lock:
                            last_scanned = self.scanned_cooldowns.get(isbn, 0.0)
                            if (current_time - last_scanned) < self.config.cooldown_seconds:
                                continue

                        # Track consensus (require 2 frames to prevent glitch)
                        if isbn not in self.candidate_history:
                            self.candidate_history[isbn] = []
                        self.candidate_history[isbn].append(current_time)

                        if len(self.candidate_history[isbn]) >= self.consensus_threshold:
                            self.candidate_history[isbn] = []

                            # Mark in-flight immediately
                            with self.in_flight_lock:
                                if isbn in self.in_flight_isbns or self.storage.is_registered(isbn):
                                    continue
                                self.in_flight_isbns.add(isbn)

                            # Crop physical barcode image (Samsung Galaxy Lens style)
                            barcode_img = crop_barcode_b64(frame, pts)

                            # Broadcast barcode captured event to UI immediately
                            self._broadcast_event({
                                "type": "barcode_captured",
                                "isbn": isbn,
                                "barcode_image": barcode_img,
                                "timestamp": datetime.now().strftime("%H:%M:%S")
                            })

                            # Push to parallel processing queue
                            try:
                                self.isbn_queue.put_nowait({
                                    "isbn": isbn,
                                    "barcode_image": barcode_img
                                })
                                logger.info(f"Queued ISBN for resolution: {isbn} (Queue depth: {self.isbn_queue.qsize()})")
                            except queue.Full:
                                with self.in_flight_lock:
                                    self.in_flight_isbns.discard(isbn)
                                logger.warning(f"ISBN Queue is full. Dropping candidate {isbn}")

                with self.detection_lock:
                    self.active_detections = new_detections

            except Exception as e:
                logger.error(f"Error in barcode detection loop: {e}")

            time.sleep(0.025)

    def _isbn_worker_loop(self):
        """Worker loop executing parallel API lookups from the queue."""
        thread_name = threading.current_thread().name

        while self.running:
            try:
                task = self.isbn_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if isinstance(task, dict):
                isbn = task["isbn"]
                barcode_img = task.get("barcode_image", "")
            else:
                isbn = task
                barcode_img = ""

            current_time = time.time()
            logger.info(f"[{thread_name}] Processing ISBN: {isbn}")

            try:
                if self.storage.is_registered(isbn):
                    logger.info(f"ISBN {isbn} already registered.")
                    self._broadcast_event({
                        "type": "already_registered",
                        "isbn": isbn,
                        "barcode_image": barcode_img,
                        "message": f"ISBN {isbn} is already registered."
                    })
                    continue

                self._broadcast_event({
                    "type": "lookup_started",
                    "isbn": isbn,
                    "barcode_image": barcode_img,
                    "message": f"Verifying {isbn} in library database..."
                })

                # Fetch book metadata (OpenLibrary first, then Google Books)
                record = self.book_service.fetch_by_isbn(isbn)
                if record:
                    saved = self.storage.save_book(record)
                    if saved:
                        logger.info(f"Cataloged: '{record.title}' (ISBN: {isbn})")
                        self._broadcast_event({
                            "type": "book_saved",
                            "status": "success",
                            "isbn": isbn,
                            "barcode_image": barcode_img,
                            "book": record.to_dict(),
                            "message": f"Successfully registered '{record.title}'",
                            "queue_remaining": self.isbn_queue.qsize()
                        })
                    else:
                        self._broadcast_event({
                            "type": "save_error",
                            "isbn": isbn,
                            "message": f"Could not save ISBN {isbn}."
                        })
                else:
                    logger.warning(f"ISBN {isbn} could not be resolved by book APIs (false positive ignored).")
                    self._broadcast_event({
                        "type": "not_found",
                        "isbn": isbn,
                        "barcode_image": barcode_img,
                        "message": f"Barcode {isbn} not found in public book registries (ignored)."
                    })

            except Exception as e:
                logger.error(f"Error resolving ISBN {isbn} in {thread_name}: {e}", exc_info=True)
            finally:
                with self.cooldown_lock:
                    self.scanned_cooldowns[isbn] = current_time

                with self.in_flight_lock:
                    self.in_flight_isbns.discard(isbn)

                self.isbn_queue.task_done()

    def process_manual_isbn(self, isbn: str) -> Dict[str, Any]:
        """Manually trigger an ISBN scan from UI."""
        norm_isbn = validate_and_normalize_isbn(isbn)
        if not norm_isbn:
            return {"success": False, "message": "Invalid ISBN format. Must be 10 or 13 digits starting with 978/979."}

        if self.storage.is_registered(norm_isbn):
            return {"success": False, "message": f"ISBN {norm_isbn} is already registered in MUET Central Library."}

        record = self.book_service.fetch_by_isbn(norm_isbn)
        if not record:
            record = BookRecord(
                isbn=norm_isbn,
                title=f"Manual Book Entry (ISBN: {norm_isbn})",
                authors="Manual Entry",
                publisher="MUET Library",
                publish_date=datetime.now().strftime("%Y"),
                page_count=0,
                categories="General",
                description="Manually added to MUET Central Library catalog.",
                scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                cover_image_url=""
            )

        self.storage.save_book(record)
        self._broadcast_event({
            "type": "book_saved",
            "status": "success",
            "isbn": norm_isbn,
            "book": record.to_dict(),
            "message": f"Registered '{record.title}'"
        })
        return {"success": True, "book": record.to_dict()}

    def generate_annotated_frame(self) -> Optional[np.ndarray]:
        """Generates video frame with clean, professional stabilized corner brackets (Samsung style)."""
        if self.camera.is_paused:
            h, w = 480, 640
            frame = np.full((h, w, 3), 16, dtype=np.uint8)
            cv2.putText(
                frame,
                "SCANNER PAUSED / OFF",
                (140, 230),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 165, 255),
                2
            )
            cv2.putText(
                frame,
                "Click 'Turn Camera ON' in dashboard to resume",
                (100, 270),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (180, 180, 180),
                1
            )
            return frame

        ret, frame = self.camera.read()
        if not ret or frame is None:
            h, w = 480, 640
            placeholder = np.zeros((h, w, 3), dtype=np.uint8)
            cv2.putText(
                placeholder,
                "Connecting to MUET Video Feed...",
                (40, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 165, 255),
                2
            )
            cv2.putText(
                placeholder,
                f"Source: {self.camera.source}",
                (40, 280),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (180, 180, 180),
                1
            )
            return placeholder

        h, w = frame.shape[:2]

        # Draw Clean Center Guide Brackets
        cx, cy = w // 2, h // 2
        rw, rh = int(w * 0.45), int(h * 0.35)
        x1, y1 = cx - rw // 2, cy - rh // 2
        x2, y2 = cx + rw // 2, cy + rh // 2

        line_len = 25
        gold_color = (0, 215, 255)
        cv2.line(frame, (x1, y1), (x1 + line_len, y1), gold_color, 2)
        cv2.line(frame, (x1, y1), (x1, y1 + line_len), gold_color, 2)
        cv2.line(frame, (x2, y1), (x2 - line_len, y1), gold_color, 2)
        cv2.line(frame, (x2, y1), (x2, y1 + line_len), gold_color, 2)
        cv2.line(frame, (x1, y2), (x1 + line_len, y2), gold_color, 2)
        cv2.line(frame, (x1, y2), (x1, y2 - line_len), gold_color, 2)
        cv2.line(frame, (x2, y2), (x2 - line_len, y2), gold_color, 2)
        cv2.line(frame, (x2, y2), (x2, y2 - line_len), neon_cyan := (0, 215, 255), 2)

        # Draw Stabilized, Clean Rectangular Corner Brackets for each detected barcode
        current_time = time.time()
        with self.detection_lock:
            for det in self.active_detections:
                if current_time - det["timestamp"] < 0.8:
                    bx, by, bw, bh = det["rect"]
                    status = det["status"]
                    isbn = det["isbn"]

                    if status == "registered":
                        color = (255, 180, 0)      # Cyan / Neon Blue
                        label = f"Cataloged: {isbn}"
                    elif status == "verifying":
                        color = (0, 215, 255)      # Yellow / Amber
                        label = f"Verifying: {isbn}..."
                    elif status == "candidate":
                        color = (0, 255, 100)      # Emerald / Neon Green
                        label = f"Reading: {isbn}"
                    else:
                        color = (130, 130, 130)    # Slate / Gray
                        label = "Barcode"

                    # Padding around barcode for clean look
                    pad = 6
                    rx1 = max(0, bx - pad)
                    ry1 = max(0, by - pad)
                    rx2 = min(w, bx + bw + pad)
                    ry2 = min(h, by + bh + pad)

                    # Draw 4 neat corner brackets instead of irregular polygon
                    c_len = min(18, (rx2 - rx1) // 3, (ry2 - ry1) // 3)
                    # Top-left
                    cv2.line(frame, (rx1, ry1), (rx1 + c_len, ry1), color, 3)
                    cv2.line(frame, (rx1, ry1), (rx1, ry1 + c_len), color, 3)
                    # Top-right
                    cv2.line(frame, (rx2, ry1), (rx2 - c_len, ry1), color, 3)
                    cv2.line(frame, (rx2, ry1), (rx2, ry1 + c_len), color, 3)
                    # Bottom-left
                    cv2.line(frame, (rx1, ry2), (rx1 + c_len, ry2), color, 3)
                    cv2.line(frame, (rx1, ry2), (rx1, ry2 - c_len), color, 3)
                    # Bottom-right
                    cv2.line(frame, (rx2, ry2), (rx2 - c_len, ry2), color, 3)
                    cv2.line(frame, (rx2, ry2), (rx2, ry2 - c_len), color, 3)

                    # Background pill badge above barcode
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                    badge_w, badge_h = label_size[0] + 12, label_size[1] + 8
                    badge_y1 = max(0, ry1 - badge_h - 4)
                    badge_y2 = badge_y1 + badge_h
                    badge_x2 = min(w, rx1 + badge_w)
                    cv2.rectangle(frame, (rx1, badge_y1), (badge_x2, badge_y2), (20, 24, 33), -1)
                    cv2.rectangle(frame, (rx1, badge_y1), (badge_x2, badge_y2), color, 1)
                    cv2.putText(
                        frame,
                        label,
                        (rx1 + 6, badge_y2 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        color,
                        1,
                        cv2.LINE_AA
                    )

        # MUET Central Library Header Banner Overlay
        cv2.putText(
            frame,
            f"MUET CENTRAL LIBRARY | Multi-Lens v2.3 | FPS: {self.camera.fps}",
            (15, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 215, 255),
            2,
            cv2.LINE_AA
        )

        return frame

    def generate_mjpeg_stream(self):
        """Yields MJPEG stream chunks for FastAPI response."""
        while self.running:
            frame = self.generate_annotated_frame()
            if frame is None:
                time.sleep(0.03)
                continue

            ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                time.sleep(0.02)
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
            time.sleep(0.033)

    def stop(self):
        self.running = False
        self.camera.stop()
