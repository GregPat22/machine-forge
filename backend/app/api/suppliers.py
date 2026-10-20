from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.models import PriceListEntry, SupplierInfo, SupplierRating
from app.services.documents import validate_template
from app.services.price_list import PriceListError, parse_price_list
from app.suppliers import connector_status

router = APIRouter(tags=["suppliers"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
TEMPLATE_NAME = "documents.docx"


@router.get("/price-list", response_model=list[PriceListEntry])
def get_price_list(request: Request) -> list[PriceListEntry]:
    return request.app.state.mf.storage.price_list()


@router.post("/price-list")
async def upload_price_list(
    request: Request, file: UploadFile = File(...), append: bool = Form(False)
) -> dict[str, int]:
    state = request.app.state.mf
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise PriceListError("File too large (max 20 MB).")
    entries = parse_price_list(file.filename or "upload.csv", data, state.settings.base_currency)
    imported = state.storage.replace_price_list(entries, append=append)
    return {"imported": imported, "total": len(state.storage.price_list())}


@router.get("/connectors")
def connectors(request: Request) -> list[dict]:
    return [asdict(s) for s in connector_status(request.app.state.mf.settings)]


# --- supplier ratings ------------------------------------------------------------------------------


class RatingIn(BaseModel):
    quality: int | None = Field(default=None, ge=1, le=5)
    delivery: int | None = Field(default=None, ge=1, le=5)
    preferred: bool = False
    notes: str | None = None


@router.get("/suppliers", response_model=list[SupplierInfo])
def suppliers(request: Request) -> list[SupplierInfo]:
    return request.app.state.mf.storage.suppliers()


@router.put("/suppliers/{name}", response_model=SupplierRating)
def rate_supplier(name: str, body: RatingIn, request: Request) -> SupplierRating:
    if not name.strip():
        raise HTTPException(status_code=400, detail="Supplier name is empty")
    rating = SupplierRating(name=name.strip(), **body.model_dump())
    request.app.state.mf.storage.set_rating(rating)
    return rating


# --- company document template ---------------------------------------------------------------------


@router.get("/templates/document")
def template_status(request: Request) -> dict:
    path = request.app.state.mf.settings.template_dir / TEMPLATE_NAME
    if not path.is_file():
        return {"exists": False}
    stat = path.stat()
    return {"exists": True, "size": stat.st_size,
            "uploaded_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}


@router.post("/templates/document")
async def upload_template(request: Request, file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Upload a .docx file.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 20 MB).")
    try:
        validate_template(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    directory = request.app.state.mf.settings.template_dir
    directory.mkdir(parents=True, exist_ok=True)
    (directory / TEMPLATE_NAME).write_bytes(data)
    return template_status(request)


@router.delete("/templates/document", status_code=204)
def delete_template(request: Request) -> Response:
    (request.app.state.mf.settings.template_dir / TEMPLATE_NAME).unlink(missing_ok=True)
    return Response(status_code=204)
