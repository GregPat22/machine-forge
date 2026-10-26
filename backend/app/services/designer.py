"""The prompting loop: problem -> first design, then request -> new revision.

The AI answers with patches (`services/patch.py`). Rejected patches go back to it as the next turn,
up to `max_attempts` answers in total; after the last one the design is unchanged and the user gets
a readable error (the repair loop, Phase 1).
"""

from __future__ import annotations

import logging

from app.llm import LLMError, LLMProvider, Turn
from app.llm.base import ProgressFn
from app.llm.prompts import SYSTEM_PROMPT, first_turn, refine_turn, repair_turn
from app.models import MachineDesign, Project
from app.services.patch import PatchError, PatchOp, PatchUpdate, apply_patches, empty_design
from app.storage import Storage

# Earlier chat turns sent as context with each request (the current design is always sent in full).
HISTORY_TURNS = 10
DEFAULT_MAX_REPAIR_ATTEMPTS = 3
# Problems quoted in the error the user sees; the AI always gets all of them.
USER_ERRORS_SHOWN = 3

log = logging.getLogger(__name__)


class ProjectNotFound(LookupError):
    pass


class PatchRejected(LLMError):
    """The AI's patches were still invalid after the last attempt. The message is safe to show."""


class Designer:
    def __init__(self, storage: Storage, provider: LLMProvider, max_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.storage = storage
        self.provider = provider
        self.max_attempts = max_attempts

    def create(self, problem: str, on_progress: ProgressFn | None = None) -> Project:
        reply, design = self._edit(
            empty_design(), [{"role": "user", "content": first_turn(problem)}], on_progress, first=True
        )
        project_id = self.storage.create_project(problem, reply, design)
        return self._get(project_id)

    def refine(self, project_id: str, request: str, on_progress: ProgressFn | None = None) -> Project:
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
        reply, design = self._edit(project.design, turns, on_progress)
        self.storage.add_revision(project_id, request, reply, design)
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

    def _edit(
        self, design: MachineDesign, turns: list[Turn], on_progress: ProgressFn | None, first: bool = False
    ) -> tuple[str, MachineDesign]:
        """Ask for patches and apply them; on errors, send them back, up to `max_attempts` answers."""
        errors: list[PatchError] = []
        for attempt in range(1, self.max_attempts + 1):
            update = self.provider.structured(
                system=SYSTEM_PROMPT, turns=turns, output=PatchUpdate, on_progress=on_progress
            )
            result = apply_patches(design, update.patches)
            errors = result.errors or (_unnamed(result.design) if first and result.design else [])
            if not errors and result.design is not None:
                log.info("attempt %d/%d: %d patches applied", attempt, self.max_attempts, len(update.patches))
                return update.reply, result.design
            log.warning("attempt %d/%d: patches rejected, %d errors: %s", attempt, self.max_attempts, len(errors),
                        "; ".join(f"{e.code} {e.message}" for e in errors))
            turns = [
                *turns,
                {"role": "assistant", "content": update.model_dump_json()},
                {"role": "user", "content": repair_turn(_describe(errors, update.patches))},
            ]
        shown = "; ".join(e.message for e in errors[:USER_ERRORS_SHOWN])
        more = f" (and {len(errors) - USER_ERRORS_SHOWN} more)" if len(errors) > USER_ERRORS_SHOWN else ""
        raise PatchRejected(
            f"The AI could not make a valid change in {self.max_attempts} attempts, so the design is unchanged. "
            f"Last problems: {shown}{more}"
        )

    def _get(self, project_id: str) -> Project:
        project = self.storage.get_project(project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        return project


def _unnamed(design: MachineDesign) -> list[PatchError]:
    """The first answer starts from an empty design: it must give the machine its name, type and summary."""
    missing = [f for f in ("name", "machine_type", "summary") if not getattr(design, f).strip()]
    if not missing:
        return []
    return [PatchError(index=None, code="missing_operand",
                       message="the first answer must set name, machine_type and summary with set_param "
                               f"(missing: {', '.join(missing)})")]


def _describe(errors: list[PatchError], patches: list[PatchOp]) -> str:
    lines = []
    for e in errors:
        where = f"patch {e.index} ({patches[e.index].op})" if e.index is not None else "answer"
        lines.append(f"- {where}: {e.code}: {e.message}")
    return "\n".join(lines)
