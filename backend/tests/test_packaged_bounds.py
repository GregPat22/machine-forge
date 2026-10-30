"""Build without network access, then exercise the wheel independently of editable source."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def packaged_app(tmp_path_factory):
    root = tmp_path_factory.mktemp("wheel")
    source = root / "source"
    source.mkdir()
    shutil.copytree(BACKEND / "app", source / "app", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(BACKEND / "pyproject.toml", source / "pyproject.toml")
    # Include the old public resource location when testing versions before the packaging fix.
    old_table = BACKEND / "data" / "catalog_bounds.yaml"
    if old_table.is_file():
        (source / "data").mkdir()
        shutil.copyfile(old_table, source / "data" / old_table.name)
    result = subprocess.run([sys.executable, "-m", "pip", "wheel", str(source), "--no-deps",
                             "--no-build-isolation", "--no-index", "--wheel-dir", str(root / "dist")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    [wheel] = (root / "dist").glob("*.whl")
    installed = root / "installed"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(installed)
    return installed


def test_wheel_contains_the_public_catalog_table(packaged_app):
    from app.services.bounds import BOUNDS_PATH

    resources = list(packaged_app.rglob("catalog_bounds.yaml"))
    assert len(resources) == 1, "the wheel must ship exactly one bounds table"
    assert hashlib.sha256(resources[0].read_bytes()).digest() == hashlib.sha256(BOUNDS_PATH.read_bytes()).digest()


@pytest.mark.parametrize("endpoint", ["timing", "diff"])
def test_packaged_result_endpoints_load_their_catalog_without_source_tree(packaged_app, endpoint):
    script = '''
import sys
from pathlib import Path
import app
from fastapi.testclient import TestClient
from app.config import Settings
from app.llm.mock import MockProvider
from app.main import create_app
from app.models import MachineDesign
from app.storage import Storage
assert Path(app.__file__).is_relative_to(Path(sys.argv[1]))
storage = Storage(":memory:")
pid = storage.create_project("Synthetic test", "Reply", MachineDesign(name="Test", machine_type="test", summary="test"))
client = TestClient(create_app(settings=Settings(llm_provider="mock"), storage=storage,
                              provider=MockProvider(), connectors=[]), raise_server_exceptions=False)
response = client.get(f"/api/projects/{pid}/{sys.argv[2]}")
assert response.status_code == 200, (response.status_code, response.text)
'''
    result = subprocess.run([sys.executable, "-c", script, str(packaged_app), endpoint],
                            cwd=packaged_app, env={**os.environ, "PYTHONPATH": str(packaged_app)},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
