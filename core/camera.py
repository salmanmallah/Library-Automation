import time
import logging
import threading
from typing import Union, Tuple, Optional
import cv2
import numpy as np

logger = logging.getLogger("LibraryAutomation.Camera")

class ThreadedCamera:
    """
    High-performance zero-latency threaded camera reader.
    Continuously pulls the latest frame from the hardware/network stream
    in an isolated thread, preventing OpenCV internal buffer lag.
    """
    def __init__(self, source: Union[int, str]):
        self.source = source
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.running = False
        self.is_paused = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

        self.fps = 0.0
        self._frame_count = 0
        self._fps_start_time = time.time()
        self.is_connected = False

        self._start_stream()

    def _start_stream(self):
        logger.info(f"Connecting to camera source: {self.source}...")
        try:
            if isinstance(self.source, int):
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(self.source)

            if self.cap and self.cap.isOpened():
                # Set smallest buffer to minimize latency
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.is_connected = True
                self.running = True
                self.thread = threading.Thread(target=self._capture_worker, daemon=True)
                self.thread.start()
                logger.info(f"Camera reader thread started successfully for {self.source}")
            else:
                logger.warning(f"Could not open camera stream: {self.source}")
                self.is_connected = False
        except Exception as e:
            logger.error(f"Error opening camera {self.source}: {e}", exc_info=True)
            self.is_connected = False

    def _capture_worker(self):
        consecutive_failures = 0
        while self.running:
            if self.is_paused:
                time.sleep(0.1)
                continue

            if not self.cap or not self.cap.isOpened():
                time.sleep(0.5)
                continue

            ret, frame = self.cap.read()
            if ret and frame is not None:
                consecutive_failures = 0
                self.is_connected = True
                with self.lock:
                    self.latest_frame = frame

                # FPS calculation
                self._frame_count += 1
                now = time.time()
                elapsed = now - self._fps_start_time
                if elapsed >= 1.0:
                    self.fps = round(self._frame_count / elapsed, 1)
                    self._frame_count = 0
                    self._fps_start_time = now
            else:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    self.is_connected = False
                    logger.warning(f"Camera stream disconnected ({self.source}). Retrying in 1s...")
                    time.sleep(1.0)
                    try:
                        self.cap.release()
                        if isinstance(self.source, int):
                            self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
                        else:
                            self.cap = cv2.VideoCapture(self.source)
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        consecutive_failures = 0
                    except Exception:
                        pass
                time.sleep(0.02)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Returns the single freshest frame without any buffer lag."""
        if self.is_paused:
            return False, None

        with self.lock:
            if self.latest_frame is None or not self.is_connected:
                return False, None
            return True, self.latest_frame.copy()

    def toggle_pause(self) -> bool:
        """Toggles between paused and active camera states."""
        self.is_paused = not self.is_paused
        logger.info(f"Camera paused state: {self.is_paused}")
        return self.is_paused

    def switch_source(self, new_source: Union[int, str]) -> bool:
        """Dynamically switches camera input source."""
        logger.info(f"Switching camera source to: {new_source}")
        self.stop()
        self.source = new_source
        self.latest_frame = None
        self._start_stream()
        return self.is_connected

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        self.is_connected = False

    def __del__(self):
        self.stop()
