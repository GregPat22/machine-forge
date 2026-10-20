from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.models import Project, ProjectSummary, Revision, SourcingReport, SparePart
from app.services.designer import Designer, ProjectNotFound
from app.services.documents import TechnicalDocument, build_document, to_docx, to_markdown
from app.services.layout import Layout, compute_layout
from app.services.sourcing import Sourcing
from app.services.spare_parts import build_catalog, catalog_csv

router = APIRouter(tags=["projects"])


class NewProject(BaseModel):
    problem: str = Field(min_length=10, description="The production problem the machine must solve")


class PromptIn(BaseModel):
    message: str = Field(min_length=1)


def _designer(request: Request) -> Designer:
    state = request.app.state.mf
    return Designer(state.storage, state.provider)


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


# Endpoints that call the model are plain `def`: FastAPI runs them in a worker thread.


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(request: Request) -> list[ProjectSummary]:
    return request.app.state.mf.storage.list_projects()


@router.post("/projects", response_model=Project, status_code=201)
def create_project(body: NewProject, request: Request) -> Project:
    return _designer(request).create(body.problem.strip())


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str, request: Request) -> Project:
    project = request.app.state.mf.storage.get_project(project_id)
    if project is None:
        raise ProjectNotFound(f"Project {project_id} not found")
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request) -> Response:
    if not request.app.state.mf.storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)


@router.post("/projects/{project_id}/prompt", response_model=Project)
def prompt(project_id: str, body: PromptIn, request: Request) -> Project:
    return _designer(request).refine(project_id, body.message.strip())


@router.get("/projects/{project_id}/revisions", response_model=list[Revision])
def revisions(project_id: str, request: Request) -> list[Revision]:
    return request.app.state.mf.storage.list_revisions(project_id)


@router.post("/projects/{project_id}/revisions/{number}/restore", response_model=Project)
def restore(project_id: str, number: int, request: Request) -> Project:
    return _designer(request).restore(project_id, number)


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
    return Response(
        content=to_docx(build_document(rev.design, rev.number)),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="technical-description-{project_id}-r{rev.number}.docx"'},
    )


@router.get("/projects/{project_id}/sourcing", response_model=SourcingReport)
def sourcing(project_id: str, request: Request, revision: int | None = None, external: bool = False) -> SourcingReport:
    state = request.app.state.mf
    rev = _revision(request, project_id, revision)
    return Sourcing(state.storage, state.settings, state.connectors).report(
        project_id, rev.number, rev.design, external=external
    )
