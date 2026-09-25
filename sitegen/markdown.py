"""The small Markdown renderer used by the site."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .patches import (
    PATCH_MARKER_RE,
    apply_anchor_replacements,
    patch_markup_tokens,
    render_patched_blocks,
)
from .records import fail

if TYPE_CHECKING:
    from .patches import PatchState


HEADING_RE = re.compile(r"^(#{1,3})[ \t]+(.*)$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
INLINE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)]*)\)"
    r"|\*\*(.+?)\*\*"
    r"|`([^`]+)`"
    r"|\*(?!\s)(.+?)(?<!\s)\*"
)
INLINE_WITH_LINKS_RE = re.compile(INLINE_RE.pattern + r"|\[([^\]]*)\]\(([^)]*)\)")


def external_link_spans(text: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for match in INLINE_WITH_LINKS_RE.finditer(text)
        if match.group(6) is not None
    ]


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
    wrap_images: bool = False,
) -> str:
    pieces: list[str] = []
    cursor = 0
    pattern = INLINE_WITH_LINKS_RE if external_links else INLINE_RE
    for match in pattern.finditer(text):
        pieces.append(html.escape(text[cursor : match.start()], quote=False))
        if external_links and match.group(6) is not None:
            label = match.group(6)
            address_with_markers = match.group(7).strip()
            address = PATCH_MARKER_RE.sub("", address_with_markers)
            if not re.match(r"https?://\S+$", address):
                fail(post_path)
            address_markers = PATCH_MARKER_RE.findall(address_with_markers)
            pieces.extend(address_markers)
            pieces.append(
                f'<a href="{html.escape(address, quote=True)}">{html.escape(label, quote=False)}</a>'
            )
        elif match.group(1) is not None:
            alt, width = image_width(match.group(1), post_path)
            image_path = match.group(2)
            image_source(content_root, image_path, post_path)
            image_url = image_prefix + image_path[7:]
            image = (
                f'<img src="{html.escape(image_url, quote=True)}" '
                f'alt="{html.escape(alt, quote=True)}"'
                + (f' width="{width}"' if width else "")
                + ">"
            )
            if wrap_images:
                pieces.append(
                    f'<a class="image-zoom" href="{html.escape(image_url, quote=True)}">{image}</a>'
                )
            else:
                pieces.append(image)
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
    wrap_images: bool = False,
) -> str:
    kind, value = block

    def inline(text: str) -> str:
        return inline_markdown(
            text, content_root, post_path, image_prefix, external_links, wrap_images
        )

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


def render_body(
    body: str,
    content_root: Path,
    post_path: Path,
    image_prefix: str,
    replacements: list[tuple[str, str]] | None = None,
    patch_state: PatchState | None = None,
    wrap_images: bool = False,
) -> tuple[str, str]:
    tokens: dict[str, str] = {}
    patch_tokens: dict[str, str] = {}
    if patch_state is not None and patch_state.has_patches:
        body, regions = patch_state.regions_and_marked_body()
        patch_tokens = patch_markup_tokens(regions)
    if replacements:
        body, tokens = apply_anchor_replacements(body, replacements, post_path)
    blocks = markdown_blocks(body)
    rendered_blocks = [
        render_block(
            block,
            content_root,
            post_path,
            image_prefix,
            external_links=True,
            wrap_images=wrap_images,
        )
        for block in blocks
    ]
    rendered_blocks = render_patched_blocks(rendered_blocks, patch_tokens)
    rendered = "\n".join(rendered_blocks)
    for token, replacement in tokens.items():
        rendered = rendered.replace(token, replacement)
    first = next(
        (rendered_block for block, rendered_block in zip(blocks, rendered_blocks) if block[0] == "paragraph"),
        rendered_blocks[0] if rendered_blocks else "",
    )
    return rendered, visible_text(first)
