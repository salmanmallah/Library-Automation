import os
import json
import asyncio
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from core.config import AppConfig
from core.storage import StorageManager
from core.book_service import BookService
from core.scanner_engine import ScannerEngine
from core.database.session import init_db, SessionLocal
from core.database.seeder import seed_database
from core.auth.dependencies import require_roles
from core.database.models.user import User

# Routers
from .routers.auth_router import router as auth_router
from .routers.catalog_router import router as catalog_router
from .routers.inventory_router import router as inventory_router
from .routers.circulation_router import router as circulation_router
from .routers.analytics_router import router as analytics_router
from .routers.users_router import router as users_router
from .routers.audit_router import router as audit_router
from .routers.scanner_router import get_scanner_router

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
    # Validate production security settings
    config.validate_security()

    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 1. Initialize relational database and seed baseline institutional data
        init_db()
        db = SessionLocal()
        try:
            seed_database(db, csv_migration_path=config.csv_file_path)
        finally:
            db.close()

        # 2. Bind event loop for real-time WebSocket broadcasting
        ws_manager.loop = asyncio.get_running_loop()
        yield

    app = FastAPI(
        title=f"{config.institution_name} - Platform",
        version="3.0.0",
        lifespan=lifespan
    )

    # Security Headers Middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    # Strict CORS configuration (removes wildcard with credentials)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Health Check endpoint
    @app.get("/healthz")
    def health_check():
        return {
            "status": "healthy",
            "version": "3.0.0",
            "environment": config.environment,
            "camera_connected": engine.camera.is_connected,
            "camera_fps": engine.camera.fps
        }

    # Bridge ScannerEngine sync events to async WebSocket broadcast
    # Filters out any private member data to prevent telemetry leakage
    def on_engine_event(event_data: dict):
        if ws_manager.loop and ws_manager.loop.is_running():
            try:
                # Sanitized public event
                safe_event = {
                    "type": event_data.get("type"),
                    "isbn": event_data.get("isbn"),
                    "barcode_image": event_data.get("barcode_image", ""),
                    "timestamp": event_data.get("timestamp", ""),
                    "message": event_data.get("message", ""),
                    "book": event_data.get("book")
                }
                asyncio.run_coroutine_threadsafe(ws_manager.broadcast(safe_event), ws_manager.loop)
            except Exception:
                pass

    engine.register_callback(on_engine_event)

    # Mount API Routers
    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(inventory_router)
    app.include_router(circulation_router)
    app.include_router(analytics_router)
    app.include_router(users_router)
    app.include_router(audit_router)
    app.include_router(get_scanner_router(engine))

    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    # --- Backward Compatibility Endpoints with strict RBAC enforcement ---
    @app.get("/api/books")
    def get_legacy_books():
        return storage.get_all_books()

    @app.delete("/api/books/{isbn}")
    def delete_legacy_book(
        isbn: str,
        current_user: User = Depends(require_roles("super_admin", "library_admin"))
    ):
        success = storage.delete_book(isbn)
        if not success:
            raise HTTPException(status_code=404, detail="Book not found")
        on_engine_event({
            "type": "book_deleted",
            "isbn": isbn,
            "message": f"Book {isbn} was deleted from catalog."
        })
        return {"success": True, "isbn": isbn}

    @app.get("/api/export")
    def export_legacy_csv(
        current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian"))
    ):
        from .routers.analytics_router import export_catalog_csv
        db = SessionLocal()
        try:
            return export_catalog_csv(db=db, current_user=current_user)
        finally:
            db.close()

    # WebSocket connection endpoint
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
