# task-kit

Skills and helper scripts for handing work to other people through task files that live
in each project's `docs/tasks/` folder, with an optional read-only mirror in Notion.

## Install

```bash
./install.sh            # links the skills into ~/.config/opencode/skills
./install.sh --claude   # also into ~/.claude/skills
```

The links point at this checkout, so `git pull` here updates every project at once.

## Skills

| Skill | Use it to |
| --- | --- |
| `task-brief` | write, change or drop one task brief; sets up `docs/tasks/` in a new project |
| `task-breakdown` | split an epic into ordered tasks, a plan and a shared runbook |
| `task-start` | start a task, mark it blocked, or hand it in with evidence |
| `task-review` | accept or reject a handed-in task against its acceptance criteria |
| `task-status` | rebuild the board, mirror to Notion, and get a progress digest |
| `task-publish` | publish one epic as one short GitHub issue plus one Notion task, linked both ways; tracker-only, no code |

`task-publish` is tracker-only: it does not create `docs/tasks/` and never edits the
project. Use it when the user wants the epic on GitHub and in Notion, not a task file.

## What a project gets

`task-brief` copies these into the project's `docs/tasks/` on first use:

| File | From |
| --- | --- |
| `_template.md` | `skills/task-brief/references/task-template.md` |
| `README.md` | `skills/task-brief/references/readme-template.md` (lifecycle, roles, board) |
| `tasks.py` | `skills/task-brief/scripts/tasks.py` (`next-id`, `new`, `lint`, `board`) |
| `notion_sync.py` | `skills/task-brief/scripts/notion_sync.py`, only when Notion is wanted |

Task files stay in the project: `tasks.py lint` checks their `path:line` references
against that project's code, and they are reviewed in the same pull request as the code.

When a script changes here, bump its `VERSION`; `task-brief` replaces an older copy in a
project the next time it runs there.

## Notion

One database serves every project; the `Project` column tells them apart.

1. Create an internal integration at https://www.notion.so/profile/integrations with Read,
   Update and Insert content, plus Read user information including email addresses.
2. Share the database (or its parent page) with the integration: ••• -> Connections.
3. In the project's `.env` (git-ignored): `NOTION_TOKEN=...` and `NOTION_DATABASE_ID=...`.
4. `python3 docs/tasks/notion_sync.py --setup` once per database (columns, column order in
   every table view, hidden `Hash`), then
   `python3 docs/tasks/notion_sync.py` whenever tasks change (`task-status` runs it).

To start a new workspace without copying by hand, either run
`python3 docs/tasks/notion_sync.py --create-template <parent page id>` there (it needs an
integration in that workspace), or publish an existing template page with "Allow duplicate
as template" and press Duplicate in the other workspace; no integration is needed to
duplicate, only to sync afterwards.

People in task headers are written as their Notion email so they map to People columns.
Edits made in Notion are overwritten by the next sync, except open questions: checkboxes
added or ticked under "Open questions" in a task page are copied into the task file.
