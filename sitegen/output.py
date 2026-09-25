"""Output installation and the top-level build sequence."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from .markdown import external_link_spans
from .pages import parse_about, render_feed, render_post_page, render_tag_page
from .patches import PatchState, apply_patches
from .records import (
    BuildError,
    Link,
    Post,
    Share,
    Tagging,
    parse_links,
    parse_patches,
    parse_posts,
    parse_shares,
    parse_tags,
    fail,
)


ASSETS = Path(__file__).resolve().parent / "assets"


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


def copy_brands(output_root: Path) -> None:
    source = ASSETS / "brands"
    destination = output_root / "assets" / "brands"
    destination.mkdir(parents=True, exist_ok=True)
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
    (output_root / "assets" / "site.css").write_bytes((ASSETS / "site.css").read_bytes())
    (output_root / "assets" / "time.js").write_bytes((ASSETS / "time.js").read_bytes())
    copy_brands(output_root)
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
    for patch_state in patch_states.values():
        for link_start, link_end in external_link_spans(patch_state.body):
            for region_start, region_end, patch in patch_state.patch_ranges():
                overlaps = link_start < region_end and region_start < link_end
                covers_link = region_start <= link_start and link_end <= region_end
                if overlaps and not covers_link:
                    fail(patch.source)
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
