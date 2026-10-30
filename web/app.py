import os
import json
import asyncio
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from pydantic import BaseModel

from core.config import AppConfig
from core.storage import StorageManager
from core.book_service import BookService
from core.scanner_engine import ScannerEngine

class ManualScanRequest(BaseModel):
    isbn: str

class CameraSwitchRequest(BaseModel):
    source: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        text = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text)
            except Exception:
                self.disconnect(connection)

def create_app(config: AppConfig, storage: StorageManager, book_service: BookService, engine: ScannerEngine) -> FastAPI:
    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ws_manager.loop = asyncio.get_running_loop()
        yield

    app = FastAPI(title="Library Automation Server", lifespan=lifespan)

    # Bridge ScannerEngine sync events to async WebSocket broadcast
    def on_engine_event(event_data: dict):
        if ws_manager.loop and ws_manager.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(ws_manager.broadcast(event_data), ws_manager.loop)
            except Exception:
                pass

    engine.register_callback(on_engine_event)

    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/video_feed")
    def video_feed():
        return StreamingResponse(
            engine.generate_mjpeg_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @app.get("/api/books")
    def get_books():
        return storage.get_all_books()

    @app.post("/api/scan_manual")
    def scan_manual(req: ManualScanRequest):
        res = engine.process_manual_isbn(req.isbn)
        return res

    @app.delete("/api/books/{isbn}")
    def delete_book(isbn: str):
        success = storage.delete_book(isbn)
        if not success:
            raise HTTPException(status_code=404, detail="Book not found")
        return {"success": True, "isbn": isbn}

    @app.get("/api/export")
    def export_csv():
        if not os.path.exists(config.csv_file_path):
            raise HTTPException(status_code=404, detail="Catalog file not found")
        return FileResponse(
            path=config.csv_file_path,
            filename="library_catalog.csv",
            media_type="text/csv"
        )

    @app.post("/api/camera/switch")
    def switch_camera(req: CameraSwitchRequest):
        source = req.source.strip()
        if source.isdigit():
            source = int(source)
        success = engine.camera.switch_source(source)
        return {"success": success, "source": str(source)}

    @app.post("/api/camera/toggle")
    def toggle_camera():
        is_paused = engine.camera.toggle_pause()
        return {"is_paused": is_paused, "status": "paused" if is_paused else "active"}

    @app.get("/api/camera/status")
    def camera_status():
        return {
            "is_paused": engine.camera.is_paused,
            "source": str(engine.camera.source),
            "fps": engine.camera.fps
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception:
            ws_manager.disconnect(websocket)

    return app
