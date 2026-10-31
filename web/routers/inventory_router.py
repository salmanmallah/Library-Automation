from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database.session import get_db
from core.database.models.user import User
from core.auth.dependencies import require_roles
from core.services import inventory_service

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])

class CopyCreateRequest(BaseModel):
    book_id: int
    shelf_id: Optional[int] = None
    condition: Optional[str] = "good"
    price: Optional[float] = 25.0
    custom_barcode: Optional[str] = None

class CopyUpdateRequest(BaseModel):
    status: Optional[str] = None
    condition: Optional[str] = None
    shelf_id: Optional[int] = None

class ShelfCreateRequest(BaseModel):
    shelf_code: str
    floor: Optional[str] = "Ground Floor"
    section: Optional[str] = "General"
    capacity: Optional[int] = 50

@router.get("/copies")
def list_copies(
    book_id: Optional[int] = Query(None),
    shelf_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    return inventory_service.get_copies(
        db=db,
        book_id=book_id,
        shelf_id=shelf_id,
        status=status,
        query=q
    )

@router.post("/copies")
def add_copy(
    req: CopyCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    try:
        copy = inventory_service.add_copy(
            db=db,
            book_id=req.book_id,
            shelf_id=req.shelf_id,
            condition=req.condition or "good",
            price=req.price or 0.0,
            custom_barcode=req.custom_barcode,
            user_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "copy": copy.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/copies/{copy_id}")
def update_copy(
    copy_id: int,
    req: CopyUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin", "librarian")),
    db: Session = Depends(get_db)
):
    try:
        updated = inventory_service.update_copy(
            db=db,
            copy_id=copy_id,
            status=req.status,
            condition=req.condition,
            shelf_id=req.shelf_id,
            user_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "copy": updated.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/copies/{copy_id}")
def delete_copy(
    copy_id: int,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin")),
    db: Session = Depends(get_db)
):
    try:
        success = inventory_service.delete_copy(
            db=db,
            copy_id=copy_id,
            user_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        if not success:
            raise HTTPException(status_code=404, detail="Copy not found.")
        return {"success": True, "message": "Physical copy removed from inventory."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/shelves")
def list_shelves(db: Session = Depends(get_db)):
    return inventory_service.get_shelves(db)

@router.post("/shelves")
def create_shelf(
    req: ShelfCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("super_admin", "library_admin")),
    db: Session = Depends(get_db)
):
    try:
        shelf = inventory_service.create_shelf(
            db=db,
            shelf_code=req.shelf_code,
            floor=req.floor or "Ground Floor",
            section=req.section or "General",
            capacity=req.capacity or 50,
            user_id=current_user.id,
            ip_address=request.client.host if request.client else "Local"
        )
        return {"success": True, "shelf": shelf.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
