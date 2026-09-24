import re
import unittest
from support import BUILD, ROOT, read, run_build, temporary_site


README = ROOT / "README.md"
WRITTEN = "2024-02-03T04:05:06Z"
ID = "20240203-040506"   # Q-post: a post's id is the moment it was written (WRITTEN)
ORG = "https://github.com/example-org"

ABOUT_EXAMPLE = re.compile(
    r"(?ms)^```about[ \t]+content/about\.md[ \t]*\n(?P<body>.*?)^```[ \t]*$"
)
IMAGE_PATH = re.compile(r"!\[[^\]]*\]\((images/[^)]+)\)")


def post_text(body="본문", post_type="short", title=None):
    lines = [f"written: {WRITTEN}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def menu(document):
    match = re.search(r"(?s)<header>(.*?)</header>", document)
    return match.group(1) if match else ""


class AboutPageContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def assert_fails_naming_about(self, root):
        docs = root / "docs"
        docs.mkdir()
        (docs / "keep.html").write_text("before", encoding="utf-8")
        result = run_build(root)
        self.assertEqual(result.returncode, 1, msg=f"stderr={result.stderr!r}")
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, msg=result.stderr)
        self.assertIn("content/about.md", lines[0].replace("\\", "/"))
        self.assertEqual((docs / "keep.html").read_text(encoding="utf-8"), "before")

    def test_about_md_becomes_the_about_page_with_its_images(self):
        about = (
            "![나](images/avatar.png)\n\n"
            "안녕하세요, **저**입니다.\n\n"
            "## 긴작업\n\n"
            "![긴작업 로고](images/org_logo.png)\n\n"
            f"LLM 시대의 개발 도구를 만듭니다. [긴작업]({ORG})\n"
        )
        images = {"avatar.png": b"avatar", "org_logo.png": b"logo"}
        with temporary_site({"about.md": about}, images) as root:
            self.assert_builds(root)
            page = read(root, "about/index.html")
            self.assertIn('<html lang="ko">', page)
            self.assertIn("<title>소개</title>", page)
            self.assertIn('<article class="post">', page)
            self.assertIn('<div class="body">', page)
            self.assertIn('src="../images/avatar.png"', page)
            self.assertIn('src="../images/org_logo.png"', page)
            self.assertIn("<strong>저</strong>", page)
            self.assertIn("<h2>긴작업</h2>", page)
            self.assertIn(f'<a href="{ORG}">긴작업</a>', page)
            self.assertEqual((root / "docs" / "images" / "avatar.png").read_bytes(), b"avatar")

    def test_the_about_page_looks_like_a_post_page(self):
        with temporary_site({"about.md": "안녕하세요.\n", f"posts/{ID}.md": post_text("글 하나")}) as root:
            self.assert_builds(root)
            about, post = read(root, "about/index.html"), read(root, f"p/{ID}/index.html")
            for page in (about, post):
                self.assertRegex(page, r"<body>")   # no page-specific class: one look for every page
                self.assertIn('<article class="post">', page)
                self.assertIn('<div class="body">', page)
            css = read(root, "assets/site.css").lower()
            self.assertNotIn(".about", css, msg="no style of the about page's own")
            self.assertNotIn("#0e0e10", css)
            self.assertNotIn("text-align: center", css)

    def test_about_md_is_not_a_post(self):
        with temporary_site(
            {"about.md": "소개 글\n", f"posts/{ID}.md": post_text("글 하나")}
        ) as root:
            self.assert_builds(root)
            self.assertFalse((root / "docs" / "p" / "about").exists())
            feed = read(root, "index.html")
            self.assertNotIn("소개 글", feed)
            self.assertIn("글 하나", feed)

    def test_every_page_has_the_feed_and_about_menu_as_folder_links(self):
        with temporary_site(
            {"about.md": "소개 글\n", f"posts/{ID}.md": post_text("글 하나")}
        ) as root:
            self.assert_builds(root)
            for page, feed, about in (
                ("index.html", "./", "about/"),
                (f"p/{ID}/index.html", "../../", "../../about/"),
                ("about/index.html", "../", "./"),
            ):
                with self.subTest(page=page):
                    header = menu(read(root, page))
                    self.assertIn(f'<a href="{feed}">피드</a>', header)
                    self.assertIn(f'<a href="{about}">소개</a>', header)
                    self.assertNotIn(".html", header)

    def test_a_missing_about_md_is_a_build_error(self):
        with temporary_site({f"posts/{ID}.md": post_text("글 하나")}, about=None) as root:
            self.assert_fails_naming_about(root)

    def test_external_links_are_links_only_on_the_about_page(self):
        body = f"여기로 [가기]({ORG})\n"
        with temporary_site({"about.md": "소개\n", f"posts/{ID}.md": post_text(body)}) as root:
            self.assert_builds(root)
            page = read(root, f"p/{ID}/index.html")
            self.assertNotIn(f'href="{ORG}"', page)
            self.assertIn(f"[가기]({ORG})", page)

    def test_an_external_link_must_be_http_or_https(self):
        for address in ("javascript:alert(1)", "p/hello.html", "mailto:me@example.com", ""):
            with self.subTest(address=address):
                with temporary_site({"about.md": f"[여기]({address})\n"}) as root:
                    self.assert_fails_naming_about(root)

    def test_an_empty_about_md_is_a_build_error(self):
        with temporary_site({"about.md": "\n  \n"}) as root:
            self.assert_fails_naming_about(root)

    def test_a_missing_image_on_the_about_page_is_a_build_error(self):
        with temporary_site({"about.md": "![나](images/none.png)\n"}) as root:
            self.assert_fails_naming_about(root)

    def test_the_readme_shows_how_to_write_the_about_page_and_its_example_builds(self):
        text = README.read_text(encoding="utf-8")
        match = ABOUT_EXAMPLE.search(text)
        self.assertIsNotNone(match, msg="README needs a ```about content/about.md example")
        heading = text.rfind("\n## ", 0, match.start())
        self.assertIn("소개", text[heading : text.find("\n", heading + 1)])
        body = match.group("body")
        images = {path[len("images/"):]: b"image" for path in IMAGE_PATH.findall(body)}
        with temporary_site({"about.md": body}, images) as root:
            self.assert_builds(root)
            self.assertTrue((root / "docs" / "about" / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
