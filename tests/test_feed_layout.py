import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


BUILD = Path(__file__).resolve().parents[1] / "build.py"
SHORT_AT, MEDIUM_AT, UNTITLED_AT = "2024-02-03T04:05:06Z", "2024-02-03T04:05:07Z", "2024-02-03T04:05:08Z"


def pid(written):
    """Q-post: a post's id is the moment it was written, YYYYMMDD-HHMMSS (UTC)."""
    return written[0:4] + written[5:7] + written[8:10] + "-" + written[11:13] + written[14:16] + written[17:19]


def post_text(written, post_type="short", title=None, body="본문"):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


@contextmanager
def temporary_site(posts):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        (content / "posts").mkdir(parents=True)
        (content / "about.md").write_text("소개\n", encoding="utf-8")   # Q-about: every site has its about page
        for written, text in posts:
            (content / "posts" / f"{pid(written)}.md").write_text(text, encoding="utf-8")
        yield root


def run_build(root):
    return subprocess.run([sys.executable, str(BUILD)], cwd=root, capture_output=True, text=True)


def read(root, relative):
    return (root / "docs" / relative).read_text(encoding="utf-8")


def feed_items(feed):
    return re.findall(r'(?s)<article class="feed-item">(.*?)</article>', feed)


def item_of(feed, post_id):
    return next(item for item in feed_items(feed) if f'p/{post_id}/' in item)


SITE = [
    (SHORT_AT, post_text(SHORT_AT, body="짧은 글의 **본문 전체**가 나온다.\n둘째 줄도 나온다.")),
    (MEDIUM_AT, post_text(MEDIUM_AT, "medium", title="중간 글 제목", body="중간 글 본문은 피드에 나오지 않는다")),
    (UNTITLED_AT, post_text(UNTITLED_AT, "long", body="제목 없는 긴 글의 첫 문단")),
]


class FeedLayoutContractTests(unittest.TestCase):
    def build(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        return read(root, "index.html")

    def test_each_post_is_its_own_box(self):
        with temporary_site(SITE) as root:
            feed = self.build(root)
            self.assertEqual(len(feed_items(feed)), 3)

    def test_a_short_post_has_no_title_line_and_shows_its_whole_body(self):
        with temporary_site(SITE) as root:
            item = item_of(self.build(root), pid(SHORT_AT))
            self.assertNotIn("feed-title", item)
            self.assertNotIn(f">{pid(SHORT_AT)}<", item, msg="the id is never shown as a title")
            self.assertIn("<strong>본문 전체</strong>", item)
            self.assertIn("둘째 줄도 나온다.", item)
            self.assertNotIn("…", item)

    def test_a_title_comes_first_in_bold_and_links_to_the_post(self):
        with temporary_site(SITE) as root:
            item = item_of(self.build(root), pid(MEDIUM_AT))
            title = re.search(r'(?s)<h2 class="feed-title"><a href="p/%s/">(.*?)</a></h2>' % pid(MEDIUM_AT), item)
            self.assertIsNotNone(title, msg=item)
            self.assertEqual(title.group(1), "중간 글 제목")
            self.assertLess(item.index("feed-title"), item.index("item-footer"))
            self.assertNotIn("중간 글 본문은 피드에 나오지 않는다", item)

    def test_an_untitled_medium_or_long_post_keeps_its_80_characters_in_the_title_place(self):
        with temporary_site(SITE) as root:
            item = item_of(self.build(root), pid(UNTITLED_AT))
            self.assertRegex(item, r'<h2 class="feed-title"><a href="p/%s/">제목 없는 긴 글의 첫 문단</a></h2>' % pid(UNTITLED_AT))

    def test_the_footer_at_the_bottom_has_the_type_and_the_time_linking_to_the_post(self):
        with temporary_site(SITE) as root:
            feed = self.build(root)
            for written, type_name in ((SHORT_AT, "짧은 글"), (MEDIUM_AT, "중간 글"), (UNTITLED_AT, "긴 글")):
                with self.subTest(post=pid(written)):
                    item = item_of(feed, pid(written))
                    footer = re.search(r'(?s)<footer class="item-footer">(.*?)</footer>', item)
                    self.assertIsNotNone(footer, msg=item)
                    self.assertTrue(item.rstrip().endswith("</footer>"), msg="the footer is the item's last part")
                    self.assertIn(type_name, footer.group(1))
                    self.assertRegex(footer.group(1), r'<a href="p/%s/"><time datetime="%s"' % (pid(written), written))

    def test_the_post_page_has_the_same_footer_under_its_body(self):
        with temporary_site(SITE) as root:
            self.build(root)
            page = read(root, f"p/{pid(SHORT_AT)}/index.html")
            footer = re.search(r'(?s)<footer class="item-footer">(.*?)</footer>', page)
            self.assertIsNotNone(footer, msg=page)
            self.assertIn("짧은 글", footer.group(1))
            self.assertIn(f'datetime="{SHORT_AT}"', footer.group(1))
            self.assertLess(page.index('<div class="body">'), page.index('<footer class="item-footer">'))

    def test_body_text_is_set_larger_for_reading(self):
        with temporary_site(SITE) as root:
            self.build(root)
            css = read(root, "assets/site.css")
            rule = re.search(r"(?s)(?:^|\})\s*body\s*\{(.*?)\}", css)
            self.assertIsNotNone(rule, msg=css)
            self.assertIn("font-size: 1.125rem", rule.group(1))


if __name__ == "__main__":
    unittest.main()
