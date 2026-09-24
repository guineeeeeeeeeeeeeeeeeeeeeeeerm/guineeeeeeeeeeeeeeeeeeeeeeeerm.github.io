import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


BUILD = Path(__file__).resolve().parents[1] / "build.py"
WRITTEN = "2024-02-03T04:05:06Z"


def post_text(body, post_type="short", title=None):
    lines = [f"written: {WRITTEN}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


@contextmanager
def temporary_site(files):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        content.mkdir()
        (content / "about.md").write_text("소개\n", encoding="utf-8")   # Q-about: every site has its about page
        for relative, text in files.items():
            path = content / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        yield root


def run_build(root):
    return subprocess.run([sys.executable, str(BUILD)], cwd=root, capture_output=True, text=True)


def read(root, relative):
    return (root / "docs" / relative).read_text(encoding="utf-8")


def body_of(document):
    match = re.search(r'(?s)<div class="body">(.*?)</div>', document)
    return match.group(1) if match else ""


class LineBreakContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def test_a_line_break_inside_a_paragraph_is_a_line_break_on_the_page(self):
        with temporary_site({"posts/two.md": post_text("첫 줄\n둘째 줄")}) as root:
            self.assert_builds(root)
            body = body_of(read(root, "p/two/index.html"))
            self.assertRegex(body, r"<p>첫 줄<br>\s*둘째 줄</p>")

    def test_a_blank_line_still_separates_paragraphs(self):
        with temporary_site({"posts/two.md": post_text("첫 문단\n\n둘째 문단")}) as root:
            self.assert_builds(root)
            body = body_of(read(root, "p/two/index.html"))
            self.assertIn("<p>첫 문단</p>", body)
            self.assertIn("<p>둘째 문단</p>", body)
            self.assertNotIn("<br>", body)

    def test_a_line_break_inside_a_quote_is_a_line_break(self):
        with temporary_site({"posts/q.md": post_text("> 인용 첫 줄\n> 인용 둘째 줄")}) as root:
            self.assert_builds(root)
            body = body_of(read(root, "p/q/index.html"))
            self.assertRegex(body, r"<blockquote>인용 첫 줄<br>\s*인용 둘째 줄</blockquote>")

    def test_formatting_on_each_line_keeps_working(self):
        with temporary_site({"posts/f.md": post_text("**굵게** 첫 줄\n*기울임* 둘째 줄")}) as root:
            self.assert_builds(root)
            body = body_of(read(root, "p/f/index.html"))
            self.assertRegex(body, r"<strong>굵게</strong> 첫 줄<br>\s*<em>기울임</em> 둘째 줄")

    def test_the_feed_shows_a_short_posts_line_breaks_too(self):
        with temporary_site({"posts/two.md": post_text("첫 줄\n둘째 줄")}) as root:
            self.assert_builds(root)
            self.assertRegex(read(root, "index.html"), r"첫 줄<br>\s*둘째 줄")

    def test_the_about_page_takes_the_same_line_breaks(self):
        with temporary_site({"about.md": "안녕하세요.\n생각을 씁니다.\n"}) as root:
            self.assert_builds(root)
            self.assertRegex(read(root, "about/index.html"), r"안녕하세요\.<br>\s*생각을 씁니다\.")


if __name__ == "__main__":
    unittest.main()
