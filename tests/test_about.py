import re
import unittest
from support import read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
ID = "20240203-040506"   # Q-post: a post's id is the moment it was written (WRITTEN)
ORG = "https://github.com/example-org"


def post_text(body="본문", post_type="short", title=None):
    lines = [f"written: {WRITTEN}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


class AboutPageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._common_site = temporary_site(
            {"about.md": "소개 글\n", f"posts/{ID}.md": post_text("글 하나")}
        )
        cls.common_root = cls._common_site.__enter__()
        result = run_build(cls.common_root)
        if result.returncode != 0:
            cls._common_site.__exit__(RuntimeError, RuntimeError(result.stderr), None)
            raise RuntimeError(f"shared about fixture failed to build: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._common_site.__exit__(None, None, None)
        super().tearDownClass()

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
            self.assertIn("<title>소개 — GuinEeeeeeeeeeeeeeeeeeeeeeeerm</title>", page)
            self.assertIn('<article class="post">', page)
            self.assertIn('<div class="body">', page)
            self.assertIn('src="../images/avatar.png"', page)
            self.assertIn('src="../images/org_logo.png"', page)
            self.assertIn("<strong>저</strong>", page)
            self.assertIn("<h2>긴작업</h2>", page)
            self.assertIn(f'<a href="{ORG}">긴작업</a>', page)
            self.assertEqual((root / "docs" / "images" / "avatar.png").read_bytes(), b"avatar")

    def test_the_about_page_looks_like_a_post_page(self):
        about, post = read(self.common_root, "about/index.html"), read(self.common_root, f"p/{ID}/index.html")
        for page in (about, post):
            self.assertIn('<article class="post">', page)
            self.assertIn('<div class="body">', page)
        css = read(self.common_root, "assets/site.css").lower()
        self.assertNotIn(".about", css, msg="no style of the about page's own")

    def test_about_md_is_not_a_post(self):
        self.assertFalse((self.common_root / "docs" / "p" / "about").exists())
        feed = read(self.common_root, "index.html")
        self.assertNotIn("소개 글", feed)
        self.assertIn("글 하나", feed)

    def test_a_missing_about_md_is_a_build_error(self):
        with temporary_site({f"posts/{ID}.md": post_text("글 하나")}, about=None) as root:
            self.assert_fails_naming_about(root)

    def test_an_external_link_must_be_http_or_https(self):
        with temporary_site({"about.md": "[여기](javascript:alert(1))\n"}) as root:
            self.assert_fails_naming_about(root)

    def test_an_empty_about_md_is_a_build_error(self):
        with temporary_site({"about.md": "\n  \n"}) as root:
            self.assert_fails_naming_about(root)

    def test_a_missing_image_on_the_about_page_is_a_build_error(self):
        with temporary_site({"about.md": "![나](images/none.png)\n"}) as root:
            self.assert_fails_naming_about(root)


if __name__ == "__main__":
    unittest.main()
