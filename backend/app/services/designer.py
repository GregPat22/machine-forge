"""The prompting loop: problem -> first design, then request -> new revision."""

from __future__ import annotations

from app.llm import LLMProvider, Turn
from app.llm.prompts import SYSTEM_PROMPT, first_turn, refine_turn
from app.models import DesignUpdate, Project
from app.storage import Storage

# Earlier chat turns sent as context with each request (the current design is always sent in full).
HISTORY_TURNS = 10


class ProjectNotFound(LookupError):
    pass


class Designer:
    def __init__(self, storage: Storage, provider: LLMProvider):
        self.storage = storage
        self.provider = provider

    def create(self, problem: str) -> Project:
        update = self.provider.structured(
            system=SYSTEM_PROMPT,
            turns=[{"role": "user", "content": first_turn(problem)}],
            output=DesignUpdate,
        )
        project_id = self.storage.create_project(problem, update.reply, update.design)
        return self._get(project_id)

    def refine(self, project_id: str, request: str) -> Project:
        project = self._get(project_id)
        history: list[Turn] = [
            {"role": m.role, "content": m.content} for m in project.messages[-HISTORY_TURNS:]
        ]
        # The history must start with a user turn.
        while history and history[0]["role"] != "user":
            history.pop(0)
        turns: list[Turn] = [
            *history,
            {"role": "user", "content": refine_turn(project.design.model_dump_json(indent=1), request)},
        ]
        update = self.provider.structured(system=SYSTEM_PROMPT, turns=turns, output=DesignUpdate)
        self.storage.add_revision(project_id, request, update.reply, update.design)
        return self._get(project_id)

    def restore(self, project_id: str, number: int) -> Project:
        self._get(project_id)
        revision = self.storage.get_revision(project_id, number)
        if revision is None:
            raise ProjectNotFound(f"Revision {number} not found")
        self.storage.add_revision(
            project_id, f"Restore revision {number}", f"Restored the design of revision {number}.", revision.design
        )
        return self._get(project_id)

    def _get(self, project_id: str) -> Project:
        project = self.storage.get_project(project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        return project
