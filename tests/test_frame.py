import re
import unittest

from support import pid, read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
ID = pid(WRITTEN)
TAG = "기록"


def post_text(body="본문"):
    return f"written: {WRITTEN}\ntype: short\n\n{body}\n"


def fixture_kwargs():
    return {
        "about": "소개\n",
        "posts": {f"posts/{ID}.md": post_text()},
        "tags": [
            {
                "post": ID,
                "tag": TAG,
                "action": "added",
                "at": "2024-02-04T00:00:00Z",
                "why": "분류",
            }
        ],
    }


def nav(document):
    match = re.search(
        r'(?s)<header class="site-header">\s*<nav class="site-nav">(.*?)</nav>\s*</header>',
        document,
    )
    return match.group(1) if match else None


def nav_without_hrefs(document):
    markup = nav(document)
    if markup is None:
        return None
    return re.sub(r'href="[^"]*"', 'href="<relative>"', re.sub(r"\s+", " ", markup)).strip()


def docs_snapshot(root):
    docs = root / "docs"
    return {
        path.relative_to(docs).as_posix(): path.read_bytes()
        for path in docs.rglob("*")
        if path.is_file()
    }


class FrameContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._site = temporary_site(images={"cover.png": b"image"}, **fixture_kwargs())
        cls.root = cls._site.__enter__()
        result = run_build(cls.root)
        if result.returncode != 0:
            cls._site.__exit__(RuntimeError, RuntimeError(result.stderr), None)
            raise RuntimeError(f"shared frame fixture failed to build: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._site.__exit__(None, None, None)
        super().tearDownClass()

    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def test_Q_build_every_page_has_the_same_frame_and_ordered_feed_about_nav(self):
        root = self.root
        pages = {
                "feed": ("index.html", "./", "about/"),
                "post": (f"p/{ID}/index.html", "../../", "../../about/"),
                "about": ("about/index.html", "../", "./"),
                "tag": (f"tags/{TAG}/index.html", "../../", "../../about/"),
        }

        normalized_nav = None
        for name, (relative, feed_href, about_href) in pages.items():
            with self.subTest(page=name):
                document = read(root, relative)
                current_nav = nav(document)
                self.assertIsNotNone(current_nav, msg=document)
                self.assertRegex(
                    document,
                    r'<header class="site-header">\s*<nav class="site-nav">',
                )
                links = re.findall(
                    r'<a\b[^>]*\bhref="([^"]+)"[^>]*>([^<]*)</a>',
                    current_nav,
                )
                self.assertEqual(
                    [text for _, text in links], ["피드", "소개", "English"],
                    msg=current_nav,
                )
                feed_index = next(
                    (index for index, (_, text) in enumerate(links) if text == "피드"),
                    None,
                )
                about_index = next(
                    (index for index, (_, text) in enumerate(links) if text == "소개"),
                    None,
                )
                self.assertIsNotNone(feed_index, msg=current_nav)
                self.assertIsNotNone(about_index, msg=current_nav)
                self.assertLess(feed_index, about_index)
                self.assertEqual(links[feed_index][0], feed_href)
                self.assertEqual(links[about_index][0], about_href)
                self.assertRegex(
                    current_nav,
                    r'(?s)<details class="lang-menu"><summary>한국어</summary><ul>'
                    r'<li><span aria-current="true" lang="ko">한국어</span></li>'
                    r'<li><a class="lang-switch"[^>]*\bhreflang="en"[^>]*\blang="en"[^>]*>English</a></li>'
                    r'</ul></details>\s*$',
                )
                body = re.search(r"(?s)<body\b[^>]*>(.*?)</body>", document)
                self.assertIsNotNone(body, msg=document)
                self.assertRegex(body.group(1), r'class="[^"]*\bframe\b[^"]*"')
                current_normalized = nav_without_hrefs(document)
                if normalized_nav is None:
                    normalized_nav = current_normalized
                self.assertEqual(current_normalized, normalized_nav)

    def test_Q_build_site_css_uses_stable_gutter_and_shared_seventy_rem_widths(self):
        css = read(self.root, "assets/site.css")
        self.assertRegex(css, r"scrollbar-gutter\s*:\s*stable\b")
        for selector in (r"\.site-nav", r"\.frame"):
            with self.subTest(selector=selector):
                rule = re.search(
                    rf"(?s)(?:^|}})[^{{}}]*{selector}[^{{}}]*\{{([^{{}}]*)\}}",
                    css,
                )
                self.assertIsNotNone(rule, msg=selector)
                self.assertRegex(rule.group(1), r"max-width\s*:\s*70rem\b")
        self.assertNotRegex(
            css,
            r"(?is)(?:^|})[^{}]*\bbody\b[^{}]*\{[^}]*\bmax-width\s*:",
        )

    def test_Q_build_docs_root_has_only_the_declared_top_level_entries(self):
        actual = {path.name for path in (self.root / "docs").iterdir()}
        self.assertEqual(
            actual,
            {"index.html", "p", "about", "tags", "en", "assets", "images", ".nojekyll"},
        )

    def test_Q_build_same_content_twice_produces_byte_identical_docs(self):
        with temporary_site(**fixture_kwargs()) as first:
            with temporary_site(**fixture_kwargs()) as second:
                self.assert_builds(first)
                self.assert_builds(second)
                self.assertEqual(docs_snapshot(first), docs_snapshot(second))


if __name__ == "__main__":
    unittest.main()
