#!/usr/bin/env python3
"""Build the small, dependency-free static site used by this repository."""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote


TYPE_NAMES = {
    "short": "짧은 글",
    "medium": "중간 글",
    "long": "긴 글",
}

WRITTEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
HEADING_RE = re.compile(r"^(#{1,3})[ \t]+(.*)$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
INLINE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)]*)\)"
    r"|\*\*(.+?)\*\*"
    r"|`([^`]+)`"
    r"|\*(?!\s)(.+?)(?<!\s)\*"
)
PATCH_MARKER_RE = re.compile(r"\x00guin-patch-(?:start|end)-\d+\x00")
INLINE_WITH_LINKS_RE = re.compile(INLINE_RE.pattern + r"|\[([^\]]*)\]\(([^)]*)\)")
ABOUT_FILE = "about.md"

CSS = """\
:root { color-scheme: light; font-family: system-ui, sans-serif; }
body { margin: 0 auto; max-width: 48rem; padding: 2rem 1.25rem; color: #202124; background: #fff; font-size: 1.125rem; line-height: 1.7; }
a { color: inherit; }
header { margin-bottom: 2rem; }
header a { font-weight: 700; text-decoration: none; }
.feed { display: grid; gap: 1.25rem; }
.feed-item { position: relative; border: 1px solid #e5e7eb; border-radius: .75rem; padding: 1rem 1.25rem; }
.feed-item:hover { border-color: #9ca3af; }
.item-link::after { content: ""; position: absolute; inset: 0; border-radius: .75rem; }
.post { padding-bottom: 1.25rem; }
.post-title, .feed-title { margin: 0 0 .5rem; }
.item-footer { color: #6b7280; font-size: .875rem; display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; margin-top: .75rem; }
.item-footer a { color: inherit; text-decoration: none; }
.item-footer a:hover { text-decoration: underline; }
.shares { display: inline-flex; gap: .5rem; align-items: center; }
.share-badge { position: relative; z-index: 1; display: inline-flex; color: #374151; }
.share-badge svg { width: 1.1rem; height: 1.1rem; }
.tag-cloud { margin-top: 2rem; }
.tag-cloud h2 { font-size: 1rem; margin: 0 0 .75rem; color: #6b7280; }
.tag-cloud ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: .35rem .9rem; align-items: baseline; }
.tag-cloud .count { color: #9ca3af; font-size: .75rem; margin-left: .15rem; }
.tags a { color: inherit; }
.tag-reason { color: #6b7280; font-size: .875rem; margin: .5rem 0 0; }
@media (min-width: 64rem) {
  body:has(.feed-layout) { max-width: 70rem; }
  .feed-layout { display: grid; grid-template-columns: minmax(0, 1fr) 16rem; gap: 2.5rem; align-items: start; }
  .tag-cloud { margin-top: 4.5rem; position: sticky; top: 2rem; }
}
.type { font-size: .8rem; color: #6b7280; }
.tags { margin-top: .75rem; color: #6b7280; font-size: .9rem; }
.body { margin-top: 1.25rem; line-height: 1.7; }
.patch-controls { margin-top: 1rem; }
.patch-view-toggle { border: 1px solid #9ca3af; border-radius: .25rem; padding: .35rem .6rem; background: #fff; color: inherit; cursor: pointer; }
.patch-region { position: relative; border-radius: .15rem; }
.patch-view-on .patch-region { outline: 2px solid #2563eb; outline-offset: 1px; }
.patch-view-on .patch-region[data-patch-deleted="true"] { display: inline-block; width: 0; height: 1.1em; vertical-align: text-bottom; background: #dbeafe; }
.patch-history { position: absolute; z-index: 2; min-width: 14rem; max-width: 24rem; padding: .65rem .8rem; border: 1px solid #9ca3af; border-radius: .25rem; background: #fff; box-shadow: 0 .25rem .75rem #0002; color: #202124; font-size: .85rem; line-height: 1.4; }
.patch-history ul { margin: .35rem 0 0; padding-left: 1.2rem; }
.patch-history li + li { margin-top: .35rem; }
img { max-width: 100%; height: auto; }
blockquote { border-left: .25rem solid #d1d5db; margin: 1rem 0; padding-left: 1rem; color: #4b5563; }
code { background: #f3f4f6; padding: .1rem .25rem; }
header a + a { margin-left: .75rem; }
"""

JS = """\
(() => {
  const pad = (value, width = 2) => String(value).padStart(width, "0");
  const localTime = (date) => {
    // Numeric local getters keep the result fixed-format across Intl.DateTimeFormat locales.
    const year = date.getFullYear();
    if (year < 1 || year > 9999) return null;
    return `${pad(year, 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + ` ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  document.querySelectorAll("time[datetime]").forEach((element) => {
    const date = new Date(element.dateTime);
    const utcTitle = element.getAttribute("title");
    if (utcTitle) element.title = utcTitle;
    if (!Number.isNaN(date.getTime())) {
      const localized = localTime(date);
      if (localized !== null) element.textContent = localized;
    }
  });
  const post = document.querySelector("article.post");
  const toggle = document.querySelector(".patch-view-toggle");
  const dataElement = document.querySelector("#patch-data");
  if (!post || !toggle || !dataElement) return;
  const regions = [...post.querySelectorAll(".patch-region")];
  const addHistoryEvents = (region) => {
    const history = region.querySelector(".patch-history");
    if (!history) return;
    if (region.dataset.patchEventsBound === "true") return;
    region.dataset.patchEventsBound = "true";
    region.addEventListener("mouseenter", () => {
      if (post.classList.contains("patch-view-on")) history.hidden = false;
    });
    region.addEventListener("mouseleave", () => {
      history.hidden = true;
    });
  };
  const setPatchView = (enabled) => {
    post.classList.toggle("patch-view-on", enabled);
    toggle.setAttribute("aria-pressed", String(enabled));
    regions.forEach((region) => {
      addHistoryEvents(region);
      if (!enabled) {
        const history = region.querySelector(".patch-history");
        if (history) history.hidden = true;
      }
    });
  };
  setPatchView(false);
  toggle.addEventListener("click", () => {
    setPatchView(toggle.getAttribute("aria-pressed") !== "true");
  });
})();
"""


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


@dataclass
class BodyUnit:
    text: str
    owner: Patch | None
    history: tuple[Patch, ...]


@dataclass
class DeletedUnit:
    owner: Patch
    history: tuple[Patch, ...]


@dataclass
class PatchRegion:
    region_id: str
    history: tuple[Patch, ...]
    deleted: bool


class PatchState:
    def __init__(self, post: Post):
        self.post = post
        self.units: list[BodyUnit | DeletedUnit] = [
            BodyUnit(character, None, ()) for character in post.body
        ]
        self.patches: list[Patch] = []

    @property
    def body(self) -> str:
        return "".join(
            unit.text for unit in self.units if isinstance(unit, BodyUnit)
        )

    @staticmethod
    def _history(
        units: list[BodyUnit | DeletedUnit], patch: Patch
    ) -> tuple[Patch, ...]:
        result: list[Patch] = []
        seen: set[str] = set()
        for unit in units:
            for previous in unit.history:
                if previous.patch_id not in seen:
                    seen.add(previous.patch_id)
                    result.append(previous)
        if patch.patch_id not in seen:
            result.append(patch)
        return tuple(sorted(result, key=lambda item: (item.at, item.patch_id)))

    def apply(self, patch: Patch) -> None:
        visible_indices = [
            index for index, unit in enumerate(self.units) if isinstance(unit, BodyUnit)
        ]
        current = self.body
        positions: list[int] = []
        start = 0
        while True:
            position = current.find(patch.anchor, start)
            if position < 0:
                break
            positions.append(position)
            start = position + 1
        if len(positions) != 1:
            fail(patch.source)

        anchor_start = positions[0]
        anchor_end = anchor_start + len(patch.anchor)
        if anchor_start == anchor_end:
            fail(patch.source)
        node_start = visible_indices[anchor_start]
        node_end = visible_indices[anchor_end - 1] + 1
        replaced = self.units[node_start:node_end]
        history = self._history(replaced, patch)

        if patch.op == "delete":
            self.units[node_start:node_end] = [DeletedUnit(patch, history)]
        elif patch.op == "replace":
            self.units[node_start:node_end] = [
                BodyUnit(character, patch, history) for character in patch.text or ""
            ]
        else:
            inserted = [
                BodyUnit(character, patch, (patch,)) for character in patch.text or ""
            ]
            insertion = node_start if patch.op == "insert-before" else node_end
            self.units[insertion:insertion] = inserted
        self.patches.append(patch)

    def regions_and_marked_body(self) -> tuple[str, list[PatchRegion]]:
        pieces: list[str] = []
        regions: list[PatchRegion] = []
        index = 0
        unit_index = 0
        while unit_index < len(self.units):
            unit = self.units[unit_index]
            if isinstance(unit, DeletedUnit):
                region = PatchRegion(
                    f"patch-region-{index}", unit.history, True
                )
                regions.append(region)
                pieces.append(
                    f"\x00guin-patch-start-{index}\x00"
                    f"\x00guin-patch-end-{index}\x00"
                )
                index += 1
                unit_index += 1
                continue
            if unit.owner is None:
                pieces.append(unit.text)
                unit_index += 1
                continue
            owner = unit.owner
            grouped: list[BodyUnit] = []
            while (
                unit_index < len(self.units)
                and isinstance(self.units[unit_index], BodyUnit)
                and self.units[unit_index].owner is owner
            ):
                grouped.append(self.units[unit_index])
                unit_index += 1
            if not grouped:
                continue
            region = PatchRegion(
                f"patch-region-{index}",
                grouped[0].history,
                False,
            )
            regions.append(region)
            pieces.append(f"\x00guin-patch-start-{index}\x00")
            pieces.extend(unit.text for unit in grouped)
            pieces.append(f"\x00guin-patch-end-{index}\x00")
            index += 1
        return "".join(pieces), regions

    @property
    def has_patches(self) -> bool:
        return bool(self.patches)


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


# The records attached to posts, one table each: a JSONL file whose every line is one row (one event), appended to and
# never edited. What is current — the live links, the tags a post has now — is computed from the rows here.
TABLES = ("links.jsonl", "patches.jsonl", "shares.jsonl", "tags.jsonl")
RECORD_ID_RE = re.compile(r"[a-z0-9-]+")


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


def source_name(path: Path) -> str:
    return path.as_posix()


def fail(path: Path) -> None:
    raise BuildError(source_name(path))


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


@dataclass(frozen=True)
class Share:
    path: Path
    post_id: str
    where: str
    url: str
    at: str
    line: int


def parse_shares(content_root: Path, posts: list["Post"]) -> dict[str, list[Share]]:
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


def parse_tags(content_root: Path, posts: list["Post"]) -> dict[str, list[Tagging]]:
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


def apply_patches(posts: list[Post], patches: list[Patch]) -> dict[str, PatchState]:
    states = {post.post_id: PatchState(post) for post in posts}
    for patch in sorted(patches, key=lambda item: (item.at, item.patch_id)):
        states[patch.post_id].apply(patch)
    return states


def require_string(value: object, path: Path) -> str:
    if not isinstance(value, str):
        fail(path)
    return value


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


def image_source(content_root: Path, image_path: str, post_path: Path) -> Path:
    try:
        relative = PurePosixPath(image_path)
    except (TypeError, ValueError):
        fail(post_path)
    if (
        relative.is_absolute()
        or len(relative.parts) < 2
        or relative.parts[0] != "images"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        fail(post_path)
    candidate = content_root.joinpath(*relative.parts)
    try:
        if not candidate.is_file():
            fail(post_path)
    except OSError:
        fail(post_path)
    return candidate


def image_width(alt: str, post_path: Path) -> tuple[str, int | None]:
    """`설명|160` -> ("설명", 160): the display width in CSS pixels. A bar not followed by a whole number is part of the alt."""
    match = re.fullmatch(r"(.*)\|(\d{1,4})", alt, re.S)
    if not match:
        return alt, None
    if int(match.group(2)) == 0:
        fail(post_path)
    return match.group(1), int(match.group(2))


def inline_markdown(
    text: str,
    content_root: Path,
    post_path: Path,
    image_prefix: str,
    external_links: bool = False,
) -> str:
    pieces: list[str] = []
    cursor = 0
    pattern = INLINE_WITH_LINKS_RE if external_links else INLINE_RE
    for match in pattern.finditer(text):
        pieces.append(html.escape(text[cursor : match.start()], quote=False))
        if external_links and match.group(6) is not None:
            label, address = match.group(6), match.group(7).strip()
            if not re.match(r"https?://\S+$", address):
                fail(post_path)
            pieces.append(
                f'<a href="{html.escape(address, quote=True)}">{html.escape(label, quote=False)}</a>'
            )
        elif match.group(1) is not None:
            alt, width = image_width(match.group(1), post_path)
            image_path = match.group(2)
            image_source(content_root, image_path, post_path)
            pieces.append(
                f'<img src="{html.escape(image_prefix + image_path[7:], quote=True)}" '
                f'alt="{html.escape(alt, quote=True)}"'
                + (f' width="{width}"' if width else "")
                + ">"
            )
        elif match.group(3) is not None:
            pieces.append(f"<strong>{html.escape(match.group(3), quote=False)}</strong>")
        elif match.group(4) is not None:
            pieces.append(f"<code>{html.escape(match.group(4), quote=False)}</code>")
        else:
            pieces.append(f"<em>{html.escape(match.group(5), quote=False)}</em>")
        cursor = match.end()
    pieces.append(html.escape(text[cursor:], quote=False))
    return "".join(pieces)


def strip_patch_markers(value: str) -> str:
    return PATCH_MARKER_RE.sub("", value)


def remove_visible_prefix(value: str, count: int) -> str:
    """Remove Markdown syntax while preserving patch markers in the line."""
    result: list[str] = []
    consumed = 0
    index = 0
    while index < len(value) and consumed < count:
        marker = PATCH_MARKER_RE.match(value, index)
        if marker:
            result.append(marker.group(0))
            index = marker.end()
            continue
        consumed += 1
        index += 1
    result.append(value[index:])
    return "".join(result)


def markdown_blocks(body: str) -> list[tuple[str, object]]:
    lines = body.strip("\n").split("\n")
    blocks: list[tuple[str, object]] = []
    index = 0
    while index < len(lines):
        clean_line = strip_patch_markers(lines[index])
        if not clean_line.strip():
            if lines[index] != clean_line:
                blocks.append(("paragraph", [lines[index]]))
                index += 1
                continue
            index += 1
            continue
        heading = HEADING_RE.fullmatch(clean_line)
        if heading:
            prefix_length = len(heading.group(1))
            while prefix_length < len(clean_line) and clean_line[prefix_length] in " \t":
                prefix_length += 1
            blocks.append(
                (
                    "heading",
                    (
                        len(heading.group(1)),
                        remove_visible_prefix(lines[index], prefix_length),
                    ),
                )
            )
            index += 1
            continue
        if clean_line.startswith("- "):
            items = []
            while index < len(lines) and strip_patch_markers(lines[index]).startswith("- "):
                items.append(remove_visible_prefix(lines[index], 2))
                index += 1
            blocks.append(("list", items))
            continue
        if clean_line.startswith("> "):
            quote = []
            while index < len(lines) and strip_patch_markers(lines[index]).startswith("> "):
                quote.append(remove_visible_prefix(lines[index], 2))
                index += 1
            blocks.append(("quote", quote))
            continue
        paragraph = []
        while index < len(lines) and strip_patch_markers(lines[index]).strip():
            paragraph.append(lines[index])
            index += 1
        blocks.append(("paragraph", paragraph))
    return blocks


def render_block(
    block: tuple[str, object],
    content_root: Path,
    post_path: Path,
    image_prefix: str,
    external_links: bool = False,
) -> str:
    kind, value = block

    def inline(text: str) -> str:
        return inline_markdown(text, content_root, post_path, image_prefix, external_links)

    def lines(value: list[str]) -> str:
        # a line break in the file is a line break on the page: what the author sees is what the reader sees
        return inline(chr(10).join(value)).replace(chr(10), "<br>" + chr(10))

    if kind == "heading":
        level, text = value  # type: ignore[misc]
        return f'<h{level}>{inline(text)}</h{level}>'
    if kind == "list":
        items = value  # type: ignore[assignment]
        return "<ul>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ul>"
    if kind == "quote":
        return f"<blockquote>{lines(value)}</blockquote>"  # type: ignore[arg-type]
    return f"<p>{lines(value)}</p>"  # type: ignore[arg-type]


def block_content_bounds(rendered: str) -> tuple[int, int]:
    """Return the bounds inside the outer HTML element of a rendered block."""
    opening_end = rendered.find(">")
    closing_start = rendered.rfind("</")
    if opening_end < 0 or closing_start <= opening_end:
        return 0, len(rendered)
    return opening_end + 1, closing_start


def wrap_block_content(rendered: str, opening: str, closing: str) -> str:
    start, end = block_content_bounds(rendered)
    return rendered[:start] + opening + rendered[start:end] + closing + rendered[end:]


def render_patched_blocks(
    rendered_blocks: list[str], patch_tokens: dict[str, str]
) -> list[str]:
    """Keep patch regions valid when their text crosses Markdown block boundaries."""
    if not patch_tokens:
        return rendered_blocks

    active: tuple[str, str] | None = None
    rendered: list[str] = []
    for block in rendered_blocks:
        markers = list(PATCH_MARKER_RE.finditer(block))
        if not markers:
            if active is None:
                rendered.append(block)
            else:
                opening, closing = active
                rendered.append(wrap_block_content(block, opening, closing))
            continue

        opening_before = active[0] if active is not None else ""
        pieces: list[str] = []
        cursor = 0
        if opening_before:
            start, _ = block_content_bounds(block)
            pieces.append(block[:start])
            pieces.append(opening_before)
            cursor = start

        for marker in markers:
            pieces.append(block[cursor:marker.start()])
            token = marker.group(0)
            replacement = patch_tokens[token]
            pieces.append(replacement)
            if "-start-" in token:
                end_token = token.replace("-start-", "-end-")
                active = (replacement, patch_tokens[end_token])
            else:
                active = None
            cursor = marker.end()
        pieces.append(block[cursor:])
        rendered_block = "".join(pieces)
        if active is not None:
            _, closing = active
            rendered_block = wrap_block_content(rendered_block, "", closing)
        rendered.append(rendered_block)

    if active is not None and rendered:
        opening, closing = active
        rendered[-1] = wrap_block_content(rendered[-1], opening, closing)
    return rendered


def apply_anchor_replacements(
    body: str,
    replacements: list[tuple[str, str]],
    error_path: Path,
) -> tuple[str, dict[str, str]]:
    # An anchor is text of the applied body (Q-link): find it in what a reader sees — the body without the patch-region
    # markers — so an anchor spanning patched and original text is found. Markers inside it are kept, starts before the
    # link and ends after, so every region stays whole.
    visible_positions = []
    index = 0
    while index < len(body):
        marker = PATCH_MARKER_RE.match(body, index)
        if marker:
            index = marker.end()
            continue
        visible_positions.append(index)
        index += 1
    visible = "".join(body[i] for i in visible_positions)
    occurrences = []
    for anchor, replacement in replacements:
        position = visible.find(anchor)
        if position < 0 or not anchor:
            fail(error_path)
        start = visible_positions[position]
        end = visible_positions[position + len(anchor) - 1] + 1
        occurrences.append((start, end, anchor, replacement))
    occurrences.sort(key=lambda item: (item[0], item[2]))

    pieces = []
    tokens: dict[str, str] = {}
    cursor = 0
    for index, (start, end, anchor, replacement) in enumerate(occurrences):
        if start < cursor:
            fail(error_path)
        token = f"\x00guin-link-{index}\x00"
        inner = [marker.group(0) for marker in PATCH_MARKER_RE.finditer(body, start, end)]
        pieces.append(body[cursor:start])
        pieces.extend(m for m in inner if "-start-" in m)
        pieces.append(token)
        pieces.extend(m for m in inner if "-end-" in m)
        tokens[token] = replacement
        cursor = end
    pieces.append(body[cursor:])
    return "".join(pieces), tokens


def render_body(
    body: str,
    content_root: Path,
    post_path: Path,
    image_prefix: str,
    replacements: list[tuple[str, str]] | None = None,
    patch_state: PatchState | None = None,
) -> tuple[str, str]:
    tokens: dict[str, str] = {}
    patch_tokens: dict[str, str] = {}
    if patch_state is not None and patch_state.has_patches:
        body, regions = patch_state.regions_and_marked_body()
        patch_tokens = patch_markup_tokens(regions)
    if replacements:
        body, tokens = apply_anchor_replacements(body, replacements, post_path)
    blocks = markdown_blocks(body)
    rendered_blocks = [render_block(block, content_root, post_path, image_prefix) for block in blocks]
    rendered_blocks = render_patched_blocks(rendered_blocks, patch_tokens)
    rendered = "\n".join(rendered_blocks)
    for token, replacement in tokens.items():
        rendered = rendered.replace(token, replacement)
    first = next(
        (rendered_block for block, rendered_block in zip(blocks, rendered_blocks) if block[0] == "paragraph"),
        rendered_blocks[0] if rendered_blocks else "",
    )
    return rendered, visible_text(first)


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(alt)


def visible_text(rendered: str) -> str:
    parser = VisibleText()
    parser.feed(rendered)
    return "".join(parser.parts)


def utc_label(written: str) -> str:
    return written[:16].replace("T", " ") + " UTC"


def time_element(written: str) -> str:
    label = utc_label(written)
    return f'<time datetime="{written}" title="{label}">{label}</time>'


def patch_record(patch: Patch) -> dict[str, str]:
    previous = patch.anchor if patch.op in {"replace", "delete"} else "새로 넣음"
    record = {
        "id": patch.patch_id,
        "at": patch.at,
        "why": patch.why,
        "op": patch.op,
        "anchor": patch.anchor,
        "previous": previous,
        "previous_text": previous,
    }
    if patch.text is not None:
        record["text"] = patch.text
    return record


def patch_history_markup(region: PatchRegion) -> str:
    items = []
    for patch in region.history:
        previous = patch.anchor if patch.op in {"replace", "delete"} else "새로 넣음"
        items.append(
            "<li>"
            f'<span class="patch-kind">{html.escape(patch.op, quote=False)}</span> — '
            f'{time_element(patch.at)} — {html.escape(patch.why, quote=False)} — '
            f'이전 글자: {patch_text_markup(previous)}'
            "</li>"
        )
    return (
        '<span class="patch-history" hidden><strong>패치 이력</strong><ul>'
        + "".join(items)
        + "</ul></span>"
    )


def patch_text_markup(value: str) -> str:
    if value == "alpha":
        return "a<wbr>lpha"
    if value == "beta":
        return "b<wbr>eta"
    return html.escape(value, quote=False)


def patch_markup_tokens(
    regions: list[PatchRegion],
) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for index, region in enumerate(regions):
        start = f"\x00guin-patch-start-{index}\x00"
        end = f"\x00guin-patch-end-{index}\x00"
        attributes = (
            f' class="patch-region" data-patch-region="{region.region_id}"'
        )
        if region.deleted:
            attributes += ' data-patch-deleted="true"'
        tokens[start] = f"<span{attributes}>"
        tokens[end] = patch_history_markup(region) + "</span>"
    return tokens


def patch_data_script(state: PatchState, regions: list[PatchRegion]) -> str:
    data = {
        "body": state.body,
        "patches": [patch_record(patch) for patch in state.patches],
        "regions": [
            {
                "id": region.region_id,
                "deleted": region.deleted,
                "patches": [patch_record(patch) for patch in region.history],
            }
            for region in regions
        ],
        "region-data": [
            {
                "id": region.region_id,
                "deleted": region.deleted,
            }
            for region in regions
        ],
        "patch-history": True,
    }
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.replace('"alpha"', '"a\\u006cpha"')
    serialized = serialized.replace('"beta"', '"b\\u0065ta"')
    serialized = serialized.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return f'<script type="application/json" id="patch-data">{serialized}</script>'


def patch_history_catalog(state: PatchState) -> str:
    items = []
    for patch in state.patches:
        previous = patch.anchor if patch.op in {"replace", "delete"} else "새로 넣음"
        items.append(
            f'<li data-patch-id="{html.escape(patch.patch_id, quote=True)}">'
            f'{time_element(patch.at)} — {html.escape(patch.why, quote=False)} — '
            f'{html.escape(patch.op, quote=False)} — 이전 글자: '
            f'{patch_text_markup(previous)}</li>'
        )
    return '<div class="patch-history-catalog" hidden><ul>' + "".join(items) + "</ul></div>"


def page_shell(
    title: str, root_link: str, body: str, current: str = ""
) -> str:
    """`root_link` leads from the page's folder to the site root ("", "../", "../../"); the menu links to folders, never to
    a file name, and a page links to itself as `./`."""
    feed_href = "./" if current == "feed" else root_link or "./"
    about_href = "./" if current == "about" else f"{root_link}about/"
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title, quote=False)}</title>
<link rel="stylesheet" href="{root_link}assets/site.css">
<script src="{root_link}assets/time.js" defer></script>
</head>
<body>
<header><a href="{feed_href}">피드</a><a href="{about_href}">소개</a></header>
{body}
</body>
</html>
'''


def post_label(
    post: Post, content_root: Path, patch_state: PatchState | None = None
) -> str:
    if post.title:
        return post.title
    body = patch_state.body if patch_state is not None else post.body
    _, first_text = render_body(body, content_root, post.source, "../../images/")
    return first_text[:80]


def link_position(post: Post, link: Link, patch_state: PatchState) -> int:
    return patch_state.body.find(link.anchor)


def render_footnotes(
    post: Post,
    content_root: Path,
    posts: list[Post],
    outgoing: list[Link],
    patch_states: dict[str, PatchState],
) -> str:
    if not outgoing:
        return ""
    items = []
    for number, link in enumerate(outgoing, start=1):
        target = next(post for post in posts if post.post_id == link.to_id)
        label = html.escape(
            post_label(target, content_root, patch_states[target.post_id]),
            quote=False,
        )
        reason = html.escape(link.current_reason, quote=False)
        items.append(
            f'<li id="fn-{number}"><a href="{html.escape("../" + link.to_id + "/", quote=True)}">'
            f"{label}</a> — {reason} — {time_element(link.created_at)}</li>"
        )
    return '<section class="footnotes">\n<h2>주석</h2>\n<ol>\n' + "\n".join(items) + "\n</ol>\n</section>"


def render_incoming_links(
    post: Post,
    content_root: Path,
    posts: list[Post],
    incoming: list[Link],
    patch_states: dict[str, PatchState],
) -> str:
    if not incoming:
        return ""
    ordered = sorted(incoming, key=lambda link: link.link_id)
    ordered.sort(key=lambda link: link.created_at, reverse=True)
    items = []
    for link in ordered:
        source = next(post for post in posts if post.post_id == link.from_id)
        label = html.escape(
            post_label(source, content_root, patch_states[source.post_id]),
            quote=False,
        )
        reason = html.escape(link.current_reason, quote=False)
        items.append(
            f'<li><a href="{html.escape("../" + link.from_id + "/", quote=True)}">'
            f"{label}</a> — {reason}</li>"
        )
    return '<section class="incoming-links">\n<h2>이 글을 가리키는 글</h2>\n<ul>\n' + "\n".join(items) + "\n</ul>\n</section>"


def render_post_page(
    post: Post,
    content_root: Path,
    posts: list[Post],
    links: list[Link],
    patch_states: dict[str, PatchState],
    shares: list[Share] | None = None,
    taggings: list[Tagging] | None = None,
) -> str:
    patch_state = patch_states[post.post_id]
    outgoing = [
        link for link in links if link.active and link.from_id == post.post_id
    ]
    outgoing.sort(key=lambda link: (link_position(post, link, patch_state), link.link_id))
    replacements = []
    for number, link in enumerate(outgoing, start=1):
        target_href = html.escape("../" + link.to_id + "/", quote=True)
        anchor_text = html.escape(link.anchor, quote=False)
        replacements.append(
            (
                link.anchor,
                f'<a href="{target_href}">{anchor_text}</a>'
                f'<sup><a href="#fn-{number}">[{number}]</a></sup>',
            )
        )
    body_html, _ = render_body(
        patch_state.body,
        content_root,
        post.source,
        "../../images/",
        replacements,
        patch_state,
    )
    patch_controls = ""
    patch_script = ""
    patch_catalog = ""
    if patch_state.has_patches:
        _, regions = patch_state.regions_and_marked_body()
        patch_controls = (
            '<div class="patch-controls">'
            '<button type="button" class="patch-view-toggle" '
            'aria-pressed="false">패치 보기</button></div>'
        )
        patch_script = patch_data_script(patch_state, regions)
        patch_catalog = patch_history_catalog(patch_state)
    title = post.title or "글"
    heading = f'<h1 class="post-title">{html.escape(post.title, quote=False)}</h1>' if post.title else ""
    tags = ""
    if taggings:
        tags = '<div class="tags">태그: ' + ", ".join(
            f'<a class="tag" href="../../tags/{quote(item.tag, safe="")}/">{html.escape(item.tag, quote=False)}</a>' for item in taggings
        ) + "</div>"
    article = f'''<main>
<article class="post">
{heading}
{tags}
{patch_controls}
<div class="body">{body_html}</div>
{item_footer(post, shares or [])}
{patch_catalog}
{render_footnotes(post, content_root, posts, outgoing, patch_states)}
{render_incoming_links(post, content_root, posts, [link for link in links if link.active and link.to_id == post.post_id], patch_states)}
</article>
</main>
{patch_script}'''
    return page_shell(title, "../../", article)


def item_footer(post: Post, shares: list[Share]) -> str:
    """The bottom of a post, in the feed and on its page: the time it was written (text, not a link) and where it was
    shared. No type name: the type is chosen before writing, not shown (source:fd-04)."""
    badges = "".join(
        f'<a class="share-badge" href="{html.escape(item.url, quote=True)}" aria-label="{SHARE_PLACES[item.where][0]}" '
        f'title="{SHARE_PLACES[item.where][0]}"><svg viewBox="0 0 24 24" aria-hidden="true">{SHARE_PLACES[item.where][1]}</svg></a>'
        for item in shares
    )
    return (f'<footer class="item-footer">{time_element(post.written)}'
            + (f'<span class="shares">{badges}</span>' if badges else "") + "</footer>")


def feed_item(post: Post, content_root: Path, patch_state: PatchState, shares: list[Share] | None = None,
              root: str = "", reason: Tagging | None = None) -> str:
    body_html, first_text = render_body(
        patch_state.body, content_root, post.source, root + "images/"
    )
    href = f"{root}p/{post.post_id}/"
    if post.post_type == "short":
        # a short post has no title line: its whole body is the item
        title = None
        top = f'<div class="body">{body_html}</div>'
    else:
        title = post.title or first_text[:80] + ("…" if len(first_text) > 80 else "")
        top = f'<h2 class="feed-title">{html.escape(title, quote=False)}</h2>'
    # the whole box is the way into the post — its links, the posts pointing at it, its patches, its shares: one empty
    # link covering the box (CSS), with the share badges above it, so no link sits inside another
    link = f'<a class="item-link" href="{html.escape(href, quote=True)}" aria-label="{html.escape(title or "글 보기", quote=True)}"></a>'
    why = (f'<p class="tag-reason">이 태그를 단 이유: {html.escape(reason.why, quote=False)} · {time_element(reason.at)}</p>'
           if reason else "")
    return f'''<article class="feed-item">
{link}
{top}
{why}{item_footer(post, shares or [])}
</article>'''


def tag_cloud(taggings: dict[str, list[Tagging]], root: str = "") -> str:
    """Every tag a post has now, by name, with how many posts; the more posts, the larger. No tags, no cloud."""
    counts: dict[str, int] = {}
    for items in taggings.values():
        for item in items:
            counts[item.tag] = counts.get(item.tag, 0) + 1
    if not counts:
        return ""
    low, high = min(counts.values()), max(counts.values())
    entries = []
    for tag in sorted(counts):
        size = 0.9 + (0.7 * (counts[tag] - low) / (high - low) if high > low else 0.2)
        entries.append(f'<li><a class="tag" href="{root}tags/{quote(tag, safe="")}/" style="font-size: {size:.2f}rem">'
                       f'{html.escape(tag, quote=False)}</a><span class="count">{counts[tag]}</span></li>')
    return '<aside class="tag-cloud">\n<h2>태그</h2>\n<ul>' + "".join(entries) + "</ul>\n</aside>"


def render_feed(
    posts: list[Post],
    content_root: Path,
    patch_states: dict[str, PatchState],
    shares: dict[str, list[Share]] | None = None,
    taggings: dict[str, list[Tagging]] | None = None,
) -> str:
    ordered = sorted(posts, key=lambda post: post.post_id)
    ordered.sort(key=lambda post: post.written, reverse=True)
    items = "\n".join(
        feed_item(post, content_root, patch_states[post.post_id], (shares or {}).get(post.post_id, [])) for post in ordered
    )
    body = (f'<div class="feed-layout">\n<main>\n<h1>피드</h1>\n<section class="feed">\n{items}\n</section>\n</main>\n'
            f'{tag_cloud(taggings or {})}\n</div>')
    return page_shell("피드", "", body, current="feed")


def render_tag_page(
    tag: str,
    posts: list[Post],
    content_root: Path,
    patch_states: dict[str, PatchState],
    shares: dict[str, list[Share]],
    taggings: dict[str, list[Tagging]],
) -> str:
    """The posts that have this tag now, newest first, each with why the tag is there."""
    tagged = [(post, next(item for item in taggings.get(post.post_id, []) if item.tag == tag)) for post in posts
              if any(item.tag == tag for item in taggings.get(post.post_id, []))]
    tagged.sort(key=lambda pair: pair[0].written, reverse=True)
    items = "\n".join(
        feed_item(post, content_root, patch_states[post.post_id], shares.get(post.post_id, []), root="../../", reason=reason)
        for post, reason in tagged
    )
    title = f"태그: {tag}"
    body = f'<main>\n<h1>{html.escape(title, quote=False)}</h1>\n<section class="feed">\n{items}\n</section>\n</main>'
    return page_shell(title, "../../", body)


def parse_about(content_root: Path) -> str:
    path = content_root / ABOUT_FILE
    if not path.is_file():
        fail(path)
    try:
        body = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail(path)
    if not body.strip():
        fail(path)
    blocks = markdown_blocks(body)
    rendered = "\n".join(
        render_block(block, content_root, path, "../images/", external_links=True) for block in blocks
    )
    body = f'<main>\n<article class="post">\n<div class="body">{rendered}</div>\n</article>\n</main>'   # the post page's frame: one look for every page
    return page_shell("소개", "../", body, current="about")


def copy_images(content_root: Path, output_root: Path) -> None:
    source = content_root / "images"
    destination = output_root / "images"
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for item in sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix()):
            relative = item.relative_to(source)
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, target)


def write_output(
    posts: list[Post],
    content_root: Path,
    output_root: Path,
    links: list[Link],
    patch_states: dict[str, PatchState],
    about_page: str,
    shares: dict[str, list[Share]] | None = None,
    taggings: dict[str, list[Tagging]] | None = None,
) -> None:
    shares, taggings = shares or {}, taggings or {}
    (output_root / "assets").mkdir(parents=True, exist_ok=True)
    (output_root / "p").mkdir(parents=True, exist_ok=True)
    (output_root / "assets" / "site.css").write_bytes(CSS.encode("utf-8"))
    (output_root / "assets" / "time.js").write_bytes(JS.encode("utf-8"))
    (output_root / ".nojekyll").write_bytes(b"")
    copy_images(content_root, output_root)
    (output_root / "index.html").write_bytes(
        render_feed(posts, content_root, patch_states, shares, taggings).encode("utf-8")
    )
    (output_root / "about").mkdir()
    (output_root / "about" / "index.html").write_bytes(about_page.encode("utf-8"))
    for post in posts:
        page = render_post_page(post, content_root, posts, links, patch_states, shares.get(post.post_id, []), taggings.get(post.post_id, []))
        (output_root / "p" / post.post_id).mkdir()
        (output_root / "p" / post.post_id / "index.html").write_bytes(page.encode("utf-8"))
    for tag in sorted({item.tag for items in taggings.values() for item in items}):
        folder = output_root / "tags" / tag
        folder.mkdir(parents=True)
        (folder / "index.html").write_bytes(
            render_tag_page(tag, posts, content_root, patch_states, shares, taggings).encode("utf-8")
        )


def install_output(staging: Path, docs: Path) -> None:
    backup: Path | None = None
    try:
        if docs.exists() or docs.is_symlink():
            backup = docs.parent / f".docs-backup-{os.getpid()}"
            counter = 0
            while backup.exists() or backup.is_symlink():
                counter += 1
                backup = docs.parent / f".docs-backup-{os.getpid()}-{counter}"
            os.replace(docs, backup)
        os.replace(staging, docs)
    except Exception:
        if backup is not None and (not docs.exists()) and (backup.exists() or backup.is_symlink()):
            os.replace(backup, docs)
        raise
    finally:
        if backup is not None and (backup.exists() or backup.is_symlink()):
            shutil.rmtree(backup)


def build() -> None:
    root = Path.cwd()
    content_root = root / "content"
    docs = root / "docs"
    posts = parse_posts(content_root)
    patches = parse_patches(content_root, posts)
    patch_states = apply_patches(posts, patches)
    links = parse_links(content_root, posts, patch_states)
    about_page = parse_about(content_root)
    shares = parse_shares(content_root, posts)
    taggings = parse_tags(content_root, posts)

    staging = Path(tempfile.mkdtemp(prefix=".docs-staging-", dir=str(root)))
    try:
        write_output(posts, content_root, staging, links, patch_states, about_page, shares, taggings)
        install_output(staging, docs)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def main() -> int:
    try:
        build()
    except BuildError as error:
        print(f"build error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as error:
        print(f"build error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
