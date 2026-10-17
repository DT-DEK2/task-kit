---
name: task-review
description: Accept or reject a finished task against its own acceptance criteria, with evidence for every criterion, and record the verdict and the resulting status in the task document. Use whenever the user asks to review, accept, sign off, verify or check finished work - "nghiệm thu", "kiểm tra task này xong chưa", "review task", "chấm task", "duyệt task", "đóng task", "accept this work", "is this done", "sign off", "verify the deliverable", "close the task". Use it after the assignee hands in (Status In review), before anything is marked Done. It reports only; it never fixes the work.
---

# Task Review

A review compares what the task asked for with what actually exists. The task document is
the contract; the repository, the systems and the linked pull request are the facts.

## Non-goals

- Do not fix, refactor or finish the work. Report, do not repair.
- Do not weaken an acceptance criterion to make it pass. If a criterion is wrong or
  unverifiable, say so and ask for the brief to be corrected with `task-brief`.
- Do not accept on the strength of a summary or a ticked checkbox.

## Workflow

1. Find the task file in `docs/tasks/` from the id or title. If several match, ask.
2. Run `python3 docs/tasks/tasks.py lint TASK-NNN`. Lint errors in the brief itself (no
   numbered criteria, missing sections) stop the review: fix the brief with `task-brief`
   first. Warnings about missing evidence are inputs to step 4.
3. Note who is reviewing. It is the `Reviewer` in the header, which defaults to the
   requester who created the task; anyone else reviewing says so in the entry. If it is the assignee, continue only when the user confirms, and
   say so in the entry.
4. Collect evidence, preferring the artifact over the report:
   - the deliverables exist and contain the described change;
   - the pull request linked under `## Evidence`: its diff, and the outputs in its
     description, re-run when cheap and read-only (`gh pr view <n>`, `gh pr diff <n>`); the
     output is compared, not just read;
   - negative checks are compared with the baseline in Context; a negative check without
     a non-empty baseline is BLOCKED, not PASS.
5. Check the negative side: changes outside the declared scope (use `git diff` or the
   system's history), new side effects, and criteria that pass only because the check was
   not actually run.
6. Judge each criterion `PASS`, `FAIL` or `BLOCKED` with one line of evidence. PASS needs
   evidence from step 4. BLOCKED names exactly what would unblock it and who has it.
7. Append the entry under `## Review log` using `references/review-report-template.md`.
   `Decision: Accepted` only when every criterion is PASS; otherwise
   `Decision: Rework needed`. Never edit earlier entries.
8. Set the header `Status`: `Done` when accepted, `In progress` when rework is needed.
   That line and the review entry are the only edits this skill makes.
9. Run `python3 docs/tasks/tasks.py lint TASK-NNN` and `python3 docs/tasks/tasks.py board`.
10. Reply in at most ten lines: the decision, the FAIL and BLOCKED criteria, and the next
    action for the assignee, written so it can be forwarded.

## Rules

- One review entry per hand-in. The history is the point.
- Requirements and acceptance criteria are not negotiable inside a review. Propose the
  change; the requester accepts it through `task-brief`.
- When a `verify` task reviews another task, the entry goes into the reviewed task's file,
  and the verify task's own evidence links to it.
- English, ASCII only, no emoji, except the message meant for the assignee.

## Output contract

- One appended `## Review log` entry and the updated `Status`.
- An updated board.
- One chat message: decision, per-criterion result for anything not PASS, next action.

## Reference files

- `references/review-report-template.md` - the review entry format.
