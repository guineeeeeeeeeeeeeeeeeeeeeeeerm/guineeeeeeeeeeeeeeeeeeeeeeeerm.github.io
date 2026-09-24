import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path


BUILD = Path(__file__).resolve().parents[1] / "build.py"
WRITTEN = "2024-02-03T04:05:06Z"


def post_text(
    post_type="short",
    written=WRITTEN,
    title=None,
    tags=None,
    body="본문",
):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    if tags is not None:
        lines.append(f"tags: {tags}")
    return "\n".join(lines) + "\n\n" + body


@contextmanager
def temporary_site(posts, images=None, old_docs=None, root_index=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        content.mkdir()
        (content / "about.md").write_text("소개\n", encoding="utf-8")   # Q-about: every site has its about page
        for filename, text in posts.items():
            path = content / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        for filename, data in (images or {}).items():
            path = content / "images" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        if old_docs is not None:
            docs = root / "docs"
            for filename, data in old_docs.items():
                path = docs / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

        if root_index is not None:
            (root / "index.html").write_text(root_index, encoding="utf-8")

        yield root


def run_build(root):
    return subprocess.run(
        [sys.executable, str(BUILD)],
        cwd=root,
        capture_output=True,
        text=True,
    )


def files_snapshot(directory):
    if not directory.exists():
        return None
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


class AnchorTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {"href": dict(attrs).get("href"), "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(
                (self.current["href"], "".join(self.current["text"]))
            )
            self.current = None


def anchor_text(document, post_id):
    parser = AnchorTextParser()
    parser.feed(document)
    suffix = f"/{post_id}/"
    for href, text in parser.links:
        if href and (href == f"p/{post_id}/" or href.endswith(suffix)):
            return text
    raise AssertionError(f"no link for {post_id!r}")


class S1GeneratorContractTests(unittest.TestCase):
    def assert_build_succeeds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def test_Q_build_recreates_the_feed_posts_assets_images_and_nojekyll(self):
        image = b"not an image format; the bytes still must be copied"
        posts = {"hello.md": post_text("medium", title="Hello", body="hello")}
        old_docs = {
            "stale.html": b"remove me",
            "assets/stale.js": b"remove me",
        }
        with temporary_site(
            posts,
            images={"picture.bin": image},
            old_docs=old_docs,
            root_index="repository landing page",
        ) as root:
            self.assert_build_succeeds(root)
            docs = root / "docs"
            self.assertTrue((docs / "index.html").is_file())
            self.assertTrue((docs / "p" / "hello" / "index.html").is_file())
            self.assertTrue(any((docs / "assets").glob("*.css")))
            self.assertTrue(any((docs / "assets").glob("*.js")))
            self.assertEqual((docs / "images" / "picture.bin").read_bytes(), image)
            self.assertTrue((docs / ".nojekyll").is_file())
            self.assertEqual((docs / ".nojekyll").read_bytes(), b"")
            self.assertFalse((docs / "stale.html").exists())
            self.assertFalse((docs / "assets" / "stale.js").exists())
            self.assertNotEqual(
                (docs / "index.html").read_text(encoding="utf-8"),
                "repository landing page",
            )

    def test_Q_build_same_input_is_byte_identical_on_second_build(self):
        posts = {
            "b.md": post_text(post_type="medium", title="B", body="two"),
            "a.md": post_text(body="one"),
        }
        with temporary_site(posts, images={"pixel.dat": b"123"}) as root:
            self.assert_build_succeeds(root)
            first = files_snapshot(root / "docs")
            self.assert_build_succeeds(root)
            second = files_snapshot(root / "docs")
            self.assertEqual(first, second)

    def test_Q_build_generated_assets_have_no_external_script_font_or_style_urls(self):
        with temporary_site({"post.md": post_text()}) as root:
            self.assert_build_succeeds(root)
            docs = root / "docs"
            rendered = "\n".join(
                path.read_text(encoding="utf-8")
                for path in docs.rglob("*")
                if path.is_file() and path.suffix in {".html", ".css", ".js"}
            )
            self.assertNotRegex(rendered, r"(?:src|href)\s*=\s*[\"']https?://")
            self.assertNotRegex(rendered, r"@import\s+url\(\s*[\"']https?://")

    def test_Q_build_bad_input_is_atomic_and_reports_one_bad_file_line(self):
        bad_file = "bad.md"
        old_docs = {
            "index.html": b"old index",
            "p/old.html": b"old post",
            "assets/site.css": b"old css",
        }
        with temporary_site(
            {bad_file: "type: short\n\nmissing written"},
            old_docs=old_docs,
        ) as root:
            before = files_snapshot(root / "docs")
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(result.stderr.strip().splitlines()), 1)
            self.assertIn(bad_file, result.stderr)
            self.assertEqual(files_snapshot(root / "docs"), before)

    def test_Q_post_written_is_required(self):
        with temporary_site({"missing-written.md": "type: short\n\n본문"}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing-written.md", result.stderr)

    def test_Q_post_type_is_required(self):
        with temporary_site({"missing-type.md": "written: " + WRITTEN + "\n\n본문"}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing-type.md", result.stderr)

    def test_Q_post_header_key_and_value_whitespace_are_ignored_but_key_case_matters(self):
        valid = " written :   " + WRITTEN + "  \n type : short \n\n본문"
        with temporary_site({"spaces.md": valid}) as root:
            self.assert_build_succeeds(root)
            self.assertTrue((root / "docs" / "p" / "spaces" / "index.html").is_file())

        with temporary_site(
            {"case.md": "Written: " + WRITTEN + "\ntype: short\n\n본문"}
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("case.md", result.stderr)

    def test_Q_post_bad_written_format_is_a_build_error(self):
        bad = post_text(written="2024-02-03 04:05:06+00:00")
        with temporary_site({"bad-written.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("bad-written.md", result.stderr)

    def test_Q_post_unknown_header_key_is_a_build_error(self):
        bad = "written: " + WRITTEN + "\ntype: short\nunknown: value\n\n본문"
        with temporary_site({"unknown-key.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("unknown-key.md", result.stderr)

    def test_Q_post_colonless_header_line_is_a_build_error(self):
        bad = "written: " + WRITTEN + "\ntype short\n\n본문"
        with temporary_site({"colonless.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("colonless.md", result.stderr)

    def test_Q_post_duplicate_header_key_is_a_build_error(self):
        bad = (
            "written: "
            + WRITTEN
            + "\ntype: short\ntype: medium\n\n본문"
        )
        with temporary_site({"duplicate-key.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("duplicate-key.md", result.stderr)

    def test_Q_post_short_title_is_forbidden_and_medium_long_titles_are_optional(self):
        with temporary_site(
            {"short-title.md": post_text(title="forbidden")}
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("short-title.md", result.stderr)

        posts = {
            "medium.md": post_text("medium", title="Medium title"),
            "long.md": post_text("long"),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            medium = (root / "docs" / "p" / "medium" / "index.html").read_text(encoding="utf-8")
            long = (root / "docs" / "p" / "long" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Medium title", medium)
            self.assertTrue((root / "docs" / "p" / "long" / "index.html").is_file())
            self.assertNotIn("None", long)

    def test_Q_post_type_must_be_short_medium_or_long(self):
        with temporary_site({"bad-type.md": post_text("tiny")}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("bad-type.md", result.stderr)

    def test_Q_post_duplicate_ids_are_a_build_error(self):
        posts = {
            "same.md": post_text(body="one"),
            "same.txt": post_text(body="two"),
        }
        with temporary_site(posts) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("same", result.stderr)

    def test_Q_post_empty_body_is_a_build_error(self):
        empty = "written: " + WRITTEN + "\ntype: short\n\n"
        with temporary_site({"empty.md": empty}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("empty.md", result.stderr)

    def test_Q_post_tags_trim_whitespace_drop_empty_names_and_are_plain_text(self):
        text = post_text(tags="  alpha, , beta  ,   ", body="태그 본문")
        with temporary_site({"tags.md": text}) as root:
            self.assert_build_succeeds(root)
            page = (root / "docs" / "p" / "tags" / "index.html").read_text(encoding="utf-8")
            self.assertIn("alpha", page)
            self.assertIn("beta", page)
            self.assertNotRegex(page, r"href=[\"'][^\"']*(?:alpha|beta)")
            self.assertNotIn("tag list", page.lower())
            self.assertFalse((root / "docs" / "tags").exists())

    def test_Q_post_missing_image_is_a_build_error(self):
        body = "![missing](images/not-present.png)"
        with temporary_site({"missing-image.md": post_text(body=body)}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing-image.md", result.stderr)

    def test_Q_post_images_only_body_is_valid_and_renders_image(self):
        body = "![Only alt](images/only.png)"
        with temporary_site(
            {"image-only.md": post_text(body=body)},
            images={"only.png": b"image bytes"},
        ) as root:
            self.assert_build_succeeds(root)
            page = (root / "docs" / "p" / "image-only" / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertRegex(page, r"<img\b[^>]*alt=[\"']Only alt")

    def test_Q_post_markdown_subset_renders_and_html_is_shown_as_text(self):
        body = (
            "# One\n\n"
            "Paragraph with **bold**, *italic*, and `code`.\n\n"
            "## Two\n\n"
            "- first\n- second\n\n"
            "> quoted\n\n"
            "### Three\n\n"
            "![Alt text](images/photo.png)\n\n"
            "<span>literal HTML</span>"
        )
        with temporary_site(
            {"markdown.md": post_text(body=body)},
            images={"photo.png": b"photo"},
        ) as root:
            self.assert_build_succeeds(root)
            page = (root / "docs" / "p" / "markdown" / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertRegex(page, r"<h1\b[^>]*>One</h1>")
            self.assertRegex(page, r"<h2\b[^>]*>Two</h2>")
            self.assertRegex(page, r"<h3\b[^>]*>Three</h3>")
            self.assertIn("<strong>bold</strong>", page)
            self.assertIn("<em>italic</em>", page)
            self.assertIn("<code>code</code>", page)
            self.assertIn("<blockquote", page)
            self.assertIn("<li>first</li>", page)
            self.assertIn("alt=\"Alt text\"", page)
            self.assertIn("&lt;span&gt;literal HTML&lt;/span&gt;", page)
            self.assertNotIn("<span>literal HTML</span>", page)

    def test_Q_post_page_shows_title_written_tags_and_type_name(self):
        text = post_text(
            post_type="long",
            title="A visible title",
            tags="alpha,beta",
            body="page body",
        )
        with temporary_site({"page.md": text}) as root:
            self.assert_build_succeeds(root)
            page = (root / "docs" / "p" / "page" / "index.html").read_text(encoding="utf-8")
            self.assertIn("A visible title", page)
            self.assertIn("page body", page)
            self.assertIn("alpha", page)
            self.assertIn("beta", page)
            self.assertIn("긴 글", page)

    def test_Q_feed_orders_newest_first_and_ids_ascending_for_equal_times(self):
        posts = {
            "z-old.md": post_text(written="2024-01-01T00:00:00Z", body="old"),
            "b-tie.md": post_text(written=WRITTEN, body="tie b"),
            "a-tie.md": post_text(written=WRITTEN, body="tie a"),
            "new.md": post_text(
                "medium",
                written="2024-03-01T00:00:00Z",
                title="new title",
                body="new body",
            ),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            positions = [feed.index(f"p/{post_id}/") for post_id in ["new", "a-tie", "b-tie", "z-old"]]
            self.assertEqual(positions, sorted(positions))
            self.assertLess(feed.index("a-tie"), feed.index("b-tie"))

    def test_Q_feed_short_shows_full_applied_body_medium_long_show_title_and_time(self):
        posts = {
            "short.md": post_text(body="**all short body**"),
            "medium.md": post_text(
                "medium", title="medium title", body="medium body must not be the summary"
            ),
            "long.md": post_text(
                "long", title="long title", body="long body must not be the summary"
            ),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertIn("<strong>all short body</strong>", feed)
            self.assertIn("medium title", feed)
            self.assertIn("long title", feed)
            self.assertNotIn("medium body must not be the summary", feed)
            self.assertNotIn("long body must not be the summary", feed)
            self.assertIn("2024-02-03 04:05 UTC", feed)
            self.assertIn("짧은 글", feed)
            self.assertIn("중간 글", feed)
            self.assertIn("긴 글", feed)

    def test_Q_feed_titleless_medium_or_long_uses_80_screen_characters_and_ellipsis(self):
        # the screen text keeps the space between the two formatted spans: 40 + 1 + 41 characters
        screen_text = "가" * 40 + " " + "가" * 41
        body = "**" + "가" * 40 + "** *" + "가" * 41 + "*"
        with temporary_site(
            {"untitled.md": post_text("medium", body=body)}
        ) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            link = anchor_text(feed, "untitled")
            self.assertIn(screen_text[:80] + "…", link)
            self.assertNotIn(screen_text[:81], link)

    def test_Q_feed_titleless_image_first_paragraph_uses_image_alt_text(self):
        with temporary_site(
            {"untitled-image.md": post_text("long", body="![A small alt](images/a.png)")},
            images={"a.png": b"a"},
        ) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertIn("A small alt", anchor_text(feed, "untitled-image"))

    def test_Q_feed_every_item_links_to_its_post_page_and_has_applied_content(self):
        posts = {
            "one.md": post_text(body="**shown in feed**"),
            "two.md": post_text("medium", title="Two", body="two body"),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertRegex(feed, r'href=["\']p/one/["\']')
            self.assertRegex(feed, r'href=["\']p/two/["\']')
            self.assertIn("<strong>shown in feed</strong>", feed)

    def test_Q_time_uses_utc_datetime_text_and_title_on_every_rendered_time(self):
        text = post_text("medium", title="timed")
        with temporary_site({"timed.md": text}) as root:
            self.assert_build_succeeds(root)
            for filename in [root / "docs" / "index.html", root / "docs" / "p" / "timed" / "index.html"]:
                document = filename.read_text(encoding="utf-8")
                self.assertRegex(
                    document,
                    r'<time\b[^>]*datetime=["\']2024-02-03T04:05:06Z["\'][^>]*>'
                    r'2024-02-03 04:05 UTC</time>',
                )
                self.assertRegex(
                    document,
                    r'<time\b[^>]*title=["\']2024-02-03 04:05 UTC["\']',
                )

    def test_Q_time_asset_localizes_time_and_retains_utc_title_without_external_code(self):
        with temporary_site({"timed.md": post_text()}) as root:
            self.assert_build_succeeds(root)
            scripts = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / "docs" / "assets").glob("*.js")
            )
            self.assertRegex(scripts, r"datetime")
            self.assertRegex(scripts, r"title")
            self.assertRegex(scripts, r"(?:toLocale|Intl\.DateTimeFormat)")

    def test_Q_ui_sets_korean_document_language_and_korean_type_names(self):
        posts = {
            "short.md": post_text("short"),
            "medium.md": post_text("medium", title="중간"),
            "long.md": post_text("long", title="긴"),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertRegex(feed, r"<html\b[^>]*lang=[\"']ko[\"']")
            for type_name in ["짧은 글", "중간 글", "긴 글"]:
                self.assertIn(type_name, feed)
            for post_id, type_name in [
                ("short", "짧은 글"),
                ("medium", "중간 글"),
                ("long", "긴 글"),
            ]:
                document = (root / "docs" / "p" / f"{post_id}" / "index.html").read_text(
                    encoding="utf-8"
                )
                self.assertRegex(document, r"<html\b[^>]*lang=[\"']ko[\"']")
                self.assertIn(type_name, document)


if __name__ == "__main__":
    unittest.main()
