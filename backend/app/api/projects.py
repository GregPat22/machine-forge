from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.api.suppliers import TEMPLATE_NAME
from app.llm import LLMError, LLMNotConfigured
from app.llm.base import Progress, ProgressFn
from app.models import MachineDesign, Project, ProjectSummary, Revision, SourcingReport, SparePart
from app.services.designer import Designer, ProjectNotFound
from app.services.diff import DesignDiff, diff_designs
from app.services.documents import TechnicalDocument, build_document, to_docx, to_markdown
from app.services.drawing import to_dxf, to_svg
from app.services.layout import Layout, compute_layout
from app.services.project_json import ProjectImportError, export_project, import_project
from app.services.plc import PlcProject, to_plcopen_xml
from app.services.plc import generate as generate_plc
from app.services.plc import to_zip as plc_to_zip
from app.services.rfq import build_rfq
from app.services.sourcing import Sourcing
from app.services.spare_parts import build_catalog, catalog_csv
from app.storage import RevisionConflict

router = APIRouter(tags=["projects"])
log = logging.getLogger(__name__)
KEEPALIVE_S = 15


class NewProject(BaseModel):
    problem: str = Field(min_length=10, description="The production problem the machine must solve")


class PromptIn(BaseModel):
    message: str = Field(min_length=1)


def _designer(request: Request) -> Designer:
    state = request.app.state.mf
    return Designer(state.storage, state.provider, max_attempts=state.settings.max_repair_attempts)


def _revision(request: Request, project_id: str, number: int | None) -> Revision:
    storage = request.app.state.mf.storage
    if number is None:
        project = storage.get_project(project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        number = project.latest_revision
    revision = storage.get_revision(project_id, number)
    if revision is None:
        raise ProjectNotFound(f"Revision {number} of project {project_id} not found")
    return revision


def _design_out(design: MachineDesign) -> dict:
    """The design as the API returns it: the stored fields plus, per station, the read-only
    values derived from the model (`sequence`, `cycle_time_s`, ADR 0012) for display."""
    data = design.model_dump(mode="json")
    for station, out in zip(design.stations, data["stations"], strict=True):
        out["sequence"] = station.sequence
        out["cycle_time_s"] = station.cycle_time_s
    return data


def _project_out(project: Project) -> dict:
    return {**project.model_dump(mode="json"), "design": _design_out(project.design)}


def _revision_out(revision: Revision) -> dict:
    return {**revision.model_dump(mode="json"), "design": _design_out(revision.design)}


# Endpoints that call the model are plain `def`: FastAPI runs them in a worker thread.
# Endpoints that return a design return `_project_out`/`_revision_out` dicts, not the models.


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(request: Request) -> list[ProjectSummary]:
    return request.app.state.mf.storage.list_projects()


@router.post("/projects", status_code=201)
def create_project(body: NewProject, request: Request) -> dict:
    return _project_out(_designer(request).create(body.problem.strip()))


@router.post("/projects/import", status_code=201)
async def import_project_file(request: Request) -> dict:
    """Create a new project from a project JSON file (the request body). Never overwrites."""
    state = request.app.state.mf
    limit = state.settings.max_import_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"File is {declared} bytes; the import limit is {limit} bytes.")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise HTTPException(status_code=413, detail=f"File is larger than the import limit of {limit} bytes.")
    try:
        # Parsing and validating up to the size limit is CPU work: keep it off the event loop.
        project_id = await run_in_threadpool(import_project, state.storage, bytes(body), max_bytes=limit)
    except ProjectImportError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    project = await run_in_threadpool(state.storage.get_project, project_id)
    return _project_out(project)


def _event_stream(run: Callable[[ProgressFn], Project]) -> StreamingResponse:
    """Run a design call in a thread and stream its progress as server-sent events.

    Events: `progress` (Progress), then exactly one of `done` (Project) or `error` ({status, detail}).
    """
    events: queue.Queue[tuple[str, object]] = queue.Queue()

    def on_progress(progress: Progress) -> None:
        events.put(("progress", progress))

    def worker() -> None:
        try:
            events.put(("done", _project_out(run(on_progress))))
        except LLMNotConfigured as exc:
            events.put(("error", {"status": 503, "detail": str(exc)}))
        except LLMError as exc:
            events.put(("error", {"status": 502, "detail": str(exc)}))
        except ProjectNotFound as exc:
            events.put(("error", {"status": 404, "detail": str(exc)}))
        except RevisionConflict as exc:
            events.put(("error", {"status": 409, "detail": str(exc)}))
        except Exception:  # never leave the client waiting on a dead stream
            log.exception("design call failed")
            events.put(("error", {"status": 500, "detail": "Unexpected server error, see the backend log."}))

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            try:
                kind, payload = events.get(timeout=KEEPALIVE_S)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
            if kind in ("done", "error"):
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/projects/stream")
def create_project_stream(body: NewProject, request: Request) -> StreamingResponse:
    designer = _designer(request)  # raises 503 before streaming if no AI is configured
    problem = body.problem.strip()
    return _event_stream(lambda progress: designer.create(problem, on_progress=progress))


@router.post("/projects/{project_id}/prompt/stream")
def prompt_stream(project_id: str, body: PromptIn, request: Request) -> StreamingResponse:
    designer = _designer(request)
    designer._get(project_id)  # 404 before streaming
    message = body.message.strip()
    return _event_stream(lambda progress: designer.refine(project_id, message, on_progress=progress))


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict:
    project = request.app.state.mf.storage.get_project(project_id)
    if project is None:
        raise ProjectNotFound(f"Project {project_id} not found")
    return _project_out(project)


@router.get("/projects/{project_id}/export")
def export(project_id: str, request: Request) -> Response:
    storage = request.app.state.mf.storage
    project = storage.get_project(project_id)
    if project is None:
        raise ProjectNotFound(f"Project {project_id} not found")
    payload = json.dumps(export_project(project, storage.list_revisions(project_id)), indent=2)
    return Response(
        payload, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="machine-forge-{project_id}.json"'},
    )


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request) -> Response:
    if not request.app.state.mf.storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)


@router.post("/projects/{project_id}/prompt")
def prompt(project_id: str, body: PromptIn, request: Request) -> dict:
    return _project_out(_designer(request).refine(project_id, body.message.strip()))


@router.get("/projects/{project_id}/revisions")
def revisions(project_id: str, request: Request) -> list[dict]:
    return [_revision_out(r) for r in request.app.state.mf.storage.list_revisions(project_id)]


@router.post("/projects/{project_id}/revisions/{number}/restore")
def restore(project_id: str, number: int, request: Request) -> dict:
    return _project_out(Designer(request.app.state.mf.storage).restore(project_id, number))


@router.get("/projects/{project_id}/spare-parts", response_model=list[SparePart])
def spare_parts(project_id: str, request: Request, revision: int | None = None) -> list[SparePart]:
    return build_catalog(_revision(request, project_id, revision).design)


@router.get("/projects/{project_id}/spare-parts.csv")
def spare_parts_csv(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    return Response(
        content=catalog_csv(build_catalog(rev.design)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="spare-parts-{project_id}-r{rev.number}.csv"'},
    )


@router.get("/projects/{project_id}/layout", response_model=Layout)
def layout(project_id: str, request: Request, revision: int | None = None) -> Layout:
    return compute_layout(_revision(request, project_id, revision).design)


@router.get("/projects/{project_id}/layout.svg")
def layout_svg(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    return Response(content=to_svg(compute_layout(rev.design), rev.design, rev.number), media_type="image/svg+xml")


@router.get("/projects/{project_id}/layout.dxf")
def layout_dxf(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    return Response(
        content=to_dxf(compute_layout(rev.design), rev.design, rev.number),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="layout-{project_id}-r{rev.number}.dxf"'},
    )


@router.get("/projects/{project_id}/diff", response_model=DesignDiff)
def diff(project_id: str, request: Request, to: int | None = None, from_: int | None = Query(None, alias="from")) -> DesignDiff:
    after = _revision(request, project_id, to)
    before = _revision(request, project_id, from_ if from_ is not None else max(after.number - 1, 1))
    return diff_designs(before.design, after.design, before.number, after.number)


@router.get("/projects/{project_id}/plc", response_model=PlcProject)
def plc(project_id: str, request: Request, revision: int | None = None) -> PlcProject:
    rev = _revision(request, project_id, revision)
    return generate_plc(rev.design, rev.number)


@router.get("/projects/{project_id}/plc.zip")
def plc_zip(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    return Response(
        content=plc_to_zip(generate_plc(rev.design, rev.number), rev.design),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="plc-{project_id}-r{rev.number}.zip"'},
    )


@router.get("/projects/{project_id}/plc.xml")
def plc_xml(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    return Response(
        content=to_plcopen_xml(rev.design, f"{rev.design.name} (revision {rev.number})"),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="plcopen-{project_id}-r{rev.number}.xml"'},
    )


@router.get("/projects/{project_id}/documents", response_model=TechnicalDocument)
def documents(project_id: str, request: Request, revision: int | None = None) -> TechnicalDocument:
    rev = _revision(request, project_id, revision)
    return build_document(rev.design, rev.number)


@router.get("/projects/{project_id}/documents.md")
def documents_markdown(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    return Response(
        content=to_markdown(build_document(rev.design, rev.number)),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="technical-description-{project_id}-r{rev.number}.md"'},
    )


@router.get("/projects/{project_id}/documents.docx")
def documents_docx(project_id: str, request: Request, revision: int | None = None) -> Response:
    rev = _revision(request, project_id, revision)
    template = request.app.state.mf.settings.template_dir / TEMPLATE_NAME
    return Response(
        content=to_docx(build_document(rev.design, rev.number), template),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="technical-description-{project_id}-r{rev.number}.docx"'},
    )


@router.get("/projects/{project_id}/rfq.xlsx")
def rfq(project_id: str, request: Request, revision: int | None = None) -> Response:
    state = request.app.state.mf
    rev = _revision(request, project_id, revision)
    return Response(
        content=build_rfq(rev.design, rev.number, state.storage, state.settings.base_currency),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="rfq-{project_id}-r{rev.number}.xlsx"'},
    )


@router.get("/projects/{project_id}/sourcing", response_model=SourcingReport)
def sourcing(project_id: str, request: Request, revision: int | None = None, external: bool = False) -> SourcingReport:
    state = request.app.state.mf
    rev = _revision(request, project_id, revision)
    return Sourcing(state.storage, state.settings, state.connectors).report(
        project_id, rev.number, rev.design, external=external
    )
