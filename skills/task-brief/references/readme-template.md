# Task handoff board

Every unit of work handed to another person lives here as one file. That file is the
contract between the assignee who does the work, the reviewer who accepts it and the
requester who asked for it.

## How to use

| Need | Skill |
| --- | --- |
| Write a brief for one piece of work | `task-brief` |
| Split an epic into tasks | `task-breakdown` |
| Start a task, block it, or hand it in for review | `task-start` |
| Accept or reject finished work | `task-review` |
| Refresh this board and get a progress digest | `task-status` |

Mechanical checks run through `python3 docs/tasks/tasks.py` (`next-id`, `new`, `lint`,
`board`). The script is standard-library Python and works without any skill.

Notion is a read-only mirror: `python3 docs/tasks/notion_sync.py` pushes every task to the
database named by `NOTION_DATABASE_ID` (token in `NOTION_TOKEN`, both read from `.env`).
Pages match on `ID`, unchanged tasks are skipped, and edits made in Notion are overwritten
on the next sync - change tasks here. `--setup` creates the columns, `--dry-run` writes
nothing.

Questions also flow back: a checkbox added under "Open questions" in a Notion page is
copied into the task file as `- [ ] Qn: ... - asked in Notion by <email>, <date>`, and a
question ticked in Notion is ticked in the file. Commit those file changes. Everything
else edited in Notion is overwritten. `--no-pull` turns this off.

## Files

- `TASK-NNN-<kebab-slug>.md` - one task. Ids are sequential and never reused.
- `PLAN-<kebab-slug>.md` - order and open decisions when an epic has three or more tasks.
- `RUNBOOK-<kebab-slug>.md` - a procedure shared by several tasks (SQL, commands). Tasks
  cite its sections instead of copying them.
- `_template.md` - the brief template. `tasks.py new` copies it.

## Roles

| Field | Who | Notion column |
| --- | --- | --- |
| Requester | Creates the task, hands it out and owns the outcome | Owner |
| Assignee | Does the work | Person |
| Leader | Team lead of the assignee; told when the task is late or blocked | Leader |
| Reviewer | Accepts or rejects the work: the requester unless they name someone else; never the assignee | Reviewer |

Write people as their email (preferred) or exact Notion name. `Issue` links the GitHub
issue that tracks the task, when there is one. `Estimate` is the expected finish
date the assignee forecasts; `Due` is the deadline the requester sets. `Project` is the
product (`Nestlie`), `Epic` the larger piece of work, `Platform` the marketplaces a
task touches (`11st, gmarket`, or `none`). `Start` is set by the assignee when
work starts; the completion date is read from the accepting review.

## Lifecycle

The `Status` field in a task file's header is the only source of truth. The board below is
generated from the files by `tasks.py board` and is never edited by hand.

| From | To | Who | Recorded as |
| --- | --- | --- | --- |
| Todo | In progress | Assignee | `Start` set to the day work starts |
| In progress | In review | Assignee | GitHub link to the pull request under Evidence |
| In review | Done | Reviewer | Review entry with `Decision: Accepted` |
| In review | In progress | Reviewer | Review entry with `Decision: Rework needed` |
| Todo, In progress | Blocked | Assignee | Open question with the reason, naming who answers it |
| Blocked | previous status | Assignee | The question ticked with its answer |
| any open | Dropped | Requester | `Dropped (replaced by TASK-NNN)`, reason in the commit message |

`Depends on` means the task cannot start until every listed task is `Done`. An ordering
constraint that applies to one step only is a sign the step belongs in its own task.

## Board flags

- `OVERDUE` - open and `Due` is in the past.
- `AT-RISK` - open and `Estimate` is later than `Due`.
- `STALE` - In progress or In review with no dated activity for more than 7 days.
- `WAITING:<ids>` - not started or in progress while a dependency is not Done.
- `UNVERIFIED` - Done without a latest review that says Accepted.
- `RESUBMITTED` - In review again after a Rework needed review.
- `OPEN-Q:n` - unanswered questions (`- [ ] Qn:`); ticked ones (`- [x] Qn:`) do not count.
- `LINT:n` - `tasks.py lint` errors in the file.

## Conventions

- One task is one assignee, one verifiable outcome, and half a day to two days of work.
- The reviewer is never the assignee.
- Claims about the current system cite `path:line`; `tasks.py lint` checks that they exist.
- Task files are English, ASCII only, no emoji. Open questions may be written in the
  language of the person who asks.
- Review entries are appended, never rewritten. The history of a task is its git history:
  say what changed and why in the commit message.

## Status board

<!-- status-board:start -->

<!-- status-board:end -->
