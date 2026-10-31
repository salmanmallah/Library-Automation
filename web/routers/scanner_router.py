import re
import ipaddress
from urllib.parse import urlparse
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.scanner_engine import ScannerEngine
from core.auth.dependencies import require_roles, get_optional_current_user
from core.database.models.user import User

router = APIRouter(tags=["Scanner"])

class ManualScanRequest(BaseModel):
    isbn: str = Field(..., min_length=10, max_length=17, description="ISBN-10 or ISBN-13 format")

class CameraSwitchRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=255, description="Device index or approved stream URL")

def validate_camera_source(source: str):
    """Prevents SSRF and cloud metadata access in camera switching while supporting local webcams and IP cameras."""
    clean = source.strip()
    if clean.isdigit():
        idx = int(clean)
        if 0 <= idx <= 10:
            return idx
        raise HTTPException(status_code=400, detail="Camera index must be between 0 and 10.")

    # URL format validation
    url_pattern = re.compile(r'^(http|https|rtsp)://[a-zA-Z0-9.-]+(:[0-9]+)?(/.*)?$', re.IGNORECASE)
    if not url_pattern.match(clean):
        raise HTTPException(
            status_code=400,
            detail="Invalid camera source. Must be a device index (0, 1) or valid HTTP/HTTPS/RTSP stream URL."
        )

    parsed = urlparse(clean)
    hostname = (parsed.hostname or "").lower()

    # Block cloud instance metadata services (AWS, GCP, Azure, OpenStack)
    cloud_metadata_hosts = {"169.254.169.254", "169.254.169.253", "metadata.google.internal", "instance-data"}
    if hostname in cloud_metadata_hosts:
        raise HTTPException(status_code=400, detail="Prohibited network destination: cloud metadata access is forbidden.")

    # Check for link-local IP
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_link_local:
            raise HTTPException(status_code=400, detail="Prohibited network destination: link-local addresses are forbidden.")
    except ValueError:
        pass

    return clean

def get_scanner_router(engine: ScannerEngine) -> APIRouter:
    r = APIRouter()

    @r.get("/video_feed")
    def video_feed():
        """MJPEG stream endpoint for video feed."""
        return StreamingResponse(
            engine.generate_mjpeg_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @r.post("/api/scanner/switch")
    @r.post("/api/camera/switch")
    @r.post("/api/scanner/camera/switch")
    def switch_camera(
        req: CameraSwitchRequest,
        current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian"))
    ):
        validated_source = validate_camera_source(req.source)
        success = engine.camera.switch_source(validated_source)
        return {"success": success, "source": str(validated_source)}

    @r.post("/api/scanner/toggle")
    @r.post("/api/camera/toggle")
    def toggle_camera(
        current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian"))
    ):
        is_paused = engine.camera.toggle_pause()
        return {"is_paused": is_paused, "status": "paused" if is_paused else "active"}

    @r.get("/api/scanner/status")
    @r.get("/api/camera/status")
    def camera_status():
        return {
            "is_paused": engine.camera.is_paused,
            "source": str(engine.camera.source),
            "fps": engine.camera.fps
        }

    @r.post("/api/scanner/manual")
    @r.post("/api/scan_manual")
    def scan_manual(
        req: ManualScanRequest,
        current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian"))
    ):
        res = engine.process_manual_isbn(req.isbn)
        return res

    return r
