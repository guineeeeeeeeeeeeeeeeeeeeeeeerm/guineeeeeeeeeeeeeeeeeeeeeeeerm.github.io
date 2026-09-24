"""Input records and the domain objects built from them."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .patches import PatchState


TYPE_NAMES = {
    "short": "짧은 글",
    "medium": "중간 글",
    "long": "긴 글",
}

WRITTEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
ABOUT_FILE = "about.md"
# The records attached to posts, one table each: a JSONL file whose every line is one row (one event), appended to and
# never edited. What is current — the live links, the tags a post has now — is computed from the rows here.
TABLES = ("links.jsonl", "patches.jsonl", "shares.jsonl", "tags.jsonl")
RECORD_ID_RE = re.compile(r"[a-z0-9-]+")


class BuildError(Exception):
    """An input error that should be reported as one line."""


class Post:
    def __init__(self, source: Path, post_id: str, fields: dict[str, str], body: str):
        self.source = source
        self.post_id = post_id
        self.fields = fields
        self.body = body
        self.post_type = fields["type"]
        self.written = fields["written"]
        self.title = fields.get("title", "")


@dataclass(frozen=True)
class Patch:
    source: Path
    patch_id: str
    post_id: str
    at: str
    why: str
    op: str
    anchor: str
    text: str | None


class Link:
    def __init__(
        self,
        source: Path,
        link_id: str,
        from_id: str,
        anchor: str,
        to_id: str,
        events: list[dict[str, str]],
    ):
        self.source = source
        self.link_id = link_id
        self.from_id = from_id
        self.anchor = anchor
        self.to_id = to_id
        self.events = events

    @property
    def created_at(self) -> str:
        return self.events[0]["at"]

    @property
    def current_reason(self) -> str:
        reason = ""
        for event in self.events:
            if event["action"] in {"created", "reason-changed"}:
                reason = event["why"]
        return reason

    @property
    def active(self) -> bool:
        return self.events[-1]["action"] != "removed"


def source_name(path: Path) -> str:
    return path.as_posix()


def fail(path: Path) -> None:
    raise BuildError(source_name(path))


def require_string(value: object, path: Path) -> str:
    if not isinstance(value, str):
        fail(path)
    return value


def table_rows(content_root: Path, name: str) -> list[tuple[Path, dict]]:
    """(where, row) for every non-empty line of a table; `where` names the file and the line (`…/links.jsonl:3`) for errors."""
    path = content_root / name
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail(path)
    rows = []
    for number, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        where = Path(f"{path}:{number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            fail(where)
        if not isinstance(row, dict):
            fail(where)
        rows.append((where, row))
    return rows


def parse_written(value: str, path: Path) -> str:
    if not WRITTEN_RE.fullmatch(value):
        fail(path)
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        fail(path)
    return value


def parse_post(path: Path, content_root: Path) -> Post:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail(path)

    lines = text.splitlines()
    separator = next((index for index, line in enumerate(lines) if not line.strip()), None)
    if separator is None:
        fail(path)

    fields: dict[str, str] = {}
    for line in lines[:separator]:
        if ":" not in line:
            fail(path)
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key not in {"written", "type", "title"} or key in fields:
            fail(path)
        fields[key] = value

    if "written" not in fields or "type" not in fields:
        fail(path)
    parse_written(fields["written"], path)
    if fields["type"] not in TYPE_NAMES:
        fail(path)
    if fields["type"] == "short" and "title" in fields:
        fail(path)

    body = "\n".join(lines[separator + 1 :])
    if not body.strip():
        fail(path)

    post_id = path.stem
    if post_id != time_id(fields["written"]):
        fail(path)   # a post's id is the moment it was written: YYYYMMDD-HHMMSS, the same instant as `written`
    return Post(path, post_id, fields, body)


def time_id(written: str) -> str:
    """`2026-09-24T07:59:21Z` -> `20260924-075921`: the id a post written then carries."""
    return written[0:4] + written[5:7] + written[8:10] + "-" + written[11:13] + written[14:16] + written[17:19]


def post_files(content_root: Path) -> list[Path]:
    if not content_root.is_dir():
        return []
    result = []
    for path in content_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(content_root)
        if relative.parts and relative.parts[0] == "images":
            continue
        if relative.as_posix() in TABLES:
            continue   # the record tables are not posts
        if relative.as_posix() == ABOUT_FILE:
            continue
        result.append(path)
    return sorted(result, key=lambda path: path.relative_to(content_root).as_posix())


def parse_posts(content_root: Path) -> list[Post]:
    posts = []
    by_id: dict[str, Path] = {}
    for path in post_files(content_root):
        post = parse_post(path, content_root)
        if post.post_id in by_id:
            fail(path)
        by_id[post.post_id] = path
        posts.append(post)
    return posts


# Where a post can be shared: the name shown to a reader and a monochrome icon drawn here (nothing is fetched). Adding a
# place is adding a line here.
SHARE_PLACES = {
    "x": ("X", '<path d="M5 5l14 14M19 5L5 19" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'),
    "threads": ("Threads", '<path d="M16.5 11.5c-.4-3-2.2-4.3-4.6-4.3-2.8 0-4.7 2-4.7 5s1.9 5 4.7 5c2.3 0 4.2-1.3 4.2-3.4 0-1.8-1.4-2.9-3.6-2.9-1.9 0-3 .9-3 2.1 0 1.1.9 1.9 2.4 1.9 2.7 0 4.1-2.3 3.4-6.4M20 12a8 8 0 1 1-8-8c3.7 0 6.3 2 7.3 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
    "linkedin": ("LinkedIn", '<rect x="3" y="3" width="18" height="18" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                 '<path d="M8 10.5V17M8 7.2v.1M11.5 17v-6.5M11.5 13.2c0-1.6 1-2.7 2.3-2.7s2.2.9 2.2 2.6V17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
}


def share_icons_svg() -> str:
    symbols = "".join(
        f'<symbol id="share-{place}" viewBox="0 0 24 24">{icon}</symbol>'
        for place, (_, icon) in SHARE_PLACES.items()
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg">{symbols}</svg>\n'


@dataclass(frozen=True)
class Share:
    path: Path
    post_id: str
    where: str
    url: str
    at: str
    line: int


def parse_shares(content_root: Path, posts: list[Post]) -> dict[str, list[Share]]:
    """The share table -> post id -> its shares, in the order they were shared (then by line)."""
    posts_by_id = {post.post_id: post for post in posts}
    shares = []
    for line, (where, data) in enumerate(table_rows(content_root, "shares.jsonl")):
        if set(data) != {"post", "where", "url", "at"}:
            fail(where)
        post_id, place, url, at = (require_string(data[key], where) for key in ("post", "where", "url", "at"))
        if post_id not in posts_by_id or place not in SHARE_PLACES or not re.fullmatch(r"https://\S+", url):
            fail(where)
        parse_written(at, where)
        shares.append(Share(where, post_id, place, url, at, line))
    out: dict[str, list[Share]] = {}
    for item in sorted(shares, key=lambda item: (item.at, item.line)):
        out.setdefault(item.post_id, []).append(item)
    return out


@dataclass(frozen=True)
class Tagging:
    """A tag a post has now: when it was (last) added and why."""

    tag: str
    at: str
    why: str


def valid_tag(tag: str) -> bool:
    return (0 < len(tag) <= 40 and tag == tag.strip() and tag not in {".", ".."}
            and not any(ch in tag for ch in "/\\\n\r"))


def parse_tags(content_root: Path, posts: list[Post]) -> dict[str, list[Tagging]]:
    """The tag table -> post id -> the tags it has now (by name). A post-tag pair's events alternate added/removed from
    `added`; its last event decides."""
    posts_by_id = {post.post_id: post for post in posts}
    last: dict[tuple[str, str], tuple[str, str, str]] = {}
    for where, data in table_rows(content_root, "tags.jsonl"):
        if set(data) != {"post", "tag", "action", "at", "why"}:
            fail(where)
        post_id, tag, action, at, why = (require_string(data[key], where) for key in ("post", "tag", "action", "at", "why"))
        if post_id not in posts_by_id or not valid_tag(tag) or action not in {"added", "removed"}:
            fail(where)
        parse_written(at, where)
        previous = last.get((post_id, tag))
        if (previous is None and action != "added") or (previous and (previous[0] == action or at < previous[1])):
            fail(where)
        last[(post_id, tag)] = (action, at, why)
    out: dict[str, list[Tagging]] = {}
    for (post_id, tag), (action, at, why) in sorted(last.items()):
        if action == "added":
            out.setdefault(post_id, []).append(Tagging(tag, at, why))
    return out


def parse_patches(content_root: Path, posts: list[Post]) -> list[Patch]:
    """The patch table: one row, one patch."""
    posts_by_id = {post.post_id: post for post in posts}
    patches: list[Patch] = []
    seen: set[str] = set()
    for where, data in table_rows(content_root, "patches.jsonl"):
        common = {"id", "post", "at", "why", "op", "anchor"}
        if not common.issubset(data):
            fail(where)
        op = require_string(data["op"], where)
        if op not in {"replace", "insert-before", "insert-after", "delete"}:
            fail(where)
        if set(data) != (common if op == "delete" else common | {"text"}):
            fail(where)
        patch_id, post_id, at, why, anchor = (require_string(data[key], where) for key in ("id", "post", "at", "why", "anchor"))
        if not RECORD_ID_RE.fullmatch(patch_id) or patch_id in seen or post_id not in posts_by_id:
            fail(where)
        seen.add(patch_id)
        parse_written(at, where)
        text = None if op == "delete" else require_string(data["text"], where)
        patches.append(Patch(where, patch_id, post_id, at, why, op, anchor, text))
    return patches


def parse_links(
    content_root: Path, posts: list[Post], patch_states: dict[str, PatchState]
) -> list[Link]:
    """The link table: a link is created by one row (from, to, anchor) and changed by later rows of the same `link`."""
    posts_by_id = {post.post_id: post for post in posts}
    by_id: dict[str, Link] = {}
    for where, row in table_rows(content_root, "links.jsonl"):
        action = row.get("action")
        if not isinstance(action, str):
            fail(where)
        if action == "created":
            if set(row) != {"link", "from", "to", "anchor", "action", "at", "why"}:
                fail(where)
            link_id, from_id, to_id, anchor = (require_string(row[key], where) for key in ("link", "from", "to", "anchor"))
            if not RECORD_ID_RE.fullmatch(link_id) or link_id in by_id or not anchor:
                fail(where)
            if from_id not in posts_by_id or to_id not in posts_by_id:
                fail(where)
            by_id[link_id] = Link(where, link_id, from_id, anchor, to_id, [])
        elif action in {"reason-changed", "removed"}:
            if set(row) != {"link", "action", "at", "why"}:
                fail(where)
            link_id = require_string(row["link"], where)
            if link_id not in by_id:
                fail(where)   # a link's first event is its creation
        else:
            fail(where)
        at = parse_written(require_string(row["at"], where), where)
        why = require_string(row["why"], where)
        link = by_id[link_id]
        if link.events and at < link.events[-1]["at"]:
            fail(where)
        link.events.append({"at": at, "action": action, "why": why})
    links = list(by_id.values())
    for link in links:
        source_body = patch_states[link.from_id].body
        positions = []
        start = 0
        while True:
            position = source_body.find(link.anchor, start)
            if position < 0:
                break
            positions.append(position)
            start = position + 1
        if len(positions) != 1:
            fail(link.source)
    return links


def utc_label(written: str) -> str:
    return written[:16].replace("T", " ") + " UTC"


def time_element(written: str) -> str:
    label = utc_label(written)
    return f'<time datetime="{written}" title="{label}">{label}</time>'
