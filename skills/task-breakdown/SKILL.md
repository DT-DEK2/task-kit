---
name: task-breakdown
description: Split a large or vague piece of work into concrete, ordered, individually assignable tasks and write the task documents and a plan. Use whenever the user asks to divide, plan, phase, sequence or organise work - "chia việc", "chia task", "phân rã", "lập kế hoạch phân công", "tách task", "break this into tasks", "plan the work", "how should we split this", "phase this project", "who does what", "sequence the work", "make a backlog". Use it before task-brief when the request spans several assignees, several systems or more than one sitting. Works for any domain - code, data, ops, QA, documentation.
---

# Task Breakdown

A breakdown is only useful if every slice can be started, finished and verified on its
own. The output is a small set of task documents plus the order they run in.

## Non-goals

- Do not do the work or write code.
- Do not produce one task with twenty requirements; that is the same as doing nothing.
- Do not invent dependencies. A dependency exists when one task's output is another
  task's input, or when both touch the same resource in a conflicting order.

## Workflow

1. Restate the epic in one sentence and confirm it with the user before slicing. A wrong
   goal sentence poisons every task below it.
2. Ground the epic: read the code, schema, infra, tickets and earlier tasks it touches.
   Find the real seams - modules, deploy steps, data flows, approvals, external parties,
   waiting periods (a pipeline cycle, a retention window, a sign-off).
3. Slice along the seams. A slice has one assignee and skill set, one verifiable outcome, one
   system, and fits one sitting (half a day to two days).
4. Apply the dependency test to every slice: it must be able to start as soon as the
   tasks it depends on are Done, and finish without waiting for anything else.
   - "Build now, deploy after X" fails the test: make the deploy its own slice.
   - "Steps 1-6 now, step 7 after another task, step 8 in two weeks" fails it: each
     waiting point starts a new slice.
   - A slice whose only purpose is to remove uncertainty is a `decision` slice and runs
     first.
5. Classify each slice: `code`, `data`, `ops`, `docs`, `verify`, `decision`. Size it `S`
   (under half a day) or `M` (one to two days). Anything bigger is split again; `L` never
   appears in a plan.
6. When something important is produced, add a `verify` slice whose assignee did not build it.
   It reviews the build tasks with the `task-review` skill.
7. Procedures shared by several slices (SQL, command sequences, checklists) go into one
   `docs/tasks/RUNBOOK-<kebab-slug>.md` with numbered sections; slices cite the sections.
8. Write each slice with the `task-brief` skill, in dependency order so `--depends` can
   name real ids.
9. Run `python3 docs/tasks/tasks.py lint`. A dependency cycle is a slicing error: re-cut
   the slices rather than editing `Depends on` to hide it.
10. With three or more slices, write `docs/tasks/PLAN-<kebab-slug>.md`: the epic sentence,
    the ordered slice table (id, title, class, size, assignee, depends on, track), the
    critical path, and the open decisions with who decides and what each blocks.
11. Run `python3 docs/tasks/tasks.py board`.

## Re-planning

- Never renumber or reuse ids. Add new tasks, set replaced ones to
  `Dropped (replaced by TASK-NNN)`, and log the change in each affected file.
- Keep a task's id when its scope shrinks; move the removed requirements to new tasks.
- Update the PLAN table and append a dated line under `## Plan changes`.

## Rules

- Prefer five small tasks over two big ones; small tasks expose wrong assumptions early.
- Every task must be assignable today with the information that exists today. "Gather more
  context" is not a task; it is a decision to settle with the user before slicing.
- English, ASCII only, no emoji, except open questions.

## Output contract

- One `TASK-NNN-<kebab-slug>.md` per slice, each passing `tasks.py lint`, no cycles.
- `PLAN-<kebab-slug>.md` when there are three or more slices; `RUNBOOK-<kebab-slug>.md`
  when slices share a procedure.
- One chat message: the ordered list, the parallel tracks, the decisions that block
  something, and the first task to start.
