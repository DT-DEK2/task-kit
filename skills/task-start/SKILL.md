---
name: task-start
description: The assignee's side of a task - pick up an assigned task, mark it blocked, or hand it in for review with evidence for every acceptance criterion. Use whenever someone starts, resumes, gets stuck on or finishes an assigned task - "nhận task", "bắt đầu TASK-001", "làm task này", "task bị kẹt", "báo blocked", "nộp task", "báo xong", "xong task rồi", "submit for review", "start TASK-001", "pick up this task", "I'm blocked on", "hand in", "mark ready for review". It records status and evidence in the task file; doing the work itself follows the brief's scope.
---

# Task Start

The brief is the contract. This skill moves a task through the assignee's part of the
lifecycle in `docs/tasks/README.md` and leaves a trace in the file at every step.

## Non-goals

- Do not change requirements, acceptance criteria, scope or the review log. If the brief is
  wrong, say so and ask the requester to change it with `task-brief`.
- Do not mark anything Done. Only a review does that.
- Do not report an acceptance criterion as passing without pasted output.

## Mode: start

1. Find the task file from the id or title. If several match, ask.
2. Run `python3 docs/tasks/tasks.py lint TASK-NNN`. If it has errors, report them and stop;
   the requester fixes the brief.
3. Check readiness and report what fails:
   - every task in `Depends on` is `Done` (the board shows `WAITING:` otherwise);
   - no open question blocks the first requirement;
   - `Assignee` is set. If it is TBD, use the name the user gives, else `git config user.name`.
4. If not ready, stop and offer the `block` mode. Start anyway only when the user says so,
   and say so in the reply.
5. Set `Status` to `In progress` and `Start` to today's date.
6. Reply with the requirements as a checklist, the out-of-scope list, and the first step.
7. While the work goes on, anything found outside Scope becomes an open question in the
   file, not extra work.

## Mode: block

1. Set `Status` to `Blocked`.
2. Add the reason as an open question in the form
   `- [ ] Qn: <question> - answered by <person>, needed by <date>`.
   When it is answered, tick it (`- [x]`) and append the answer and date; never delete it.
3. When unblocked, tick the question with its answer and set the previous status back.

## Mode: submit

1. Make sure the changes are in a pull request (or pushed commits). For every acceptance
   criterion, run its check when it is read-only or the brief asks for it, and put the
   command and the lines of output that prove it in the pull request description, one
   heading per criterion. A check that cannot be run here is listed there as missing.
   Under `## Evidence` in the task file, replace `- None yet.` with the GitHub link:
   `- PR: https://github.com/<org>/<repo>/pull/<n>`.
2. Tick the checkbox of each criterion the evidence supports. Leave it unticked otherwise
   and say why in the reply. A tick is the assignee's claim, not acceptance.
3. Re-run any negative check (expected "no matches", "zero rows") against the baseline in
   Context and confirm the baseline was non-empty.
4. Set `Status` to `In review`. `Reviewer` must be set; if it is TBD, ask the user who reviews.
5. Run `python3 docs/tasks/tasks.py lint TASK-NNN` and `python3 docs/tasks/tasks.py board`.
6. Reply with a message for the reviewer (three to five lines, in their language): the task
   id and file, which criteria have evidence, anything left unticked, and what to re-run.

## Rules

- Evidence links are appended, never edited after a review has read them. A resubmission
  after `Rework needed` adds the new link (or the same PR with new commits) on a new line.
- English, ASCII only in the task file; messages to people may use their language.

## Output contract

- The task file with updated `Status` (and `Start` in start mode) and the GitHub link under
  Evidence (submit mode).
- An updated board.
- One chat message: what changed, what is next, and the message to forward when there is
  one.
