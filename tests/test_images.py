import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


BUILD = Path(__file__).resolve().parents[1] / "build.py"
WRITTEN = "2024-02-03T04:05:06Z"
ID = "20240203-040506"   # Q-post: a post's id is the moment it was written (WRITTEN)


def post_text(body, post_type="short", title=None):
    lines = [f"written: {WRITTEN}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


@contextmanager
def temporary_site(files, images=("a.png",)):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        content.mkdir()
        (content / "about.md").write_text("소개\n", encoding="utf-8")   # Q-about: every site has its about page
        for relative, text in files.items():
            path = content / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for name in images:
            path = content / "images" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"image")
        yield root


def run_build(root):
    return subprocess.run([sys.executable, str(BUILD)], cwd=root, capture_output=True, text=True)


def read(root, relative):
    return (root / "docs" / relative).read_text(encoding="utf-8")


def img_tags(document):
    return re.findall(r"<img [^>]*>", document)


class ImageWidthContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def test_a_width_after_the_bar_sets_the_display_width_and_leaves_the_alt(self):
        with temporary_site({f"posts/{ID}.md": post_text("![작은 그림|160](images/a.png)")}) as root:
            self.assert_builds(root)
            tags = img_tags(read(root, f"p/{ID}/index.html"))
            self.assertEqual(len(tags), 1, msg=tags)
            self.assertIn('width="160"', tags[0])
            self.assertIn('alt="작은 그림"', tags[0])
            self.assertIn('src="../../images/a.png"', tags[0])

    def test_without_a_width_the_image_has_no_width_attribute(self):
        with temporary_site({f"posts/{ID}.md": post_text("![그림](images/a.png)")}) as root:
            self.assert_builds(root)
            tag = img_tags(read(root, f"p/{ID}/index.html"))[0]
            self.assertNotIn("width=", tag)
            self.assertIn('alt="그림"', tag)

    def test_a_bar_not_followed_by_a_whole_number_stays_in_the_alt(self):
        for alt in ("a|b", "크기|넓게", "x|12px"):
            with self.subTest(alt=alt):
                with temporary_site({f"posts/{ID}.md": post_text(f"![{alt}](images/a.png)")}) as root:
                    self.assert_builds(root)
                    tag = img_tags(read(root, f"p/{ID}/index.html"))[0]
                    self.assertNotIn("width=", tag)
                    self.assertIn(f'alt="{alt}"', tag)

    def test_a_zero_width_is_a_build_error_naming_the_post(self):
        with temporary_site({f"posts/{ID}.md": post_text("![그림|0](images/a.png)")}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn(f"content/posts/{ID}.md", result.stderr.replace("\\", "/"))

    def test_the_feed_uses_the_alt_without_the_width(self):
        body = "![그림 설명|200](images/a.png)"
        with temporary_site({f"posts/{ID}.md": post_text(body, post_type="medium")}) as root:
            self.assert_builds(root)
            feed = read(root, "index.html")
            self.assertIn("그림 설명", feed)
            self.assertNotIn("그림 설명|200", feed)

    def test_the_about_page_takes_the_same_width(self):
        with temporary_site({"about.md": "![나|120](images/a.png)\n"}) as root:
            self.assert_builds(root)
            tag = img_tags(read(root, "about/index.html"))[0]
            self.assertIn('width="120"', tag)
            self.assertIn('alt="나"', tag)


if __name__ == "__main__":
    unittest.main()
