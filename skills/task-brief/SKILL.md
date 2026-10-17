---
name: task-brief
description: Turn a raw request into one concise, verifiable task document that another person can pick up and execute, plus a short assignment message (in the chat reply, not in the file) the user can paste to the assignee. Use this whenever work is being handed to someone else, or an existing brief must be changed or dropped - assign work, hand off, delegate, write a task, ticket, brief or spec, "giao task", "giao việc này cho dev", "phân công nhiệm vụ", "viết task", "sửa task", "huỷ task", "handoff", "assign this", "write up a task", "make a ticket". Works for any domain - code, data, ops, QA, documentation. It only produces the handoff document; it never does the work.
---

# Task Brief

One task document serves three readers: the assignee who executes it, the reviewer who
accepts it, and the requester who checks status. Write for all three in one page.

## Non-goals

- Never change code, configuration, infrastructure or data while writing a brief. Read only.
- Never invent facts about the current system. A claim without a source is not written as
  fact; raise it with the user in the reply.
- Never write a brief only the author can understand. Local context that is not in the
  repo goes into the brief.

## Setup (once per repository)

The skill folder holds the canonical copies: `references/task-template.md`,
`references/readme-template.md`, `scripts/tasks.py`.

1. If `docs/tasks/` does not exist, create it and copy those three files to
   `docs/tasks/_template.md`, `docs/tasks/README.md` and `docs/tasks/tasks.py`.
2. If `docs/tasks/tasks.py` exists, compare `python3 docs/tasks/tasks.py version` with the
   `VERSION` in the skill copy. When the skill copy is newer, replace the repo copy and
   say so in the reply.
3. Never overwrite an existing `README.md` or `_template.md`; report differences instead.

## Workflow: new brief

1. Read `docs/tasks/README.md` (lifecycle and conventions). Read
   `references/example-filled-brief.md` once per session before the first brief.
2. Ground the request: search the repo for the files, functions, tables, commands, configs
   and earlier tasks it touches, and collect `path:line` references. Read any document,
   ticket or thread the user points at.
3. Decide the boundary. One assignee, one outcome, half a day to two days, startable as soon
   as the tasks in `Depends on` are Done. If any of that fails, stop and load
   `task-breakdown` instead of writing a vague brief.
4. Create the file: `python3 docs/tasks/tasks.py new <kebab-slug> --title "<imperative
   title>" --project "<project>" [--epic E] [--platform 11st,gmarket] --requester <user> [--assignee X] [--leader L]
   [--reviewer Y] [--estimate YYYY-MM-DD] [--priority P1] [--due YYYY-MM-DD] [--depends
   TASK-001] --author <user>`. It assigns the next id and fills the header. The
   requester is the user who asks for the brief (the creator) unless they name someone
   else, and the reviewer defaults to the requester; pass `--reviewer` only when the user
   names another reviewer. People are written as their email
   (preferred) or exact Notion name, so the Notion mirror can map them.
5. Write requirements `R1..Rn` in the order the assignee will do them. Each one is a
   verifiable change or behaviour, not a goal. Two requirements that always pass or fail
   together are one requirement.
6. Write acceptance criteria `AC1..ACn` a reviewer can run or inspect: a command, query,
   file or artifact, and the expected result. Requirements say what changes; acceptance
   criteria say how someone proves it changed.
7. Baseline every negative check. An AC that expects "no matches", "zero rows" or "no
   error" must be run now, against the current state, and must return the thing it later
   expects to be gone. Record that baseline in Context. A check that already passes today
   proves nothing - fix the pattern or query until the baseline is non-empty.
8. Fill the remaining sections. Keep Goal, Context and References short; the value is in
   the requirements and acceptance criteria. Procedures longer than about 30 lines that
   several tasks share go into `docs/tasks/RUNBOOK-<slug>.md`, cited by section.
9. Draft an assignment message for the chat reply only; it is not stored in the task file.
   Write it in the language of the person who receives it (the language the user wrote
   the request in, unless told otherwise). Three to six lines: who, what, the file, done
   when, how to report back, due date.
10. Run `python3 docs/tasks/tasks.py lint TASK-NNN`. Fix every ERROR. Fix every WARN or
    state in the reply why it stays.
11. Run `python3 docs/tasks/tasks.py board`.

## Workflow: change or drop an existing brief

1. Edit the task file in place. Never create a second file for the same work.
2. Say what changed and why in the commit message; the file keeps no change log.
3. Never edit `## Evidence` or `## Review log`.
4. If requirements or acceptance criteria change after the task left `Todo`, say so in the
   reply so the assignee is told.
5. To drop a task, set `Status` to `Dropped` or `Dropped (replaced by TASK-NNN)` and log
   the reason. Ids are never reused or renumbered.
6. Run `lint` and `board` as above.

## Writing rules

- One page is the target, `tasks.py lint` warns at about 200 lines.
- Cite where every statement about the current system was read (`path:line`).
- Imperatives: "Add the filter to ...", "Verify that ...".
- `Depends on` holds task ids or `none`, nothing else. "Can be built now but deployed only
  after X" is a sign that the deploy is its own task.
- Use `TBD` for assignee, leader, reviewer, estimate and due date when the user did not say.
  Never guess an estimate; it is the finish date the assignee forecasts. Do not block on it.
- `## Open questions` is for the assignee and other readers to ask; a new brief leaves it
  at `- None.`. Do not put the requester's own undecided points there: decide them with
  the user, write the decision into the requirements or risks, or list them in the reply.
  Questions others add are checkboxes `- [ ] Qn: ...`, ticked with the answer appended.
- Name the work that is explicitly excluded; scope creep is half of handoff failures.
- Task files: English, ASCII only, no emoji. Open questions may use the asker's language.

## Output contract

- `docs/tasks/TASK-NNN-<kebab-slug>.md` that passes `tasks.py lint` with zero errors.
- An updated board in `docs/tasks/README.md`.
- A chat reply containing only: the file path, the assignment message as a quoted block,
  anything the requester still has to decide or fill in (due date, people), and any lint
  warnings left in place.

## Reference files

- `references/task-template.md` - canonical template (bootstrap only).
- `references/readme-template.md` - canonical README with lifecycle and board markers.
- `references/example-filled-brief.md` - a filled brief with the expected level of detail.
- `scripts/tasks.py` - canonical helper script, copied to `docs/tasks/tasks.py`.
- `scripts/notion_sync.py` - optional Notion mirror, copied to `docs/tasks/notion_sync.py`
  only when the user wants Notion.
