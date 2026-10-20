"""FastAPI application. Run with: uvicorn app.main:create_app --factory --reload (from backend/)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import projects, suppliers
from app.config import Settings, load_settings
from app.llm import LLMError, LLMNotConfigured, LLMProvider, make_provider
from app.services.designer import ProjectNotFound
from app.services.price_list import PriceListError
from app.storage import Storage
from app.suppliers import SupplierConnector, make_connectors


class AppState:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        provider: LLMProvider | None,
        connectors: list[SupplierConnector],
    ):
        self.settings = settings
        self.storage = storage
        self.connectors = connectors
        self._provider = provider
        self.provider_error: str | None = None
        if provider is None:
            try:
                self._provider = make_provider(settings)
            except LLMNotConfigured as exc:
                self.provider_error = str(exc)

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            raise LLMNotConfigured(self.provider_error or "No AI provider configured.")
        return self._provider


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
    provider: LLMProvider | None = None,
    connectors: list[SupplierConnector] | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Machine Forge", version="0.2.0")
    app.state.mf = AppState(
        settings=settings,
        storage=storage or Storage(settings.db_path),
        provider=provider,
        connectors=make_connectors(settings) if connectors is None else connectors,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LLMNotConfigured)
    async def _not_configured(_: Request, exc: LLMNotConfigured) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(ProjectNotFound)
    async def _not_found(_: Request, exc: ProjectNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(PriceListError)
    async def _bad_price_list(_: Request, exc: PriceListError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    def status() -> dict:
        state: AppState = app.state.mf
        model = state._provider.model if state._provider else None
        return {
            "llm": {
                "provider": settings.llm_provider,
                "model": model,
                "ready": state._provider is not None,
                "error": state.provider_error,
            },
            "base_currency": settings.base_currency,
        }

    app.include_router(projects.router, prefix="/api")
    app.include_router(suppliers.router, prefix="/api")
    return app

