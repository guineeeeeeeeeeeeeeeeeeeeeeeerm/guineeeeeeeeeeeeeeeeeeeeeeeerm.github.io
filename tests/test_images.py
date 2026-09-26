import re
import unittest
from support import read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
ID = "20240203-040506"   # Q-post: a post's id is the moment it was written (WRITTEN)


def post_text(body, post_type="short", title=None):
    lines = [f"written: {WRITTEN}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def img_tags(document):
    return re.findall(r"<img [^>]*>", document)


class ImageWidthContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def test_a_bar_not_followed_by_a_whole_number_stays_in_the_alt(self):
        for alt in ("a|b", "크기|넓게", "x|12px"):
            with self.subTest(alt=alt):
                with temporary_site({f"posts/{ID}.md": post_text(f"![{alt}](images/a.png)")}, images=("a.png",)) as root:
                    self.assert_builds(root)
                    tag = img_tags(read(root, f"p/{ID}/index.html"))[0]
                    self.assertNotIn("width=", tag)
                    self.assertIn(f'alt="{alt}"', tag)

    def test_a_zero_width_is_a_build_error_naming_the_post(self):
        with temporary_site({f"posts/{ID}.md": post_text("![그림|0](images/a.png)")}, images=("a.png",)) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn(f"content/posts/{ID}.md", result.stderr.replace("\\", "/"))

    def test_the_feed_uses_the_alt_without_the_width(self):
        body = "![그림 설명|200](images/a.png)"
        with temporary_site({f"posts/{ID}.md": post_text(body, post_type="medium")}, images=("a.png",)) as root:
            self.assert_builds(root)
            feed = read(root, "index.html")
            self.assertIn("그림 설명", feed)
            self.assertNotIn("그림 설명|200", feed)

    def test_the_about_page_takes_the_same_width(self):
        with temporary_site({"about.md": "![나|120](images/a.png)\n"}, images=("a.png",)) as root:
            self.assert_builds(root)
            tag = img_tags(read(root, "about/index.html"))[0]
            self.assertIn('width="120"', tag)
            self.assertIn('alt="나"', tag)


if __name__ == "__main__":
    unittest.main()
