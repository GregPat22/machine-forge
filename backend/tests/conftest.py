from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.mock import MockProvider
from app.main import create_app
from app.storage import Storage


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(llm_provider="mock", fx_rates={"USD": 0.9}, template_dir=tmp_path / "templates")


@pytest.fixture
def storage() -> Storage:
    return Storage(":memory:")


@pytest.fixture
def client(settings: Settings, storage: Storage) -> TestClient:
    app = create_app(settings=replace(settings), storage=storage, provider=MockProvider(), connectors=[])
    return TestClient(app)


BLISTER_PROBLEM = "We need to pack 300 tablets per minute into PVC/Alu blisters of 10 for a pharma customer."
