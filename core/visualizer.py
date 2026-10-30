import time
from typing import List, Tuple, Optional, Any
import cv2
import numpy as np

class HUDVisualizer:
    def __init__(self):
        self.status_message: str = "Ready. Point camera at barcode or QR code."
        self.status_color: Tuple[int, int, int] = (255, 255, 255)  # White (BGR)
        self.status_timestamp: float = time.time()
        self.message_duration: float = 4.0

    def set_status(self, message: str, status_type: str = "info"):
        self.status_message = message
        self.status_timestamp = time.time()
        
        if status_type == "success":
            self.status_color = (0, 220, 0)      # Green
        elif status_type == "warning":
            self.status_color = (0, 215, 255)    # Yellow/Amber
        elif status_type == "error":
            self.status_color = (0, 0, 255)      # Red
        else:
            self.status_color = (255, 255, 255)  # White

    def draw_barcode_polygon(self, frame: np.ndarray, polygon: List[Any], color: Tuple[int, int, int] = (0, 255, 0)):
        """Draws bounding polygon around detected barcode."""
        if polygon and len(polygon) >= 4:
            pts = np.array([(p.x, p.y) for p in polygon], dtype=np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=3)

    def draw_hud(self, frame: np.ndarray) -> np.ndarray:
        """Renders HUD status bar overlay at the top of the video feed."""
        h, w, _ = frame.shape
        overlay = frame.copy()

        # Top banner background (semi-transparent)
        cv2.rectangle(overlay, (0, 0), (w, 55), (25, 25, 25), -1)
        # Bottom guide background
        cv2.rectangle(overlay, (0, h - 35), (w, h), (20, 20, 20), -1)

        alpha = 0.75
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Draw status message
        current_time = time.time()
        display_msg = self.status_message
        color = self.status_color
        if (current_time - self.status_timestamp) > self.message_duration:
            display_msg = "Ready to scan. Point at an ISBN Barcode / QR."
            color = (200, 200, 200)

        cv2.putText(
            frame,
            display_msg,
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2,
            cv2.LINE_AA
        )

        # Draw footer info
        cv2.putText(
            frame,
            "Press [ESC] or [Q] to Exit",
            (15, h - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 180, 180),
            1,
            cv2.LINE_AA
        )
        return frame
