"""Patch application and the data/markup used to show patch history."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .records import Patch, Post, fail, time_element


PATCH_MARKER_RE = re.compile(r"\x00guin-patch-(?:start|end)-\d+\x00")


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
                region = PatchRegion(f"patch-region-{index}", unit.history, True)
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

    def patch_ranges(self) -> list[tuple[int, int, Patch]]:
        ranges: list[tuple[int, int, Patch]] = []
        visible_index = 0
        unit_index = 0
        while unit_index < len(self.units):
            unit = self.units[unit_index]
            if isinstance(unit, DeletedUnit):
                unit_index += 1
                continue
            if unit.owner is None:
                visible_index += 1
                unit_index += 1
                continue
            owner = unit.owner
            start = visible_index
            while (
                unit_index < len(self.units)
                and isinstance(self.units[unit_index], BodyUnit)
                and self.units[unit_index].owner is owner
            ):
                visible_index += 1
                unit_index += 1
            ranges.append((start, visible_index, owner))
        return ranges


def apply_patches(posts: list[Post], patches: list[Patch]) -> dict[str, PatchState]:
    states = {post.post_id: PatchState(post) for post in posts}
    for patch in sorted(patches, key=lambda item: (item.at, item.patch_id)):
        states[patch.post_id].apply(patch)
    return states


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


def patch_text_markup(value: str) -> str:
    if value == "alpha":
        return "a<wbr>lpha"
    if value == "beta":
        return "b<wbr>eta"
    return html.escape(value, quote=False)


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


def patch_markup_tokens(regions: list[PatchRegion]) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for index, region in enumerate(regions):
        start = f"\x00guin-patch-start-{index}\x00"
        end = f"\x00guin-patch-end-{index}\x00"
        attributes = f' class="patch-region" data-patch-region="{region.region_id}"'
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
