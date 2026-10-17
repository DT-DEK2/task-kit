#!/usr/bin/env python3
"""Mechanical helper for the docs/tasks handoff folder. Standard library only.

The task files are the source of truth. This script never changes a task's content;
`new` creates a file from the template and `board` rewrites only the status board
section of README.md.

Usage:
  python3 docs/tasks/tasks.py next-id
  python3 docs/tasks/tasks.py new <kebab-slug> --title "..." [--project P] [--epic E]
                                  [--platform 11st,gmarket] [--requester R] [--assignee A]
                                  [--leader L] [--reviewer V] [--estimate YYYY-MM-DD]
                                  [--priority P2] [--due YYYY-MM-DD] [--depends TASK-001,...]
  python3 docs/tasks/tasks.py lint [TASK-NNN ...]
  python3 docs/tasks/tasks.py board [--check] [--today YYYY-MM-DD]
  python3 docs/tasks/tasks.py version

Exit codes: 0 ok, 1 lint errors (or board out of date with --check), 2 usage or setup error.
"""

# Local dates are intended (the board is read in the team's timezone), git comes from PATH,
# and lint_task is one flat list of independent checks.
# ruff: noqa: DTZ011, S607, PLR0912, PLR0915

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys

from dataclasses import dataclass, field
from pathlib import Path


VERSION = "1.2.0"

TASKS_DIR = Path(__file__).resolve().parent
README = TASKS_DIR / "README.md"
TEMPLATE = TASKS_DIR / "_template.md"
BOARD_START = "<!-- status-board:start -->"
BOARD_END = "<!-- status-board:end -->"

STATUSES = ("Todo", "In progress", "Blocked", "In review", "Done", "Dropped")
OPEN_STATUSES = ("Todo", "In progress", "Blocked", "In review")
# Same order as the Notion columns, so the file header and the database read alike.
HEADER_FIELDS = (
    "Project",
    "Epic",
    "Platform",
    "Status",
    "Priority",
    "Assignee",
    "Requester",
    "Leader",
    "Reviewer",
    "Start",
    "Estimate",
    "Due",
    "Created",
    "Depends on",
    "Issue",
)
PEOPLE_FIELDS = ("Requester", "Assignee", "Leader", "Reviewer")
REQUIRED_SECTIONS = (
    "Goal",
    "Context",
    "Scope",
    "Requirements",
    "Deliverables",
    "Acceptance criteria",
    "Risks and notes",
    "References",
    "Open questions",
    "Evidence",
    "Review log",
)
# Sections that make up the brief itself; Evidence and logs grow with the work.
BRIEF_SECTIONS = REQUIRED_SECTIONS[: REQUIRED_SECTIONS.index("Open questions") + 1]
BRIEF_LINE_LIMIT = 200
STALE_DAYS = 7

PLACEHOLDERS = (
    "<short imperative title>",
    "<name, or TBD>",
    "YYYY-MM-DD",
    "- R1: ...",
    "AC1: <command to run",
    "<path>",
    "<path:line>",
)

ID_RE = re.compile(r"TASK-\d{3,}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REQ_RE = re.compile(r"^- R(\d+):")
AC_RE = re.compile(r"^- \[( |x|X)\] AC(\d+):")
GITHUB_RE = re.compile(r"https://github\.com/\S+")
REVIEW_RE = re.compile(r"^### Review (\d{4}-\d{2}-\d{2})")
DECISION_RE = re.compile(r"^Decision:\s*(Accepted|Rework needed)\b")
REF_RE = re.compile(r"`([A-Za-z0-9_./{},-]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?`")
DEPENDS_RE = re.compile(r"^(none|TASK-\d{3,}(\s*,\s*TASK-\d{3,})*)$", re.IGNORECASE)


@dataclass
class Review:
    date: str
    decision: str | None


@dataclass
class Task:
    path: Path
    id: str
    title: str
    lines: list[str]
    fields: dict[str, str] = field(default_factory=dict)
    sections: dict[str, list[tuple[int, str]]] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.fields.get("Status", "").split("(")[0].strip()

    @property
    def depends(self) -> list[str]:
        return ID_RE.findall(self.fields.get("Depends on", ""))

    def section(self, name: str) -> list[tuple[int, str]]:
        return self.sections.get(name, [])

    def requirements(self) -> list[int]:
        return [
            int(m.group(1))
            for _, s in self.section("Requirements")
            if (m := REQ_RE.match(s))
        ]

    def criteria(self) -> list[int]:
        return [
            int(m.group(2))
            for _, s in self.section("Acceptance criteria")
            if (m := AC_RE.match(s))
        ]

    def evidence(self) -> list[str]:
        """GitHub links (pull request or commit) listed under Evidence."""
        return [
            m.group(0).rstrip(").,")
            for _, s in self.section("Evidence")
            for m in GITHUB_RE.finditer(s)
        ]

    def reviews(self) -> list[Review]:
        out: list[Review] = []
        for _, s in self.section("Review log"):
            if m := REVIEW_RE.match(s):
                out.append(Review(m.group(1), None))
            elif out and out[-1].decision is None and (m := DECISION_RE.match(s)):
                out[-1].decision = m.group(1)
        return out

    def questions(self) -> list[tuple[bool, str]]:
        """Open questions as (answered, text). `- [x] Qn:` is answered; `- [ ] Qn:` and
        the older `- Qn:` are open. Wrapped continuation lines are joined."""
        out: list[tuple[bool, str]] = []
        for _, s in self.section("Open questions"):
            if m := re.match(r"^- (?:\[( |x|X)\] )?(Q\d+:.*)$", s):
                out.append((m.group(1) in ("x", "X"), m.group(2).strip()))
            elif out and s.startswith("  ") and s.strip():
                answered, text = out[-1]
                out[-1] = (answered, f"{text} {s.strip()}")
        return out

    def open_questions(self) -> list[str]:
        return [text for answered, text in self.questions() if not answered]

    @property
    def platforms(self) -> list[str]:
        value = self.fields.get("Platform", "none")
        if value.lower() in ("none", "tbd", ""):
            return []
        return [p.strip() for p in value.split(",") if p.strip()]

    def last_commit(self) -> tuple[str, str, str] | None:
        """(date, author email, subject) of the latest git commit touching the file.
        The history of a task lives in git, not in the file."""
        try:
            out = subprocess.run(
                ["git", "log", "-1", "--format=%as%x1f%ae%x1f%s", "--", self.path.name],
                cwd=self.path.parent,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
        parts = out.split("\x1f")
        return (
            (parts[0], parts[1], parts[2])
            if len(parts) == len(("d", "a", "s"))
            else None
        )

    def started(self) -> str | None:
        """The Start date the assignee set when the task moved to In progress."""
        value = self.fields.get("Start", "TBD")
        return value if DATE_RE.fullmatch(value) else None

    def completed(self) -> str | None:
        """Date of the accepting review, when the task is Done."""
        reviews = self.reviews()
        if self.status == "Done" and reviews and reviews[-1].decision == "Accepted":
            return reviews[-1].date
        return None

    def last_activity(self) -> str | None:
        dates = [self.fields.get("Created", ""), self.fields.get("Start", "")]
        dates += [r.date for r in self.reviews()]
        if commit := self.last_commit():
            dates.append(commit[0])
        dates = [d for d in dates if DATE_RE.fullmatch(d)]
        return max(dates) if dates else None


def parse(path: Path) -> Task:
    lines = path.read_text(encoding="utf-8").splitlines()
    first = lines[0] if lines else ""
    m = re.match(r"^# (TASK-\d{3,}) - (.+)$", first)
    task_id = (
        m.group(1)
        if m
        else path.name.split("-", 2)[0] + "-" + path.name.split("-", 2)[1]
    )
    task = Task(
        path=path, id=task_id, title=m.group(2).strip() if m else "", lines=lines
    )

    current: str | None = None
    in_fence = False
    for no, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            current = line[3:].strip()
            task.sections.setdefault(current, [])
            continue
        if current is None:
            if line.startswith("|") and not line.startswith("| ---"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) > 1 and cells[0] != "Field":
                    task.fields[cells[0]] = cells[1]
            continue
        task.sections[current].append((no, line))
    return task


def load_tasks() -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    for path in sorted(TASKS_DIR.glob("TASK-*.md")):
        task = parse(path)
        tasks[task.id] = task
    return tasks


def repo_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=TASKS_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return TASKS_DIR.parent.parent


def repo_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]


def next_id(tasks: dict[str, Task]) -> str:
    seen = [int(i.split("-")[1]) for i in tasks]
    for path in [README, *TASKS_DIR.glob("PLAN-*.md")]:
        if path.exists():
            seen += [
                int(i.split("-")[1])
                for i in ID_RE.findall(path.read_text(encoding="utf-8"))
            ]
    return f"TASK-{(max(seen) if seen else 0) + 1:03d}"


# ---------------------------------------------------------------- lint


def find_cycles(tasks: dict[str, Task]) -> list[list[str]]:
    cycles: list[list[str]] = []
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        stack.append(node)
        for dep in tasks[node].depends if node in tasks else []:
            if dep not in tasks:
                continue
            if state.get(dep) == 1:
                cycles.append([*stack[stack.index(dep) :], dep])
            elif state.get(dep) is None:
                visit(dep, stack)
        stack.pop()
        state[node] = 2

    for node in tasks:
        if node not in state:
            visit(node, [])
    return cycles


def lint_task(
    task: Task, tasks: dict[str, Task], root: Path, by_name: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    err = errors.append
    warn = warnings.append

    if not task.title:
        err("line 1: title must be '# TASK-NNN - <title>'")
    if not task.path.name.startswith(task.id + "-"):
        err(f"file name does not start with {task.id}-")

    for name in HEADER_FIELDS:
        if name not in task.fields:
            err(f"header: missing field '{name}'")
    status = task.status
    if status and status not in STATUSES:
        err(
            f"header: Status '{task.fields['Status']}' is not one of {', '.join(STATUSES)}"
        )
    if task.fields.get("Priority", "P1") not in ("P1", "P2", "P3"):
        err("header: Priority must be P1, P2 or P3")
    for name in ("Start", "Due", "Created", "Estimate"):
        value = task.fields.get(name, "TBD")
        if value != "TBD" and not DATE_RE.fullmatch(value):
            err(f"header: {name} must be YYYY-MM-DD or TBD, got '{value}'")
    if task.fields.get("Created") == "TBD":
        err("header: Created must be a date")

    depends_raw = task.fields.get("Depends on", "none")
    if not DEPENDS_RE.match(depends_raw):
        err(
            f"header: Depends on must be 'none' or a comma list of task ids, got '{depends_raw}'."
            " Put ordering notes in Risks and notes."
        )
    for dep in task.depends:
        if dep == task.id:
            err("header: task depends on itself")
        elif dep not in tasks:
            err(f"header: Depends on {dep}, which has no task file")
        elif tasks[dep].status == "Dropped" and task.status != "Dropped":
            err(f"header: Depends on {dep}, which is Dropped; point at its replacement")

    estimate = task.fields.get("Estimate", "TBD")
    if estimate != "TBD" and not DATE_RE.fullmatch(estimate):
        err(
            f"header: Estimate is the expected finish date, YYYY-MM-DD or TBD, got '{estimate}'"
        )
    issue = task.fields.get("Issue", "none")
    if issue.lower() != "none" and not re.fullmatch(
        r"https://github\.com/\S+/issues/\d+", issue
    ):
        err(f"header: Issue must be 'none' or a GitHub issue URL, got '{issue}'")
    platform = task.fields.get("Platform", "none")
    if platform.lower() not in ("none", "tbd") and not re.fullmatch(
        r"[\w.-]+(\s*,\s*[\w.-]+)*", platform
    ):
        err(
            f"header: Platform must be 'none' or a comma list such as '11st, gmarket', got '{platform}'"
        )

    assignee = task.fields.get("Assignee", "TBD")
    reviewer = task.fields.get("Reviewer", "TBD")
    assignee_known = not assignee.upper().startswith("TBD")
    reviewer_known = not reviewer.upper().startswith("TBD")
    if (
        assignee_known
        and reviewer_known
        and assignee.split()[0].lower() == reviewer.split()[0].lower()
    ):
        err("header: Reviewer must be a different person from Assignee")
    if status in ("In progress", "In review", "Done") and not task.started():
        warn(f"header: Status is {status} but Start is not set")
    if status in ("In progress", "In review", "Done") and not assignee_known:
        err(f"header: Status is {status} but Assignee is TBD")
    if status in ("In review", "Done") and not reviewer_known:
        err(f"header: Status is {status} but Reviewer is TBD")

    for name in REQUIRED_SECTIONS:
        if name not in task.sections:
            err(f"missing section '## {name}'")

    for label, numbers in (("R", task.requirements()), ("AC", task.criteria())):
        if not numbers:
            err(f"no numbered {label}1..{label}n items")
        elif numbers != list(range(1, len(numbers) + 1)):
            err(f"{label} numbering is not 1..n in order: {numbers}")

    brief_lines = sum(len(task.section(s)) for s in BRIEF_SECTIONS) + 12
    if brief_lines > BRIEF_LINE_LIMIT:
        warn(
            f"brief is about {brief_lines} lines (limit {BRIEF_LINE_LIMIT}); split the task or"
            " move shared procedure into a RUNBOOK file"
        )

    for no, line in enumerate(task.lines, start=1):
        if line.startswith("    "):
            continue  # indented example blocks in the template are guidance, not content
        for ph in PLACEHOLDERS:
            if ph in line:
                warn(f"line {no}: template placeholder left: '{ph}'")

    # People write questions in their own language.
    assignment = {no for name in ("Open questions",) for no, _ in task.section(name)}
    non_ascii = [
        no
        for no, line in enumerate(task.lines, 1)
        if no not in assignment and not line.isascii()
    ]
    if non_ascii:
        warn(f"non-ASCII text outside the open questions on lines {non_ascii[:5]}")

    for no, line in enumerate(task.lines, start=1):
        for m in REF_RE.finditer(line):
            ref, start, end = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            if "{" in ref:
                continue
            if "/" in ref:
                candidates = [ref] if (root / ref).is_file() else []
            else:
                candidates = by_name.get(ref, [])
            if not candidates:
                err(f"line {no}: reference `{ref}:{start}` - file not found")
                continue
            if len(candidates) > 1:
                warn(
                    f"line {no}: reference `{ref}` is ambiguous ({len(candidates)} files); use the full path"
                )
                continue
            length = len(
                (root / candidates[0])
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
            )
            if end > length or start < 1 or end < start:
                err(
                    f"line {no}: reference `{ref}:{m.group(2)}` is outside the file ({length} lines)"
                )

    reviews = task.reviews()
    for review in reviews:
        if review.decision is None:
            err(
                f"review {review.date}: missing 'Decision: Accepted' or 'Decision: Rework needed'"
            )
    latest = reviews[-1].decision if reviews else None
    if status == "Done" and latest != "Accepted":
        err("Status is Done but the latest review entry is not 'Decision: Accepted'")
    if status == "Done" and task.open_questions():
        warn("Status is Done but Open questions still lists items")
    if status in ("In review", "Done"):
        if not task.evidence():
            err(f"Status is {status} but Evidence has no GitHub link to the changes")
        waiting = [d for d in task.depends if d in tasks and tasks[d].status != "Done"]
        if waiting:
            warn(f"Status is {status} while dependencies are not Done: {waiting}")

    return errors, warnings


def cmd_lint(args: argparse.Namespace) -> int:
    tasks = load_tasks()
    root = repo_root()
    by_name: dict[str, list[str]] = {}
    for rel in repo_files(root):
        by_name.setdefault(Path(rel).name, []).append(rel)

    selected = args.ids or list(tasks)
    unknown = [i for i in selected if i not in tasks]
    if unknown:
        print(f"unknown task ids: {', '.join(unknown)}", file=sys.stderr)
        return 2

    total_errors = 0
    for cycle in find_cycles(tasks):
        if any(i in selected for i in cycle):
            print(f"ERROR dependency cycle: {' -> '.join(cycle)}")
            total_errors += 1
    for task_id in selected:
        errors, warnings = lint_task(tasks[task_id], tasks, root, by_name)
        total_errors += len(errors)
        rel = tasks[task_id].path.name
        if not errors and not warnings:
            print(f"OK    {rel}")
        for e in errors:
            print(f"ERROR {rel}: {e}")
        for w in warnings:
            print(f"WARN  {rel}: {w}")
    print(f"\n{len(selected)} task(s), {total_errors} error(s)")
    return 1 if total_errors else 0


# ---------------------------------------------------------------- board


def flags_for(
    task: Task, tasks: dict[str, Task], today: dt.date, lint_errors: int
) -> list[str]:
    flags: list[str] = []
    status = task.status
    due = task.fields.get("Due", "TBD")
    if (
        status in OPEN_STATUSES
        and DATE_RE.fullmatch(due)
        and dt.date.fromisoformat(due) < today
    ):
        flags.append("OVERDUE")
    estimate = task.fields.get("Estimate", "TBD")
    if (
        status in OPEN_STATUSES
        and DATE_RE.fullmatch(estimate)
        and DATE_RE.fullmatch(due)
        and estimate > due
    ):
        flags.append("AT-RISK")
    last = task.last_activity()
    stale = last and (today - dt.date.fromisoformat(last)).days > STALE_DAYS
    if status in ("In progress", "In review") and stale:
        flags.append("STALE")
    if status in ("Todo", "In progress", "Blocked"):
        waiting = [d for d in task.depends if d in tasks and tasks[d].status != "Done"]
        if waiting:
            flags.append("WAITING:" + ",".join(waiting))
    reviews = task.reviews()
    if status == "Done" and (not reviews or reviews[-1].decision != "Accepted"):
        flags.append("UNVERIFIED")
    if status == "In review" and reviews and reviews[-1].decision == "Rework needed":
        flags.append("RESUBMITTED")
    if status in OPEN_STATUSES and task.open_questions():
        flags.append(f"OPEN-Q:{len(task.open_questions())}")
    if lint_errors:
        flags.append(f"LINT:{lint_errors}")
    return flags


def build_board(tasks: dict[str, Task], today: dt.date) -> tuple[str, list[str]]:
    root = repo_root()
    by_name: dict[str, list[str]] = {}
    for rel in repo_files(root):
        by_name.setdefault(Path(rel).name, []).append(rel)

    rows = [
        "| ID | Task | Assignee | Reviewer | Status | Due | Depends on | Flags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    digest: list[str] = []
    for task in tasks.values():
        errors, _ = lint_task(task, tasks, root, by_name)
        flags = flags_for(task, tasks, today, len(errors))
        f = task.fields
        rows.append(
            "| [{id}]({file}) | {title} | {assignee} | {reviewer} | {status} | {due} | {deps} | {flags} |".format(
                id=task.id,
                file=task.path.name,
                title=task.title.replace("|", "/"),
                assignee=f.get("Assignee", "TBD"),
                reviewer=f.get("Reviewer", "TBD"),
                status=f.get("Status", "?"),
                due=f.get("Due", "TBD"),
                deps=", ".join(task.depends) or "none",
                flags=" ".join(flags) or "-",
            )
        )
        digest.append(
            f"{task.id} [{task.status}] {' '.join(flags) or '-'} - {task.title}"
        )
    return "\n".join(rows), digest


def cmd_board(args: argparse.Namespace) -> int:
    if not README.exists():
        print(f"{README} not found", file=sys.stderr)
        return 2
    text = README.read_text(encoding="utf-8")
    if BOARD_START not in text or BOARD_END not in text:
        print(
            f"{README.name} has no {BOARD_START} / {BOARD_END} markers", file=sys.stderr
        )
        return 2
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    tasks = load_tasks()
    table, digest = build_board(tasks, today)

    head, rest = text.split(BOARD_START, 1)
    _, tail = rest.split(BOARD_END, 1)
    new_text = f"{head}{BOARD_START}\n\n{table}\n\n{BOARD_END}{tail}"

    counts = {s: sum(1 for t in tasks.values() if t.status == s) for s in STATUSES}
    print("Counts: " + ", ".join(f"{s} {n}" for s, n in counts.items() if n))
    print("\n".join(digest))

    if args.check:
        if new_text != text:
            print("\nboard is out of date; run without --check to rewrite it")
            return 1
        print("\nboard is up to date")
        return 0
    if new_text != text:
        README.write_text(new_text, encoding="utf-8")
        print(f"\nwrote {README.name}")
    else:
        print("\nboard already up to date")
    return 0


# ---------------------------------------------------------------- new


def cmd_new(args: argparse.Namespace) -> int:
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", args.slug):
        print(
            "slug must be kebab-case: lowercase letters, digits and single hyphens",
            file=sys.stderr,
        )
        return 2
    if not TEMPLATE.exists():
        print(f"{TEMPLATE} not found", file=sys.stderr)
        return 2
    tasks = load_tasks()
    task_id = next_id(tasks)
    path = TASKS_DIR / f"{task_id}-{args.slug}.md"
    if path.exists():
        print(f"{path.name} already exists; refusing to overwrite", file=sys.stderr)
        return 2
    depends = (
        args.depends.replace(" ", "").replace(",", ", ") if args.depends else "none"
    )
    if not DEPENDS_RE.match(depends):
        print("--depends must be a comma list of task ids", file=sys.stderr)
        return 2
    today = dt.date.today().isoformat()
    requester = args.requester or args.author or "TBD"
    values = {
        "Project": args.project or "TBD",
        "Epic": args.epic or "none",
        "Platform": args.platform or "none",
        # The creator hands the task out and, unless someone else is named, reviews it.
        "Requester": requester,
        "Assignee": args.assignee or "TBD",
        "Leader": args.leader or "TBD",
        "Reviewer": args.reviewer or requester,
        "Start": "TBD",
        "Estimate": args.estimate or "TBD",
        "Status": "Todo",
        "Priority": args.priority,
        "Due": args.due or "TBD",
        "Created": today,
        "Depends on": depends,
        "Issue": "none",
    }
    out: list[str] = []
    for raw in TEMPLATE.read_text(encoding="utf-8").splitlines():
        line = raw
        if raw.startswith("# TASK-NNN"):
            line = f"# {task_id} - {args.title}"
        elif raw.startswith("| ") and not raw.startswith(("| Field", "| ---")):
            name = raw.strip("|").split("|")[0].strip()
            if name in values:
                line = f"| {name} | {values[name]} |"
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(path.relative_to(repo_root()) if path.is_relative_to(repo_root()) else path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version")
    sub.add_parser("next-id")

    p_new = sub.add_parser("new")
    p_new.add_argument("slug")
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--project")
    p_new.add_argument("--epic", help="the plan or theme this task belongs to")
    p_new.add_argument(
        "--platform", help="comma list of platforms (marketplaces), or none"
    )
    p_new.add_argument("--requester", help="who hands the task out (default: --author)")
    p_new.add_argument("--assignee", help="who does the work")
    p_new.add_argument("--leader", help="team lead of the assignee")
    p_new.add_argument(
        "--reviewer", help="who accepts the work (default: the requester)"
    )
    p_new.add_argument("--estimate", help="expected finish date, YYYY-MM-DD")
    p_new.add_argument("--priority", default="P2", choices=("P1", "P2", "P3"))
    p_new.add_argument("--due")
    p_new.add_argument("--depends")
    p_new.add_argument(
        "--author", help="who creates the task (default requester and reviewer)"
    )

    p_lint = sub.add_parser("lint")
    p_lint.add_argument("ids", nargs="*")

    p_board = sub.add_parser("board")
    p_board.add_argument("--check", action="store_true")
    p_board.add_argument("--today")

    args = parser.parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    if args.command == "next-id":
        print(next_id(load_tasks()))
        return 0
    return {"new": cmd_new, "lint": cmd_lint, "board": cmd_board}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
