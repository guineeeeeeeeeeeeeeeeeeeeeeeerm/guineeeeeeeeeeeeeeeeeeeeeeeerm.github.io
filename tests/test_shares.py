import json
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
OTHER_AT, OTHER = "2024-02-03T04:05:07Z", "20240203-040507"


def post_text(written=WRITTEN, body="본문"):
    return f"written: {written}\ntype: short\n\n{body}"


def share(share_id, post=ID, where="x", url="https://x.com/someone/status/1", at="2024-02-04T00:00:00Z"):
    return {"id": share_id, "post": post, "where": where, "url": url, "at": at}


@contextmanager
def temporary_site(shares=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        (content / "posts").mkdir(parents=True)
        (content / "about.md").write_text("소개\n", encoding="utf-8")   # Q-about: every site has its about page
        (content / "posts" / f"{ID}.md").write_text(post_text(), encoding="utf-8")
        (content / "posts" / f"{OTHER}.md").write_text(post_text(OTHER_AT, "공유되지 않은 글"), encoding="utf-8")
        if shares is not None:
            (content / "shares").mkdir()
            for name, value in shares.items():
                path = content / "shares" / name
                path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")
        yield root


def run_build(root):
    return subprocess.run([sys.executable, str(BUILD)], cwd=root, capture_output=True, text=True)


def read(root, relative):
    return (root / "docs" / relative).read_text(encoding="utf-8")


def item_of(feed, post_id):
    return next(item for item in re.findall(r'(?s)<article class="feed-item">(.*?)</article>', feed) if f'p/{post_id}/' in item)


def badges(html):
    return re.findall(r'(?s)<a class="share-badge"[^>]*>.*?</a>', html)


class ShareContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def assert_fails_naming(self, root, name):
        result = run_build(root)
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, msg=result.stderr)
        self.assertIn(f"shares/{name}", lines[0].replace("\\", "/"))

    def test_without_shares_there_are_no_badges(self):
        with temporary_site() as root:
            self.assert_builds(root)
            self.assertEqual(badges(read(root, "index.html")), [])
            self.assertEqual(badges(read(root, f"p/{ID}/index.html")), [])

    def test_a_share_is_a_badge_linking_to_the_shared_post_in_the_feed_and_on_the_post_page(self):
        with temporary_site({"on-x.json": share("on-x")}) as root:
            self.assert_builds(root)
            for page in (item_of(read(root, "index.html"), ID), read(root, f"p/{ID}/index.html")):
                found = badges(page)
                self.assertEqual(len(found), 1, msg=page)
                self.assertIn('href="https://x.com/someone/status/1"', found[0])
                self.assertIn('aria-label="X"', found[0])
                self.assertIn("<svg", found[0], msg="an icon drawn in the site, not fetched")
                self.assertNotRegex(found[0], r'src="https?://')
                footer = re.search(r'(?s)<footer class="item-footer">(.*?)</footer>', page).group(1)
                self.assertIn(found[0], footer, msg="badges sit in the footer")
                self.assertRegex(read(root, "assets/site.css"), r"\.share-badge\s*\{[^}]*z-index", msg="a badge sits above the box's link")
            self.assertEqual(badges(item_of(read(root, "index.html"), OTHER)), [], msg="only the shared post has it")

    def test_the_first_places_are_x_threads_and_linkedin_in_share_time_order(self):
        shares = {
            "c.json": share("c", where="linkedin", url="https://www.linkedin.com/posts/1", at="2024-02-06T00:00:00Z"),
            "a.json": share("a", where="threads", url="https://www.threads.net/@someone/post/1", at="2024-02-05T00:00:00Z"),
            "b.json": share("b", where="x", url="https://x.com/someone/status/1", at="2024-02-04T00:00:00Z"),
        }
        with temporary_site(shares) as root:
            self.assert_builds(root)
            labels = [re.search(r'aria-label="([^"]+)"', b).group(1) for b in badges(read(root, f"p/{ID}/index.html"))]
            self.assertEqual(labels, ["X", "Threads", "LinkedIn"])

    def test_a_bad_share_file_is_a_build_error_naming_it(self):
        base = share("s")
        cases = {
            "not-json.json": "{ not json",
            "missing-url.json": {k: v for k, v in base.items() if k != "url"},
            "extra-key.json": {**base, "id": "extra-key", "extra": 1},
            "id-mismatch.json": {**base, "id": "different"},
            "no-such-post.json": {**base, "id": "no-such-post", "post": "20990101-000000"},
            "unknown-place.json": {**base, "id": "unknown-place", "where": "myspace"},
            "http-url.json": {**base, "id": "http-url", "url": "http://x.com/1"},
            "bad-at.json": {**base, "id": "bad-at", "at": "2024-02-04 00:00"},
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                with temporary_site({name: value}) as root:
                    self.assert_fails_naming(root, name)


if __name__ == "__main__":
    unittest.main()
