from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.models import PriceListEntry
from app.services.price_list import PriceListError, parse_price_list
from app.suppliers import connector_status

router = APIRouter(tags=["suppliers"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
