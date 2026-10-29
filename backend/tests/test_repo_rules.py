"""Repository-wide checks for docs/engineering-rules.md. They read source files, never the network."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO / "frontend" / "src"


def _frontend_sources() -> list[Path]:
    return sorted(p for p in FRONTEND_SRC.rglob("*") if p.suffix in (".ts", ".tsx"))


def test_frontend_does_not_import_the_deleted_render() -> None:
    """Rule 4: the procedural render was removed in Phase 0 and must not come back by import."""
    assert FRONTEND_SRC.is_dir()
    assert not (FRONTEND_SRC / "render").exists(), "frontend/src/render/ was deleted in Phase 0"
    offenders = []
    pattern = re.compile(r"""from\s+["'][^"']*(?:/render/|MachineRender)[^"']*["']""")
    for source in _frontend_sources():
        if pattern.search(source.read_text(encoding="utf-8")):
            offenders.append(str(source.relative_to(REPO)))
    assert offenders == [], f"files import the deleted render: {offenders}"


BACKEND_APP = REPO / "backend" / "app"

# Free-text fields of the design (and the same names on other models). Logic must not branch on them.
_TEXT = r"(?:name|function|summary|description|target_rate_text|machine_type)"
_NAME_LOGIC = [
    re.compile(rf"\.{_TEXT}\b.*(?:\.lower\(|\.upper\(|\.casefold\(|\.toLowerCase\(|\.toUpperCase\()"),
    re.compile(rf"\.{_TEXT}\??\.(?:startswith|endswith|find|index|split|includes|startsWith|endsWith|indexOf|match|search)\("),
    re.compile(rf"\.{_TEXT}\b\s*(?:===|!==|==|!=)"),
    re.compile(rf"(?:===|!==|==|!=)\s*[\w.\[\]?]+\.{_TEXT}\b"),
    re.compile(rf"\.{_TEXT}\s+(?:not\s+)?in\b"),
    re.compile(rf"\bin\s+[\w.\[\]]+\.{_TEXT}\b"),
    re.compile(rf"\bre\.\w+\(.*\.{_TEXT}\b"),
    re.compile(rf"\.test\(.*\.{_TEXT}\b"),
]

# Display-only or not a design field: (file, text on the line, reason). Every entry must still match.
_NAME_LOGIC_ALLOWED = [
    ("backend/app/storage.py", "key=lambda s: s.name.lower()", "sorts suppliers for display"),
    ("backend/app/services/patch.py", "if parameter.name in parameter_names", "Parameter.name is the parameter key"),
    ("backend/app/services/patch.py", "if p.name == op.name", "Parameter.name is the parameter key"),
    ("backend/app/services/sourcing.py", "if connector.name in errors", "connector id, frozen module"),
    ("frontend/src/components/PlcView.tsx", "f.name ===", "generated PLC file name"),
    ("frontend/src/components/SupplierRatings.tsx", "x.name === s.name", "supplier, parking lot"),
    ("frontend/src/pages/Suppliers.tsx", "v?.toLowerCase().includes(q)", "text search typed by the user"),
]


def _logic_sources() -> list[Path]:
    return sorted(BACKEND_APP.rglob("*.py")) + _frontend_sources()


def test_no_logic_branches_on_display_names() -> None:
    """Rule 1: no comparison, keyword or regex test on a name or other free text decides behaviour."""
    offenders, used = [], set()
    for source in _logic_sources():
        rel = str(source.relative_to(REPO))
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if not any(p.search(line) for p in _NAME_LOGIC):
                continue
            allowed = [i for i, (path, text, _) in enumerate(_NAME_LOGIC_ALLOWED) if path == rel and text in line]
            if allowed:
                used.update(allowed)
            else:
                offenders.append(f"{rel}:{number}: {line.strip()}")
    assert offenders == [], "logic reads a display name or free text (rule 1):\n" + "\n".join(offenders)
    stale = [entry for i, entry in enumerate(_NAME_LOGIC_ALLOWED) if i not in used]
    assert stale == [], f"allowlist entries that match nothing any more: {stale}"


ENGINES = BACKEND_APP / "engines"
_IO_MODULES = ("sqlite3", "httpx", "yaml", "pathlib", "os", "app.storage", "app.llm")


def _imported_modules(tree: ast.AST) -> list[str]:
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_engines_do_no_io() -> None:
    """Rule 5: engines are pure. No I/O import, no open(), no `except ...: pass` under app/engines/."""
    sources = sorted(ENGINES.rglob("*.py"))
    assert any(p.name != "__init__.py" for p in sources), "app/engines/ has no engine to check"
    offenders = []
    for source in sources:
        rel = source.relative_to(REPO)
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(rel))
        for module in _imported_modules(tree):
            if any(module == m or module.startswith(m + ".") for m in _IO_MODULES):
                offenders.append(f"{rel}: imports {module}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Name) and func.id == "open") or (
                    isinstance(func, ast.Attribute) and func.attr == "open"
                ):
                    offenders.append(f"{rel}:{node.lineno}: calls open(")
            if isinstance(node, ast.ExceptHandler) and all(isinstance(s, ast.Pass) for s in node.body):
                offenders.append(f"{rel}:{node.lineno}: except ...: pass")
    assert offenders == [], "engines must do no I/O (rule 5):\n" + "\n".join(offenders)
