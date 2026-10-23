---
name: task-publish
description: Publish one task or epic to the user's trackers - exactly one GitHub issue in the current repo and exactly one Notion task in the ABC Tasks database, linked both ways. Use this whenever the user says "create tasks", "create a task", "make an issue", "write the task", "put this on Notion", "put this on GitHub", "tạo task", "viết task", "tạo task trên Notion và GitHub", "apply the plan", "apply", or asks to turn a plan or epic into tracked work. Keep the task short and outcome-focused; do not prescribe the implementation. This skill writes only the tracking artifacts (GitHub issue plus Notion page), not code, DAGs, configs or Airflow tasks. Default to ONE issue and ONE Notion task for the whole epic; do not create child issues, sub-issues or per-task Notion pages unless the user explicitly asks.
---

# Task Publish

Turn a plan or epic into tracked work in two places: one GitHub issue and one Notion task.
The two point at each other. Keep both short: a task is a contract, not a runbook.

## Write the outcome, not the steps

The person who picks up the task usually knows the code and the domain better than the
person writing it. A detailed step list has two costs: it can be wrong or stale, and it
steers the assignee away from a better solution. So:

- State **what must be true** and **why it matters**. Leave **how** to the assignee.
- Keep the issue to roughly 30-60 lines: a short context, a goal, a checklist of outcomes,
  and acceptance criteria. If it grows, cut the procedure, not the outcome.
- Add a fact only when the assignee cannot infer it from the repo: a destination, a hard
  deadline, a naming decision, a host or protocol constraint. Write it as a constraint, not
  as a procedure.
- If you do not fully understand the concept, ask the user or put the gap under
  `## Open questions` instead of inventing steps. The assignee can clarify before starting.
- No file-by-file layout, exact command sequences, exhaustive term tables or one section per
  step by default. Those belong in a runbook when the user asks for one.

## The one-and-one rule

- One GitHub issue for the epic, with all work items in its `## Tasks` checklist.
- One Notion task page for the same epic, mirroring the issue.
- No child issues, no sub-issues, no per-task Notion pages. If the user wants a different
  shape, they must say so explicitly; do not split by default.
- If the user also asks for implementation later, use one branch and one pull request for
  the whole epic. Never create one PR per task.

## Destination

Default Notion board: **ABC Tasks**, data source
`collection://3fb63dbc-6f83-806b-bdb6-000b8a03b5e2`. If it is not reachable, search for
"ABC Tasks" and confirm the board with the user before creating anything.

Properties on the page:

| Property | Value |
|---|---|
| `Task` | the page title, same summary as the issue |
| `Link` | the GitHub issue URL |
| `Project` | the project from the request, normally `Nestlie` or `Nestle Scraper` |
| `Platform` | the marketplace/product name, for example `gsshop` |
| `Priority` | `P1`, `P2` or `P3`; the board has no `P0`, so map a P0 epic to `P1` and note it |
| `Status` | `Todo` |
| `Person` | the assignee when the user named one; otherwise leave empty |
| `Due` / `Completed` | leave empty unless the user gave dates |

If the `Platform` value does not exist yet, update the data source first, listing every
option because omitted options are removed:

```sql
ALTER COLUMN "Platform" SET MULTI_SELECT('11st':default, 'cjmall':blue, 'auction':green, 'gsshop':purple)
```

## Workflow

1. **Collect the outcome.** Use the conversation first. Read the repo only enough to state
   the goal, the current path and the constraints; do not reverse-engineer the
   implementation for the assignee.
2. **Fix the metadata.** Decide the repo, project, platform, priority and assignee (default
   `@me`). Check the labels exist with `gh label list`; use `enhancement` and
   `documentation` when they do.
3. **Draft the short issue** with the template below. English, ASCII only, no emoji.
4. **Create the issue** with the body in a temp file, then capture its number and URL:

   ```bash
   gh issue create --title "<P1> - <summary>" --body-file /tmp/opencode/<slug>-issue.md \
     --label enhancement --label documentation --assignee @me
   ```

5. **Create the Notion page** with `notion-create-pages`, parent
   `{ "data_source_id": "3fb63dbc-6f83-806b-bdb6-000b8a03b5e2" }`, the properties above, and
   content that mirrors the short issue. Start with `GitHub issue: [#N](<url>).` so the two
   records are connected in both directions.
6. **Back-link.** Add exactly one comment to the issue with the Notion page URL. Do not add
   child pages or more comments.
7. **Report.** Give the issue URL, the Notion URL and one line saying the trackers are
   created and no code was written. If the user also asked for implementation, say the next
   step is one branch and one PR for the epic.

## Issue template

```markdown
**Branch**: <one issue, one PR, off main: `feat/<slug>`>

**Order**: <P1, standalone; or what blocks what>

**Assignee + label**: <@user>, `enhancement`, `documentation`

## Context

Why this exists, what runs today, what hurts. Two to four sentences.

## Goal

The outcome in one or two sentences.

## Tasks

- [ ] <outcome 1>
- [ ] <outcome 2>

## Acceptance

- [ ] <a command, query or UI state that proves the outcome>

## Notes

Dependencies, constraints, links, open questions. No secrets.
```

Optional sections, only when they add information the assignee cannot infer:

- `## Constraints` - a hard deadline, a destination, a host or protocol limit.
- `## Out of scope` - the work this task deliberately excludes.
- `## Cutover` - only when the change stops a running path; state the requirement, not the
  commands.
- `## Open questions` - what the author cannot decide or does not understand.

Do not add a `## Task 1` section per checkbox. The checklist is the plan.

## Notion page content

Mirror the short issue, not a longer version of it:

```markdown
GitHub issue: [#N](<url>). This is the single Notion task for <epic>.

## Goal

...

## Tasks

- [ ] ...

## Acceptance

- [ ] ...

## Notes

...
```

Notion-flavored Markdown: fence code blocks, use pipe tables for simple tables, use
`- [ ]` for checklists, and use Markdown links for external URLs such as the GitHub issue.
Do not use raw HTML tags.

## Guardrails

- **No code.** Do not create or edit DAG files, configs, scripts, tests or docs as part of
  task creation. The issue and the Notion page are the deliverable.
- **No step-by-step instructions.** Do not write "first do X, then run Y" unless the user
  explicitly asks for a runbook. Describe the result and the constraints.
- **No splitting by default.** One issue and one page for the epic. Child issues or
  per-task pages only on an explicit request.
- **No secrets.** Never put tokens, keys, passwords or private host details in the issue or
  the Notion page.
- **No invented facts.** A path, command, schedule or host must come from the repo or the
  user. Write `TBD` or an open question when it cannot be read.
- **No silent schema loss.** When adding a select/multi-select option, list every existing
  option; an omitted option is removed from the data source.
- **No extra PRs.** If implementation is requested later, one branch and one PR for the
  epic, not one per task.

## Verify

```bash
gh issue view <number> --json number,title,url,labels,assignee
```

Then fetch the Notion page and check: `Link` equals the issue URL, `Status` is `Todo`,
`Platform` contains the intended value, and the first content line links back to the issue.
The issue should have exactly one back-link comment.

## Short example

```markdown
**Branch**: `feat/neslie-gsshop`, one PR.

**Order**: P1, standalone.

**Assignee + label**: @me, `enhancement`, `documentation`

## Context

gsshop still runs through the legacy `nestlie_gsshop` Docker DAG on three UTC slots. The
host scheduler already runs the real cadence (00:01 basic, four detail slots) but Airflow
cannot see it.

## Goal

Run gsshop from `neslie_dispatch` with a basic DAG at 00:01 VN and a detail DAG at
02:00/07:00/12:00/18:40 VN over ssh, and stop the legacy DAG and the host scheduler.

## Tasks

- [ ] Basic DAG: scrape_basic -> upload_basic on its own 00:01 cron.
- [ ] Detail DAG: detail -> upload -> remain on four dispatcher slots, run_index 1-4.
- [ ] Registry, env template, docs and access-control updates.
- [ ] Cut over from `nestlie_gsshop` and the host scheduler.

## Acceptance

- [ ] `airflow dags list | grep gsshop` shows both DAGs.
- [ ] One dispatcher slot triggers the detail DAG with the right run_index and date.
- [ ] A full day has one basic run and four detail runs, no legacy run, and the BQ tables
      match.

## Notes

Depends on the cjmall PR #81 for the registry shape. The host and key already exist on
100.90.53.150.
```

The tracker pair from issue #84 and its Notion page shows the linking pattern; its body is
longer than the new default because it was written before this rule. Prefer the short shape
above.
