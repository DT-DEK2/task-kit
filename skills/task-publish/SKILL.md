---
name: task-publish
description: Publish one task or epic to the user's trackers - exactly one GitHub issue in the current repo and exactly one Notion task in the ABC Tasks database, linked both ways. Use this whenever the user says "create tasks", "create a task", "make an issue", "write the task", "put this on Notion", "put this on GitHub", "tạo task", "viết task", "tạo task trên Notion và GitHub", "apply the plan", "apply", or asks to turn a plan or epic into tracked work. This skill writes only the tracking artifacts (GitHub issue plus Notion page), not code, DAGs, configs or Airflow tasks. Default to ONE issue and ONE Notion task for the whole epic; do not create child issues, sub-issues or per-task Notion pages unless the user explicitly asks.
---

# Task Publish

Turn a plan or epic into tracked work in two places: one GitHub issue and one Notion task.
The two point at each other, and the issue carries every work item as a checklist so the
whole epic stays readable in one place.

"Create tasks" means these tracking artifacts. It does not mean Airflow tasks, DAG files,
code, configs or a pull request. Stop after the issue and the Notion page; implementation is
a separate request.

## The one-and-one rule

- One GitHub issue for the epic, with all work items in its `## Tasks` checklist and one
  `## Task N - ...` section per item when detail is useful.
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

1. **Collect the plan.** Use the conversation first. Read the repo for paths, commands,
   schedules, hosts and existing DAGs so the issue describes the real system. Do not invent
   a command or a file; ask only for facts that cannot be read.
2. **Fix the metadata.** Decide the repo, project, platform, priority and assignee (default
   `@me`). Check the labels exist with `gh label list`; use `enhancement` and
   `documentation` when they do.
3. **Draft the issue body** with the template below. English, ASCII only, no emoji. Keep
   the whole epic in one issue. Link to long docs instead of pasting them, and keep the body
   under GitHub's 65,536-character limit.
4. **Create the issue** with the body in a temp file, then capture its number and URL:

   ```bash
   gh issue create --title "<P1> - <summary>" --body-file /tmp/opencode/<slug>-issue.md \
     --label enhancement --label documentation --assignee @me
   ```

5. **Create the Notion page** with `notion-create-pages`, parent
   `{ "data_source_id": "3fb63dbc-6f83-806b-bdb6-000b8a03b5e2" }`, the properties above, and
   content that mirrors the issue. Start the content with `GitHub issue: [#N](<url>).` so
   the two records are connected in both directions.
6. **Back-link.** Add exactly one comment to the issue with the Notion page URL. Do not add
   child pages or more comments.
7. **Report.** Give the issue URL, the Notion URL and one line saying the trackers are
   created and no code was written. If the user also asked for implementation, say the next
   step is one branch and one PR for the epic.

## Issue template

Use this exact shape; skip a section only when it genuinely has nothing to say.

```markdown
**Branch**: <one issue, one PR, off main: `feat/<slug>`; name the source-repo branch if one is needed>

**Order**: <P0/P1 of N; what runs in parallel, what blocks what>

**Assignee + label**: <@user>, `enhancement`, `documentation`

## Notions

| Term | Meaning |
|---|---|
| Marketplace / project | ... |
| Source state | branch, checkout, commit, what is not on main |
| Phase / work item | ... |
| Transport / runtime | ... |
| Dispatcher / scheduler | ... |
| Legacy | ... |
| Host | ... |

## Context

Why this exists, what runs today, what hurts. Ground it in real files and commands.

## Goal

The outcome in one or two sentences.

## Tasks

- [ ] 1. <one outcome per line>
- [ ] 2. ...
- [ ] 3. ...

## Task 1 - <name>

Files: `<path>`, `<path>`.

- <requirement>
- <requirement>

**Done when**: <a command, exit code, query or UI state that proves it>

## Task 2 - <name>

...

## Cutover and rollback

<only when the change replaces a running path>

## Verify

```bash
<the local checks and the live checks>
```

## Notes

<dependencies on other issues/PRs, naming decisions, schedules that change, risks>
```

## Notion page content

Mirror the issue, not a summary of it:

```markdown
GitHub issue: [#N](<url>). This is the single Notion task for <epic>; it covers the full plan.

## Goal

...

## Naming

| Marketplace | Phase | DAG / item | Slot | Flow |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

## Notions

| Term | Meaning |
|---|---|
| ... | ... |

## Context

...

## Tasks

- [ ] 1. ...

## Task 1 - <name>

...

## Cutover and rollback

...

## Verify

```bash
...
```

## Notes

...
```

Notion-flavored Markdown: fence code blocks, use pipe tables for simple tables, use
`- [ ]` for checklists, and use Markdown links for external URLs such as the GitHub issue.
Do not use raw HTML tags.

## Guardrails

- **No code.** Do not create or edit DAG files, configs, scripts, tests or docs as part of
  task creation. The issue and the Notion page are the deliverable.
- **No splitting by default.** One issue and one page for the epic. Child issues or
  per-task pages only on an explicit request.
- **No secrets.** Never put tokens, keys, passwords or private host details in the issue or
  the Notion page.
- **No invented facts.** A path, command, schedule or host must come from the repo or the
  user. Write `TBD` and ask when it cannot be read.
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

## Reference

A full example from this workspace: GitHub issue
[#84](https://github.com/abcinsight/abcstudio-airflow/issues/84) and its single Notion task
`40263dbc-6f83-8180-bac2-c62688b840b6` in ABC Tasks. The issue carries the five work items
in one body; the Notion page mirrors it; one comment links the page back to the issue.
