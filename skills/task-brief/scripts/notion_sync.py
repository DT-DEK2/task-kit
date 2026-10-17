#!/usr/bin/env python3
"""One-way sync of docs/tasks into a Notion database. Standard library only.

The repository stays the source of truth: Notion is a read-only view. Pages are matched
on the `ID` property, so re-running never creates duplicates. A page whose task file is
gone is flagged REMOVED, never deleted. Pages without an ID (empty rows) are ignored.

People columns (Person, Owner, Leader, Reviewer) are Notion People. Task files name people
by email (preferred) or exact Notion name; the integration needs the capability "Read user
information including email addresses" to resolve them. Unresolved names are reported and
left empty.

Configuration comes from the environment, or from `.env` at the repository root:
  NOTION_TOKEN          internal integration secret (the database must be shared with it)
  NOTION_DATABASE_ID    the database id (32 hex characters from its URL, before ?v=)
  NOTION_SYNC_BRANCH    branch used for the File links to GitHub (default: main)

Usage:
  python3 docs/tasks/notion_sync.py --create-template PARENT_PAGE_ID [--title T] [--dry-run]
                                     a new page with an empty task database, ready to
                                     publish as a template or to sync into
  python3 docs/tasks/notion_sync.py --setup [--prune] [--dry-run]   also orders the table views
                                     create, rename or convert columns; --prune also deletes
                                     unused columns that are empty in every row
  python3 docs/tasks/notion_sync.py [--dry-run] [--force] [--only TASK-001 ...]
                                     [--archive-removed] [--no-pull]

Exit codes: 0 ok, 1 Notion API error, 2 configuration error.
"""

# Local dates are intended, git comes from PATH, urlopen only ever sees the fixed
# https://api.notion.com base, and setup/sync are flat sequences of independent steps.
# ruff: noqa: DTZ011, S607, S310, PLR0912, PLR0915

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from pathlib import Path

sys.dont_write_bytecode = (
    True  # importing tasks must not leave __pycache__ in docs/tasks
)
import tasks as tk  # noqa: E402


API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
VIEWS_VERSION = "2026-03-11"  # the Views API needs 2025-09-03 or later
HIDDEN_COLUMNS = ("Hash",)
# Column order in table views; columns not listed follow in SCHEMA order.
VIEW_ORDER = ("Project", "Task", "ID", "Issue", "Epic", "Platform")
COLUMN_WIDTHS = {
    "Task": 360,
    "ID": 100,
    "Summary": 360,
    "Last change": 300,
    "Flags": 180,
}
TEXT_LIMIT = 2000
CHILDREN_LIMIT = 100
WRITE_PAUSE = 0.35  # Notion allows about three requests per second per integration
MAX_RETRIES = 5
HTTP_RATE_LIMIT = 429
HTTP_FORBIDDEN = 403
HTTP_SERVER_ERROR = 500
SUMMARY_LIMIT = 300

TITLE_PROP = "Task"
ID_PROP = "ID"
FLAG_COLORS = {
    "OVERDUE": "red",
    "AT-RISK": "orange",
    "STALE": "brown",
    "WAITING": "yellow",
    "UNVERIFIED": "purple",
    "RESUBMITTED": "blue",
    "OPEN-Q": "pink",
    "LINT": "red",
    "REMOVED": "gray",
}
# Notion column -> task header field, for the people columns.
PEOPLE_COLUMNS = {
    "Person": "Assignee",
    "Owner": "Requester",
    "Leader": "Leader",
    "Reviewer": "Reviewer",
}


def _select(*options: tuple[str, str]) -> dict:
    return {"options": [{"name": n, "color": c} for n, c in options]}


# Column order: --setup applies it to every table view through the Views API.
SCHEMA: dict[str, dict] = {
    ID_PROP: {"rich_text": {}},
    "Project": {"select": {}},
    "Epic": {"select": {}},
    "Platform": {"multi_select": {}},
    "Status": {
        "select": _select(
            ("Todo", "gray"),
            ("In progress", "blue"),
            ("Blocked", "red"),
            ("In review", "yellow"),
            ("Done", "green"),
            ("Dropped", "brown"),
        )
    },
    "Priority": {"select": _select(("P1", "red"), ("P2", "orange"), ("P3", "gray"))},
    "Person": {"people": {}},
    "Owner": {"people": {}},
    "Leader": {"people": {}},
    "Reviewer": {"people": {}},
    "Start": {"date": {}},
    "Estimate": {"date": {}},
    "Due": {"date": {}},
    "Completed": {"date": {}},
    "Summary": {"rich_text": {}},
    "Depends on": {"rich_text": {}},
    "Flags": {"multi_select": _select(*FLAG_COLORS.items())},
    "Open questions": {"number": {"format": "number"}},
    "Last changed by": {"people": {}},
    "Last change": {"rich_text": {}},
    "Issue": {"url": {}},
    "File": {"url": {}},
    "Hash": {"rich_text": {}},
}
# Columns earlier versions of this script created and no longer write. Their values were
# always derived by the sync, so --setup deletes them without losing anything.
RETIRED_COLUMNS = ("Synced",)
# Existing columns whose type setup may convert (data in them is rewritten by the sync).
CONVERTIBLE = {("rich_text", "people"), ("number", "date")}


class NotionError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- config


def load_env(root: Path) -> None:
    env_file = root / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def github_base(root: Path) -> str | None:
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.match(
        r"^(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?$", url
    )
    return f"https://github.com/{m.group(1)}" if m else None


# ---------------------------------------------------------------- api


class Client:
    def __init__(self, token: str, dry_run: bool) -> None:
        self.token = token
        self.dry_run = dry_run
        self.writes = 0

    def call(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        version: str = NOTION_VERSION,
    ) -> dict:
        is_write = method != "GET" and not path.endswith("/query")
        if is_write and self.dry_run:
            self.writes += 1
            return {}
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(MAX_RETRIES):
            req = urllib.request.Request(f"{API}/{path}", data=data, method=method)
            req.add_header("Authorization", f"Bearer {self.token}")
            req.add_header("Notion-Version", version)
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    if is_write:
                        self.writes += 1
                        time.sleep(WRITE_PAUSE)
                    return json.loads(resp.read() or b"{}")
            except urllib.error.HTTPError as e:
                if e.code == HTTP_RATE_LIMIT or e.code >= HTTP_SERVER_ERROR:
                    time.sleep(float(e.headers.get("Retry-After", 1 + attempt)))
                    continue
                try:
                    detail = json.loads(e.read())
                    message = f"{detail.get('code')}: {detail.get('message')}"
                except ValueError:
                    message = str(e)
                raise NotionError(
                    f"{method} {path} -> {e.code} {message}", e.code
                ) from None
            except TimeoutError:
                # A write that timed out may still have been applied; resending it could
                # create a duplicate page. Reads are safe to retry.
                if is_write:
                    raise NotionError(
                        f"{method} {path} -> timed out; Notion may have applied it."
                        " Re-run the sync: pages are matched by ID, so nothing is duplicated."
                    ) from None
                if attempt == MAX_RETRIES - 1:
                    raise NotionError(f"{method} {path} -> timed out") from None
                time.sleep(1 + attempt)
            except urllib.error.URLError as e:
                if attempt == MAX_RETRIES - 1:
                    raise NotionError(f"{method} {path} -> {e.reason}") from None
                time.sleep(1 + attempt)
        raise NotionError(f"{method} {path} -> gave up after {MAX_RETRIES} attempts")

    def paginate(self, method: str, path: str, body: dict | None = None) -> list[dict]:
        out: list[dict] = []
        cursor: str | None = None
        while True:
            if method == "GET":
                sep = "&" if "?" in path else "?"
                url = path + (f"{sep}start_cursor={cursor}" if cursor else "")
                res = self.call("GET", url)
            else:
                res = self.call(
                    method,
                    path,
                    {**(body or {}), **({"start_cursor": cursor} if cursor else {})},
                )
            out += res.get("results", [])
            if not res.get("has_more"):
                return out
            cursor = res["next_cursor"]


# ---------------------------------------------------------------- people


class People:
    """Resolves an email or Notion name from a task header to a Notion user id."""

    def __init__(self, client: Client) -> None:
        self.by_key: dict[str, str] = {}
        self.names: dict[str, str] = {}
        self.emails: dict[str, str] = {}
        self.available = True
        # The integration's own user: blocks it created are ones this script pushed.
        self.me: str | None = client.call("GET", "users/me").get("id")
        try:
            users = client.paginate("GET", "users?page_size=100")
        except NotionError as e:
            if e.status != HTTP_FORBIDDEN:
                raise
            self.available = False
            return
        for user in users:
            if user.get("type") != "person":
                continue
            self.names[user["id"]] = user.get("name") or ""
            email = user.get("person", {}).get("email")
            if email:
                self.by_key[email.lower()] = user["id"]
                self.emails[user["id"]] = email
            if user.get("name"):
                self.by_key.setdefault(user["name"].strip().lower(), user["id"])

    def resolve(self, value: str) -> tuple[list[dict], str | None]:
        """Return the people property value and an unresolved name, if any."""
        if not value or value.upper().startswith("TBD"):
            return [], None
        m = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", value)
        key = (m.group(0) if m else value).strip().lower()
        user_id = self.by_key.get(key)
        if user_id:
            return [{"object": "user", "id": user_id}], None
        return [], value

    def who(self, user_id: str | None) -> str:
        """How a Notion user is written in a task file: email, else name."""
        if not user_id:
            return "unknown"
        return (
            self.emails.get(user_id)
            or self.names.get(user_id)
            or f"notion-user-{user_id[:8]}"
        )


# ---------------------------------------------------------------- questions from Notion

QUESTIONS_HEADING = "Open questions"
QUESTIONS_HINT = (
    "Add a checkbox below to ask a question, tick one when it is answered. The next sync"
    " copies both into the task file."
)


def notion_questions(client: Client, page_id: str) -> list[dict]:
    """Checkboxes under the Open questions heading of a task page."""
    out: list[dict] = []
    inside = False
    for b in client.paginate("GET", f"blocks/{page_id}/children?page_size=100"):
        kind = b["type"]
        if kind.startswith("heading_"):
            title = "".join(x["plain_text"] for x in b[kind]["rich_text"]).strip()
            inside = title.lower() == QUESTIONS_HEADING.lower()
            continue
        if inside and kind == "to_do":
            text = "".join(x["plain_text"] for x in b["to_do"]["rich_text"]).strip()
            if any(
                ch.isalnum() for ch in text
            ):  # skip "/" and other slash-command leftovers
                out.append(
                    {
                        "text": " ".join(text.split()),
                        "checked": b["to_do"]["checked"],
                        "created_by": b.get("created_by", {}).get("id"),
                        "edited_by": b.get("last_edited_by", {}).get("id"),
                        "created": b.get("created_time", "")[:10],
                        "edited": b.get("last_edited_time", "")[:10],
                    }
                )
    return out


def question_key(text: str) -> str:
    """Question text without its number, the "asked in Notion" suffix and markup."""
    text = re.sub(r"^Q\d+:\s*", "", " ".join(text.split()))
    text = re.sub(r"\s+- asked in Notion by .*$", "", text)
    return text.replace("`", "").strip().lower()


def pull_questions(
    task: tk.Task, found: list[dict], people: People, today: str, write: bool
) -> list[str]:
    """Copy questions added or ticked in Notion into the task file. Returns what changed."""
    repo = task.questions()
    by_number: dict[str, tuple[int, bool]] = {}
    for i, (answered, text) in enumerate(repo):
        if m := re.match(r"Q(\d+):", text):
            by_number[m.group(1)] = (i, answered)
    known = {question_key(text) for _, text in repo}
    numbers = [int(n) for n in by_number] or [0]

    ticks: list[tuple[str, dict]] = []
    new: list[tuple[int, dict]] = []
    for q in found:
        m = re.match(r"Q(\d+):", q["text"])
        if m and m.group(1) in by_number:
            if q["checked"] and not by_number[m.group(1)][1]:
                ticks.append((m.group(1), q))
            continue
        if q["created_by"] == people.me:
            continue  # pushed by this script earlier, not asked by a person
        if question_key(q["text"]) in known:
            continue
        numbers.append(max(numbers) + 1)
        new.append((numbers[-1], q))
    if not ticks and not new:
        return []

    changes = [
        f"Q{n} answered in Notion by {people.who(q['edited_by'])}" for n, q in ticks
    ]
    changes += [
        f"Q{n} added in Notion by {people.who(q['created_by'])}" for n, q in new
    ]
    if not write:
        return changes

    lines = list(task.lines)
    start = lines.index(f"## {QUESTIONS_HEADING}")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    section = lines[start + 1 : end]

    for number, q in ticks:
        i = next(
            i for i, s in enumerate(section) if re.match(rf"^- \[ \] Q{number}:", s)
        )
        section[i] = section[i].replace("- [ ]", "- [x]", 1)
        j = i + 1
        while j < len(section) and section[j].startswith("  ") and section[j].strip():
            j += 1
        note = f"  Answered in Notion by {people.who(q['edited_by'])}, {q['edited']}"
        repo_text = " ".join(repo[by_number[number][0]][1].split())
        section.insert(j, note + (f": {q['text']}" if q["text"] != repo_text else "."))

    if new:
        # drop the "- None." placeholder and its continuation lines
        kept: list[str] = []
        skipping = False
        for s in section:
            if re.match(r"^- None\b", s):
                skipping = True
                continue
            if skipping and s.startswith("  "):
                continue
            skipping = False
            kept.append(s)
        section = kept
        while section and not section[-1].strip():
            section.pop()
        if not section:
            section = [""]
        for number, q in new:
            who = people.who(q["created_by"])
            text = re.sub(
                r"^Q\d+:\s*", "", q["text"]
            )  # numbering is ours, not the typist's
            section.append(
                f"- [ ] Q{number}: {text} - asked in Notion by {who}, {q['created']}"
            )
        section.append("")

    lines[start + 1 : end] = section
    task.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changes


# ---------------------------------------------------------------- rendering


def rich(text: str, link: str | None = None) -> list[dict]:
    """Plain text to rich text, with `backtick` spans as inline code."""
    out: list[dict] = []
    for i, part in enumerate(re.split(r"`([^`]*)`", text)):
        for start in range(0, len(part), TEXT_LIMIT):
            chunk = part[start : start + TEXT_LIMIT]
            item: dict = {"type": "text", "text": {"content": chunk}}
            if link:
                item["text"]["link"] = {"url": link}
            if i % 2:
                item["annotations"] = {"code": True}
            out.append(item)
    return out[:100]


def list_items(lines: list[tuple[int, str]]) -> list[str]:
    items: list[str] = []
    for _, line in lines:
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()
    return items


def paragraphs(lines: list[tuple[int, str]]) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for _, line in [*lines, (0, "")]:
        if line.strip():
            current.append(line.strip())
        elif current:
            out.append(" ".join(current))
            current = []
    return out


def summary(task: tk.Task) -> str:
    goal = paragraphs(task.section("Goal"))
    if not goal:
        return ""
    first = re.split(r"(?<=\.)\s", goal[0], maxsplit=1)[0]
    return first if len(first) <= SUMMARY_LIMIT else first[: SUMMARY_LIMIT - 3] + "..."


def block(kind: str, text: str, **extra: object) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": rich(text), **extra}}


def render_body(task: tk.Task, file_url: str | None) -> list[dict]:
    blocks: list[dict] = []
    note = "Synced from the repository; change this task there, not here."
    if file_url:
        blocks.append(
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        *rich(note + " Source: "),
                        *rich(task.path.name, link=file_url),
                    ],
                    "icon": {"type": "emoji", "emoji": "\U0001f4c4"},
                },
            }
        )
    blocks.append(block("heading_2", "Goal"))
    blocks += [block("paragraph", p) for p in paragraphs(task.section("Goal"))]

    blocks.append(block("heading_2", "Requirements"))
    blocks += [
        block("bulleted_list_item", item)
        for item in list_items(task.section("Requirements"))
    ]

    blocks.append(block("heading_2", "Acceptance criteria"))
    for item in list_items(task.section("Acceptance criteria")):
        m = re.match(r"^\[( |x|X)\]\s*(.*)$", item)
        if m:
            blocks.append(block("to_do", m.group(2), checked=m.group(1) != " "))

    blocks.append(block("heading_2", QUESTIONS_HEADING))
    blocks.append(block("paragraph", QUESTIONS_HINT))
    blocks += [block("to_do", q, checked=done) for done, q in task.questions()]

    reviews = task.reviews()
    if reviews:
        last = reviews[-1]
        blocks.append(block("heading_2", "Latest review"))
        blocks.append(
            block(
                "paragraph", f"{last.date} - {last.decision or 'no decision recorded'}"
            )
        )
    return blocks


def text_prop(value: str) -> dict:
    return {"rich_text": rich(value) if value else []}


def date_prop(value: str | None) -> dict:
    return {"date": {"start": value} if value and tk.DATE_RE.fullmatch(value) else None}


def properties(
    task: tk.Task, flags: list[str], file_url: str | None, people: People
) -> tuple[dict, list[str]]:
    f = task.fields
    status = task.status if task.status in tk.STATUSES else None
    priority = f.get("Priority") if f.get("Priority") in ("P1", "P2", "P3") else None
    project = f.get("Project", "TBD")
    epic = f.get("Epic", "none")
    commit = task.last_commit()  # the history of a task is its git history
    last_who = commit[1] if commit else ""
    last_what = f"{commit[0]} - {commit[2]}" if commit else "not committed yet"

    props: dict = {
        TITLE_PROP: {"title": rich(f"{task.id} - {task.title}")},
        ID_PROP: text_prop(task.id),
        "Project": {"select": {"name": project} if project != "TBD" else None},
        "Epic": {
            "select": {"name": epic} if epic.lower() not in ("none", "tbd") else None
        },
        "Platform": {"multi_select": [{"name": n} for n in task.platforms]},
        "Status": {"select": {"name": status} if status else None},
        "Priority": {"select": {"name": priority} if priority else None},
        "Start": date_prop(task.started()),
        "Estimate": date_prop(f.get("Estimate")),
        "Due": date_prop(f.get("Due")),
        "Completed": date_prop(task.completed()),
        "Summary": text_prop(summary(task)),
        "Depends on": text_prop(", ".join(task.depends) or "none"),
        "Flags": {"multi_select": [{"name": n} for n in flags]},
        "Open questions": {"number": len(task.open_questions())},
        "Last changed by": {"people": people.resolve(last_who)[0]},
        "Last change": text_prop(last_what[:SUMMARY_LIMIT]),
        "Issue": {
            "url": f["Issue"] if f.get("Issue", "none").startswith("https://") else None
        },
        "File": {"url": file_url},
    }
    unresolved: list[str] = []
    for column, field_name in PEOPLE_COLUMNS.items():
        value, missing = people.resolve(f.get(field_name, ""))
        props[column] = {"people": value}
        if missing:
            unresolved.append(f"{field_name}={missing}")
    return props, unresolved


def plain(prop: dict) -> str:
    value = prop.get(prop.get("type", ""), [])
    return (
        "".join(x.get("plain_text", "") for x in value)
        if isinstance(value, list)
        else ""
    )


# ---------------------------------------------------------------- commands


# Property types that support the "is_not_empty" filter, so emptiness can be proven.
PRUNABLE = {
    "rich_text",
    "number",
    "select",
    "multi_select",
    "date",
    "people",
    "url",
    "email",
    "phone_number",
    "files",
    "status",
}


def is_empty_column(client: Client, database_id: str, name: str, kind: str) -> bool:
    res = client.call(
        "POST",
        f"databases/{database_id}/query",
        {"page_size": 1, "filter": {"property": name, kind: {"is_not_empty": True}}},
    )
    return not res.get("results")


def setup(client: Client, database_id: str, prune: bool = False) -> int:
    db = client.call("GET", f"databases/{database_id}")
    props: dict[str, dict] = db.get("properties", {})
    patch: dict[str, dict] = {}
    title_name = next((n for n, p in props.items() if p["type"] == "title"), None)
    if title_name and title_name != TITLE_PROP:
        patch[title_name] = {"name": TITLE_PROP}
        print(f"rename   {title_name!r} -> {TITLE_PROP!r}")
    problems = 0
    for name, spec in SCHEMA.items():
        kind = next(iter(spec))
        current = props.get(name, {}).get("type")
        if current is None:
            patch[name] = spec
            print(f"add      {name!r} ({kind})")
        elif current == kind:
            if kind in ("select", "multi_select") and spec[kind]:
                patch[name] = spec
                print(f"options  {name!r}")
        elif (current, kind) in CONVERTIBLE:
            patch[name] = spec
            print(f"convert  {name!r} {current} -> {kind}")
        else:
            print(
                f"CONFLICT {name!r} is {current}, expected {kind}; rename or delete it in Notion"
            )
            problems += 1
    for name, prop in props.items():
        if name in SCHEMA or name == title_name:
            continue
        kind = prop["type"]
        if name in RETIRED_COLUMNS:
            patch[name] = None
            print(f"delete   {name!r} ({kind}) - retired sync column")
            continue
        if not prune:
            print(
                f"unused   {name!r} - not touched; --prune deletes it when it is empty"
            )
        elif kind not in PRUNABLE:
            print(
                f"keep     {name!r} ({kind}) - emptiness cannot be checked; delete it in Notion"
            )
        elif is_empty_column(client, database_id, name, kind):
            patch[name] = None
            print(f"delete   {name!r} ({kind}) - empty in every row")
        else:
            print(
                f"keep     {name!r} ({kind}) - has data; delete it in Notion if you are sure"
            )
    if problems:
        return 2
    body = {
        "title": db.get("title") or rich("Nestle Tasks"),
        "description": rich(
            "Synced from docs/tasks by notion_sync.py. Read only: change tasks in the repo."
        ),
        "properties": patch,
    }
    client.call("PATCH", f"databases/{database_id}", body)
    verb = "would update" if client.dry_run else "updated"
    print(f"\n{verb} database schema ({len(patch)} column change(s))")
    return configure_views(client, database_id)


def configure_views(client: Client, database_id: str) -> int:
    """Put every table view of the database in SCHEMA order and hide the sync columns."""
    order = [*VIEW_ORDER, *(n for n in [TITLE_PROP, *SCHEMA] if n not in VIEW_ORDER)]
    columns = [
        {
            "property_id": "title" if name == TITLE_PROP else name,
            "visible": name not in HIDDEN_COLUMNS,
            "width": COLUMN_WIDTHS.get(name, 140),
        }
        for name in order
    ]
    refs = client.call("GET", f"views?database_id={database_id}", version=VIEWS_VERSION)
    for ref in refs.get("results", []):
        view = client.call("GET", f"views/{ref['id']}", version=VIEWS_VERSION)
        if view.get("type") != "table":
            print(
                f"view     {view.get('name')!r} ({view.get('type')}) - not a table, left as is"
            )
            continue
        client.call(
            "PATCH",
            f"views/{ref['id']}",
            {"configuration": {"type": "table", "properties": columns}},
            version=VIEWS_VERSION,
        )
        verb = "would order" if client.dry_run else "ordered"
        print(
            f"view     {view.get('name')!r} - {verb} {len(order)} columns, hid {', '.join(HIDDEN_COLUMNS)}"
        )
    return 0


def sync(client: Client, database_id: str, args: argparse.Namespace, root: Path) -> int:
    db = client.call("GET", f"databases/{database_id}")
    have = db.get("properties", {})
    wrong = [
        n
        for n in (TITLE_PROP, *SCHEMA)
        if n not in have or (n in SCHEMA and have[n]["type"] != next(iter(SCHEMA[n])))
    ]
    if wrong:
        print(
            f"database columns missing or of the wrong type: {wrong}; run with --setup first",
            file=sys.stderr,
        )
        return 2

    people = People(client)
    if not people.available:
        print(
            "WARN people columns stay empty: enable 'Read user information including email"
            " addresses' for the integration",
            file=sys.stderr,
        )

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    tasks = tk.load_tasks()
    by_name: dict[str, list[str]] = {}
    for rel in tk.repo_files(root):
        by_name.setdefault(Path(rel).name, []).append(rel)
    base = github_base(root)
    branch = os.environ.get("NOTION_SYNC_BRANCH", "main")

    existing: dict[str, dict] = {}
    blank = 0
    for page in client.paginate(
        "POST", f"databases/{database_id}/query", {"page_size": 100}
    ):
        task_id = plain(page["properties"].get(ID_PROP, {})).strip()
        if task_id:
            existing[task_id] = page
        else:
            blank += 1

    selected = args.only or list(tasks)
    if not args.no_pull:
        pulled = 0
        for task_id in selected:
            if (
                task_id in tasks
                and task_id in existing
                and tasks[task_id].status in tk.OPEN_STATUSES
            ):
                found = notion_questions(client, existing[task_id]["id"])
                changes = pull_questions(
                    tasks[task_id],
                    found,
                    people,
                    today.isoformat(),
                    write=not client.dry_run,
                )
                for change in changes:
                    print(f"pull    {task_id} {change}")
                pulled += len(changes)
        if pulled:
            verb = "would copy" if client.dry_run else "copied"
            print(
                f"{verb} {pulled} question change(s) from Notion into docs/tasks; commit them\n"
            )
            if not client.dry_run:
                tasks = tk.load_tasks()

    counts = {"create": 0, "update": 0, "props": 0, "skip": 0, "removed": 0}
    for task_id in selected:
        task = tasks.get(task_id)
        if task is None:
            print(f"unknown task id {task_id}", file=sys.stderr)
            return 2
        errors, _ = tk.lint_task(task, tasks, root, by_name)
        flags = sorted(
            {f.split(":")[0] for f in tk.flags_for(task, tasks, today, len(errors))}
        )
        rel = task.path.relative_to(root).as_posix()
        file_url = f"{base}/blob/{branch}/{rel}" if base else None
        props, unresolved = properties(task, flags, file_url, people)
        body = render_body(task, file_url)
        # Two halves: properties and page body. A status or people change rewrites only
        # the properties; the body (about 20 calls) is rewritten only when it changed.
        props_hash = hashlib.sha256(
            json.dumps(props, sort_keys=True).encode()
        ).hexdigest()[:8]
        body_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest()[:8]
        digest = f"{props_hash}{body_hash}"
        props["Hash"] = text_prop(digest)

        page = existing.get(task_id)
        if page is None:
            action = "create"
            client.call(
                "POST",
                "pages",
                {
                    "parent": {"database_id": database_id},
                    "properties": props,
                    "children": body[:CHILDREN_LIMIT],
                },
            )
        elif plain(page["properties"].get("Hash", {})) == digest and not args.force:
            action = "skip"
        else:
            old = plain(page["properties"].get("Hash", {}))
            body_changed = args.force or old[8:] != body_hash
            action = "update" if body_changed else "props"
            client.call("PATCH", f"pages/{page['id']}", {"properties": props})
        if action == "update":
            if not client.dry_run:
                for child in client.paginate(
                    "GET", f"blocks/{page['id']}/children?page_size=100"
                ):
                    client.call("DELETE", f"blocks/{child['id']}")
            client.call(
                "PATCH",
                f"blocks/{page['id']}/children",
                {"children": body[:CHILDREN_LIMIT]},
            )
        counts[action] += 1
        note = (
            f"  (not in Notion: {', '.join(unresolved)})"
            if unresolved and people.available
            else ""
        )
        print(f"{action:7} {task_id} [{task.status}] {' '.join(flags) or '-'}{note}")

    if not args.only:
        for task_id, page in existing.items():
            if task_id in tasks:
                continue
            current = [
                o["name"]
                for o in page["properties"].get("Flags", {}).get("multi_select", [])
            ]
            if args.archive_removed:
                client.call("PATCH", f"pages/{page['id']}", {"archived": True})
                counts["removed"] += 1
                print(f"removed {task_id} - no task file; page moved to Notion's Trash")
            elif "REMOVED" not in current:
                client.call(
                    "PATCH",
                    f"pages/{page['id']}",
                    {
                        "properties": {
                            "Flags": {
                                "multi_select": [
                                    {"name": n} for n in [*current, "REMOVED"]
                                ]
                            }
                        }
                    },
                )
                counts["removed"] += 1
                print(f"removed {task_id} - no task file; flagged REMOVED, page kept")

    summary_line = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
    mode = "dry run, nothing written" if client.dry_run else f"{client.writes} write(s)"
    print(f"\n{summary_line or 'nothing to do'} ({mode})")
    if blank:
        print(
            f"{blank} page(s) without an {ID_PROP} were ignored; delete them in Notion if they are empty rows"
        )
    return 0


TEMPLATE_GUIDE = (
    "How to use this template in another workspace:",
    "Duplicate this page into the workspace (from the published page: Duplicate).",
    "Fill the table by hand, or sync it from a repository: create an internal integration"
    " in that workspace (Settings > Connections > Develop or manage integrations), share"
    " the database with it (... > Connections), and set NOTION_TOKEN and NOTION_DATABASE_ID"
    " (the 32 characters before ?v= in the database link) in the repository's .env.",
    "Then run: python3 docs/tasks/notion_sync.py --setup, followed by"
    " python3 docs/tasks/notion_sync.py.",
)


def create_template(client: Client, parent_id: str, title: str) -> int:
    """Create a page holding an empty task database with the full schema and view."""
    page = client.call(
        "POST",
        "pages",
        {
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": rich(title)}},
            "children": [
                block(
                    "callout",
                    TEMPLATE_GUIDE[0],
                    icon={"type": "emoji", "emoji": "\U0001f4cb"},
                ),
                *[block("numbered_list_item", line) for line in TEMPLATE_GUIDE[1:]],
            ],
        },
    )
    db = client.call(
        "POST",
        "databases",
        {
            "parent": {"type": "page_id", "page_id": page.get("id", parent_id)},
            "is_inline": True,
            "title": rich("Tasks"),
            "description": rich(
                "Synced from docs/tasks by notion_sync.py. Read only: change tasks in the repo."
            ),
            "properties": {TITLE_PROP: {"title": {}}, **SCHEMA},
        },
    )
    if client.dry_run:
        print(
            f"would create page {title!r} with a Tasks database of {len(SCHEMA) + 1} columns"
        )
        return 0
    configure_views(client, db["id"].replace("-", ""))
    print(f"page      {page.get('url')}")
    print(f"database  {db['id'].replace('-', '')}  (NOTION_DATABASE_ID for this copy)")
    print(
        "Publish the page with 'Allow duplicate as template' to copy it to another workspace."
    )
    return 0


# Body of the "New" page template: the brief sections, each with a one-line hint.
BRIEF_SKELETON: tuple[tuple[str, str, str], ...] = (
    (
        "Goal",
        "paragraph",
        "One or two sentences: what is different once this task is done.",
    ),
    (
        "Context",
        "bulleted_list_item",
        "What exists today and where (file:line), and why it is not good enough.",
    ),
    (
        "Scope",
        "bulleted_list_item",
        "In scope: ...  Out of scope: the adjacent work this task must not touch.",
    ),
    (
        "Requirements",
        "bulleted_list_item",
        "R1: one verifiable change or behaviour per line.",
    ),
    (
        "Deliverables",
        "bulleted_list_item",
        "The files, tables or artifacts that change; a pull request.",
    ),
    (
        "Acceptance criteria",
        "to_do",
        "AC1: the command, query or check to run, and the expected result.",
    ),
    (
        "Risks and notes",
        "bulleted_list_item",
        "Ordering constraints, cost, what can go wrong.",
    ),
    ("References", "bulleted_list_item", "Links to code, docs and tickets."),
    (QUESTIONS_HEADING, "paragraph", QUESTIONS_HINT),
    (
        "Evidence",
        "bulleted_list_item",
        "PR: the GitHub link to the pull request, added by the assignee.",
    ),
    ("Review log", "paragraph", "Filled by the reviewer."),
)
TEMPLATE_DEFAULTS = {"Status": "Todo", "Priority": "P2"}


def fill_template(
    client: Client, database_id: str, name: str, project: str | None
) -> int:
    """Fill a database page template (created in the Notion app) with defaults and sections."""
    db = client.call("GET", f"databases/{database_id}", version=VIEWS_VERSION)
    sources = db.get("data_sources", [])
    if not sources:
        print(
            "the database has no data source; is the integration connected?",
            file=sys.stderr,
        )
        return 2
    templates = client.call(
        "GET", f"data_sources/{sources[0]['id']}/templates", version=VIEWS_VERSION
    ).get("templates", [])
    match = [x for x in templates if x.get("name", "").strip().lower() == name.lower()]
    if not match:
        names = ", ".join(repr(x.get("name")) for x in templates) or "none"
        print(
            f"no template named {name!r} (found: {names}). In Notion: New (arrow) > + New template,"
            f" name it {name!r}, then run this again.",
            file=sys.stderr,
        )
        return 2
    template_id = match[0]["id"]
    props: dict = {n: {"select": {"name": v}} for n, v in TEMPLATE_DEFAULTS.items()}
    if project:
        props["Project"] = {"select": {"name": project}}
    client.call("PATCH", f"pages/{template_id}", {"properties": props})
    if not client.dry_run:
        for child in client.paginate(
            "GET", f"blocks/{template_id}/children?page_size=100"
        ):
            client.call("DELETE", f"blocks/{child['id']}")
    children: list[dict] = []
    for heading, kind, hint in BRIEF_SKELETON:
        children.append(block("heading_2", heading))
        item = block(kind, hint, **({"checked": False} if kind == "to_do" else {}))
        item[kind]["rich_text"][0]["annotations"] = {"italic": True, "color": "gray"}
        children.append(item)
    client.call("PATCH", f"blocks/{template_id}/children", {"children": children})
    verb = "would fill" if client.dry_run else "filled"
    default = (
        " (default)" if match[0].get("is_default") else " - set it as default in Notion"
    )
    print(
        f"{verb} template {name!r}{default}: {len(BRIEF_SKELETON)} sections, {', '.join(props)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--setup", action="store_true", help="create, rename or convert the columns"
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="with --setup: delete unused columns that are empty in every row",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="read from Notion but write nothing"
    )
    parser.add_argument(
        "--force", action="store_true", help="rewrite pages even when unchanged"
    )
    parser.add_argument("--only", nargs="+", metavar="TASK-NNN")
    parser.add_argument(
        "--archive-removed",
        action="store_true",
        help="move pages whose task file is gone to Notion's Trash instead of flagging them",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="do not copy questions added or ticked in Notion into the task files",
    )
    parser.add_argument(
        "--create-template",
        metavar="PARENT_PAGE_ID",
        help="create a page with an empty task database (schema and view) under this page",
    )
    parser.add_argument(
        "--title", default="Task board (template)", help="with --create-template"
    )
    parser.add_argument(
        "--fill-template",
        metavar="NAME",
        help="fill the database page template NAME (made in the Notion app) with the brief sections",
    )
    parser.add_argument("--project", help="with --fill-template: default Project value")
    parser.add_argument("--today")
    args = parser.parse_args(argv)

    root = tk.repo_root()
    load_env(root)
    token = os.environ.get("NOTION_TOKEN", "")
    database_id = os.environ.get("NOTION_DATABASE_ID", "").replace("-", "")
    if token and args.create_template:
        try:
            return create_template(
                Client(token, args.dry_run),
                args.create_template.replace("-", ""),
                args.title,
            )
        except NotionError as e:
            print(f"Notion API error: {e}", file=sys.stderr)
            return 1
    if not token or not re.fullmatch(r"[0-9a-f]{32}", database_id):
        print(
            "set NOTION_TOKEN and NOTION_DATABASE_ID (32 hex characters) in the environment or .env",
            file=sys.stderr,
        )
        return 2

    client = Client(token, args.dry_run)
    try:
        if args.fill_template:
            return fill_template(client, database_id, args.fill_template, args.project)
        if args.setup:
            return setup(client, database_id, prune=args.prune)
        return sync(client, database_id, args, root)
    except NotionError as e:
        print(f"Notion API error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
