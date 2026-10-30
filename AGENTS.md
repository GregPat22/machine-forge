# Project instructions

Before any project-related work, read `CLAUDE.md` when present, follow its project
instructions, and read the documents it requires. It is the reference for project
standards and workflows; keep those instructions there rather than duplicating them here.

Also consult the existing configuration:

- Inspect `.claude/` for applicable project instructions. Read instruction Markdown and
  rules recursively when present, respecting any path scopes. Read relevant skill,
  command, and agent definitions for their project conventions and workflow guidance.
- Read `.claude/settings.json` and respect its shared restrictions. Claude permission
  syntax is not Codex configuration, and reading it does not enforce those restrictions
  in Codex. Local permission grants do not override project restrictions or approvals.
- Read the applicable workflow prompts in `.conductor/settings.toml` under `[prompts]`,
  including `general`, even when working outside Conductor.

Codex automatically discovers this file; the referenced files require explicit reads.
Claude skills, slash commands, hooks, permissions, and subagent definitions are not
automatically installed or executable in Codex. Use supported native equivalents where
available, preserve the applicable project guidance, and report any unsupported step
rather than claiming it ran.
