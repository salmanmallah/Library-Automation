from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.scanner_engine import ScannerEngine

router = APIRouter(tags=["Scanner"])

class ManualScanRequest(BaseModel):
    isbn: str

class CameraSwitchRequest(BaseModel):
    source: str

def get_scanner_router(engine: ScannerEngine) -> APIRouter:
    r = APIRouter()

    @r.get("/video_feed")
    def video_feed():
        return StreamingResponse(
            engine.generate_mjpeg_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @r.post("/api/scanner/switch")
    @r.post("/api/camera/switch")
    def switch_camera(req: CameraSwitchRequest):
        source = req.source.strip()
        if source.isdigit():
            source = int(source)
        success = engine.camera.switch_source(source)
        return {"success": success, "source": str(source)}

    @r.post("/api/scanner/toggle")
    @r.post("/api/camera/toggle")
    def toggle_camera():
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
    def scan_manual(req: ManualScanRequest):
        res = engine.process_manual_isbn(req.isbn)
        return res

    return r
