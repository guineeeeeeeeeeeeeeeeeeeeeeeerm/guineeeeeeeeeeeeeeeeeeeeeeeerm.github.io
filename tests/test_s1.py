import html
import re
import unittest
from pathlib import Path
from support import pid, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"


ID = pid()
W2, W3 = "2024-02-03T04:05:07Z", "2024-02-03T04:05:08Z"   # more posts in one site: other moments, same minute


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


def files_snapshot(directory):
    if not directory.exists():
        return None
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def title_text(document, post_id):
    """The text in a feed item's title place (source:fd-04: the whole box is the link; the title is text in it)."""
    for item in re.findall(r'(?s)<article class="feed-item">(.*?)</article>', document):
        if f'href="p/{post_id}/"' in item:
            title = re.search(r'(?s)<h2 class="feed-title">(.*?)</h2>', item)
            if title:
                return html.unescape(re.sub(r"<[^>]+>", "", title.group(1)))
    raise AssertionError(f"no titled feed item for {post_id!r}")


class S1GeneratorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._common_site = temporary_site({f"{ID}.md": post_text()})
        cls.common_root = cls._common_site.__enter__()
        result = run_build(cls.common_root)
        if result.returncode != 0:
            cls._common_site.__exit__(RuntimeError, RuntimeError(result.stderr), None)
            raise RuntimeError(f"shared S1 fixture failed to build: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._common_site.__exit__(None, None, None)
        super().tearDownClass()

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
        posts = {f"{ID}.md": post_text("medium", title="Hello", body="hello")}
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
            self.assertTrue((docs / "p" / ID / "index.html").is_file())
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

    def test_Q_build_generated_assets_have_no_external_script_font_or_style_urls(self):
        docs = self.common_root / "docs"
        rendered = "\n".join(
            path.read_text(encoding="utf-8")
            for path in docs.rglob("*")
            if path.is_file() and path.suffix in {".html", ".css", ".js"}
        )
        # Q-meta: the canonical link names the page's own absolute address; it loads nothing.
        rendered = re.sub(r'<link rel="canonical" href="https://guineeeeeeeeeeeeeeeeeeeeeeeerm\.github\.io/[^"]*">', "", rendered)
        self.assertNotRegex(rendered, r"(?:src|href)\s*=\s*[\"']https?://")
        self.assertNotRegex(rendered, r"@import\s+url\(\s*[\"']https?://")

    def test_Q_build_bad_input_is_atomic_and_reports_one_bad_file_line(self):
        bad_file = f"{ID}.md"
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

    def test_Q_post_type_is_required(self):
        with temporary_site({f"{ID}.md": "written: " + WRITTEN + "\n\n본문"}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_header_key_and_value_whitespace_are_ignored_but_key_case_matters(self):
        valid = " written :   " + WRITTEN + "  \n type : short \n\n본문"
        with temporary_site({f"{ID}.md": valid}) as root:
            self.assert_build_succeeds(root)
            self.assertTrue((root / "docs" / "p" / ID / "index.html").is_file())

        with temporary_site(
            {f"{ID}.md": "Written: " + WRITTEN + "\ntype: short\n\n본문"}
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_bad_written_format_is_a_build_error(self):
        bad = post_text(written="2024-02-03 04:05:06+00:00")   # the file is named for the moment it meant
        with temporary_site({f"{ID}.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_unknown_header_key_is_a_build_error(self):
        bad = "written: " + WRITTEN + "\ntype: short\nunknown: value\n\n본문"
        with temporary_site({f"{ID}.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_colonless_header_line_is_a_build_error(self):
        bad = "written: " + WRITTEN + "\ntype short\n\n본문"
        with temporary_site({f"{ID}.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_duplicate_header_key_is_a_build_error(self):
        bad = (
            "written: "
            + WRITTEN
            + "\ntype: short\ntype: medium\n\n본문"
        )
        with temporary_site({f"{ID}.md": bad}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_short_title_is_forbidden_and_medium_long_titles_are_optional(self):
        with temporary_site(
            {f"{ID}.md": post_text(title="forbidden")}
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

        posts = {
            f"{ID}.md": post_text("medium", title="Medium title"),
            f"{pid(W2)}.md": post_text("long", written=W2),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            medium = (root / "docs" / "p" / ID / "index.html").read_text(encoding="utf-8")
            long = (root / "docs" / "p" / pid(W2) / "index.html").read_text(encoding="utf-8")
            self.assertIn("Medium title", medium)
            self.assertTrue((root / "docs" / "p" / pid(W2) / "index.html").is_file())
            self.assertNotIn("None", long)

    def test_Q_post_type_must_be_short_medium_or_long(self):
        with temporary_site({f"{ID}.md": post_text("tiny")}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_duplicate_ids_are_a_build_error(self):
        posts = {
            f"{ID}.md": post_text(body="one"),
            f"{ID}.txt": post_text(body="two"),
        }
        with temporary_site(posts) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(ID, result.stderr)

    def test_Q_post_empty_body_is_a_build_error(self):
        empty = "written: " + WRITTEN + "\ntype: short\n\n"
        with temporary_site({f"{ID}.md": empty}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_tags_header_is_a_build_error(self):
        # source:tg-01: tags are events in the tag table (Q-tag), never a header line
        text = post_text(tags="alpha, beta", body="태그 본문")
        with temporary_site({f"{ID}.md": text}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

    def test_Q_post_missing_image_is_a_build_error(self):
        body = "![missing](images/not-present.png)"
        with temporary_site({f"{ID}.md": post_text(body=body)}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{ID}.md", result.stderr)

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
            {f"{ID}.md": post_text(body=body)},
            images={"photo.png": b"photo"},
        ) as root:
            self.assert_build_succeeds(root)
            page = (root / "docs" / "p" / ID / "index.html").read_text(
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

    def test_Q_feed_orders_newest_first(self):
        old, mid, new = "2024-01-01T00:00:00Z", WRITTEN, "2024-03-01T00:00:00Z"
        posts = {
            f"{pid(old)}.md": post_text(written=old, body="old"),
            f"{pid(mid)}.md": post_text(written=mid, body="mid"),
            f"{pid(new)}.md": post_text("medium", written=new, title="new title", body="new body"),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            positions = [feed.index(f"p/{pid(w)}/") for w in [new, mid, old]]
            self.assertEqual(positions, sorted(positions))

    def test_Q_feed_titleless_medium_or_long_uses_80_screen_characters_and_ellipsis(self):
        # the screen text keeps the space between the two formatted spans: 40 + 1 + 41 characters
        screen_text = "가" * 40 + " " + "가" * 41
        body = "**" + "가" * 40 + "** *" + "가" * 41 + "*"
        with temporary_site(
            {f"{ID}.md": post_text("medium", body=body)}
        ) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            link = title_text(feed, ID)
            self.assertIn(screen_text[:80] + "…", link)
            self.assertNotIn(screen_text[:81], link)

    def test_Q_feed_titleless_image_first_paragraph_uses_image_alt_text(self):
        with temporary_site(
            {f"{ID}.md": post_text("long", body="![A small alt](images/a.png)")},
            images={"a.png": b"a"},
        ) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertIn("A small alt", title_text(feed, ID))

    def test_Q_time_uses_utc_datetime_text_and_title_on_every_rendered_time(self):
        text = post_text("medium", title="timed")
        with temporary_site({f"{ID}.md": text}) as root:
            self.assert_build_succeeds(root)
            for filename in [root / "docs" / "index.html", root / "docs" / "p" / ID / "index.html"]:
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
        scripts = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.common_root / "docs" / "assets").glob("*.js")
        )
        self.assertRegex(scripts, r"datetime")
        self.assertRegex(scripts, r"title")
        self.assertRegex(scripts, r"(?:toLocale|Intl\.DateTimeFormat)")

    def test_Q_ui_sets_korean_document_language_and_shows_no_type_names(self):
        posts = {
            f"{ID}.md": post_text("short"),
            f"{pid(W2)}.md": post_text("medium", written=W2, title="중간"),
            f"{pid(W3)}.md": post_text("long", written=W3, title="긴"),
        }
        with temporary_site(posts) as root:
            self.assert_build_succeeds(root)
            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertRegex(feed, r"<html\b[^>]*lang=[\"']ko[\"']")
            for type_name in ["짧은 글", "중간 글", "긴 글"]:
                self.assertNotIn(type_name, feed)
            for post_id, type_name in [
                (ID, "짧은 글"),
                (pid(W2), "중간 글"),
                (pid(W3), "긴 글"),
            ]:
                document = (root / "docs" / "p" / f"{post_id}" / "index.html").read_text(
                    encoding="utf-8"
                )
                self.assertRegex(document, r"<html\b[^>]*lang=[\"']ko[\"']")
                self.assertNotIn(type_name, document)


if __name__ == "__main__":
    unittest.main()
