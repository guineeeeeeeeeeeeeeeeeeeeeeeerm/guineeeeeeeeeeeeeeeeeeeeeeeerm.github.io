"""HTML page rendering for posts, the feed, tags, and the about page."""

from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import quote

from .markdown import markdown_blocks, render_block, render_body
from .patches import PatchState, patch_data_script, patch_history_catalog
from .records import (
    ABOUT_FILE,
    SHARE_PLACES,
    Link,
    Post,
    Share,
    Tagging,
    fail,
    time_element,
)


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
