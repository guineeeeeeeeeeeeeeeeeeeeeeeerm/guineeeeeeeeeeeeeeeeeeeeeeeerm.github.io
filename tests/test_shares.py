import re
import unittest
from pathlib import Path
from support import read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
ID = "20240203-040506"   # Q-post: a post's id is the moment it was written (WRITTEN)
OTHER_AT, OTHER = "2024-02-03T04:05:07Z", "20240203-040507"


def post_text(written=WRITTEN, body="본문"):
    return f"written: {written}\ntype: short\n\n{body}"


def share(post=ID, where="x", url="https://x.com/someone/status/1", at="2024-02-04T00:00:00Z"):
    """One row of the share table (Q-share)."""
    return {"post": post, "where": where, "url": url, "at": at}


SHARE_POSTS = {
    f"posts/{ID}.md": post_text(),
    f"posts/{OTHER}.md": post_text(OTHER_AT, "공유되지 않은 글"),
}

BRAND_FILES = {
    "x": "x.svg",
    "threads": "threads.svg",
    "linkedin": "linkedin.png",
    "substack": "substack.png",
    "bluesky": "bluesky.svg",
    "devto": "devto.svg",
}


def item_of(feed, post_id):
    return next(item for item in re.findall(r'(?s)<article class="feed-item">(.*?)</article>', feed) if f'p/{post_id}/' in item)


def badges(html):
    return re.findall(r'(?s)<a class="share-badge"[^>]*>.*?</a>', html)


class ShareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._common_site = temporary_site(posts=SHARE_POSTS, shares={"on-x": share()})
        cls.common_root = cls._common_site.__enter__()
        result = run_build(cls.common_root)
        if result.returncode != 0:
            cls._common_site.__exit__(RuntimeError, RuntimeError(result.stderr), None)
            raise RuntimeError(f"shared share fixture failed to build: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._common_site.__exit__(None, None, None)
        super().tearDownClass()

    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def assert_fails_naming(self, root, line):
        result = run_build(root)
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        lines = [text for text in result.stderr.splitlines() if text.strip()]
        self.assertEqual(len(lines), 1, msg=result.stderr)
        self.assertIn(f"shares.jsonl:{line}", lines[0].replace("\\", "/"))

    def test_Q_share_without_shares_there_are_no_badges(self):
        with temporary_site(posts=SHARE_POSTS) as root:
            self.assert_builds(root)
            self.assertEqual(badges(read(root, "index.html")), [])
            self.assertEqual(badges(read(root, f"p/{ID}/index.html")), [])

    def test_Q_share_a_share_is_a_badge_linking_to_the_shared_post_in_the_feed_and_on_the_post_page(self):
        pages = (
            (item_of(read(self.common_root, "index.html"), ID), "assets/brands/x.svg"),
            (read(self.common_root, f"p/{ID}/index.html"), "../../assets/brands/x.svg"),
        )
        for page, expected_src in pages:
            found = badges(page)
            self.assertEqual(len(found), 1, msg=page)
            self.assertIn('href="https://x.com/someone/status/1"', found[0])
            self.assertIn('aria-label="X"', found[0])
            self.assertRegex(found[0], rf'<img\b[^>]*\bsrc="{re.escape(expected_src)}"')
            self.assertRegex(found[0], r'<img\b[^>]*\balt=""')
            self.assertNotRegex(found[0], r'\bsrc="https?://')
            self.assertNotRegex(found[0].lower(), r'<svg\b|<path\b')
            footer = re.search(r'(?s)<footer class="item-footer">(.*?)</footer>', page).group(1)
            self.assertIn(found[0], footer, msg="badges sit in the footer")
        self.assertEqual(badges(item_of(read(self.common_root, "index.html"), OTHER)), [], msg="only the shared post has it")

    def test_Q_share_equal_share_times_keep_share_file_line_order(self):
        shares = {
            "threads": share(
                where="threads",
                url="https://www.threads.net/@someone/post/1",
                at="2024-02-04T00:00:00Z",
            ),
            "x": share(at="2024-02-04T00:00:00Z"),
        }
        with temporary_site(posts=SHARE_POSTS, shares=shares) as root:
            self.assert_builds(root)
            labels = [re.search(r'aria-label="([^"]+)"', b).group(1) for b in badges(read(root, f"p/{ID}/index.html"))]
            self.assertEqual(labels, ["Threads", "X"])

    def test_Q_share_substack_is_known_and_uses_its_brand_badge(self):
        with temporary_site(
            posts=SHARE_POSTS,
            shares={
                "substack": share(
                    where="substack",
                    url="https://someone.substack.com/p/post",
                )
            },
        ) as root:
            self.assert_builds(root)
            for page, expected_src in (
                (item_of(read(root, "index.html"), ID), "assets/brands/substack.png"),
                (read(root, f"p/{ID}/index.html"), "../../assets/brands/substack.png"),
            ):
                found = badges(page)
                self.assertEqual(len(found), 1, msg=page)
                self.assertIn('aria-label="Substack"', found[0])
                self.assertRegex(found[0], rf'<img\b[^>]*\bsrc="{re.escape(expected_src)}"')
                self.assertRegex(found[0], r'<img\b[^>]*\balt=""')

    def test_Q_share_bluesky_is_known_and_uses_its_brand_badge(self):
        with temporary_site(
            posts=SHARE_POSTS,
            shares={
                "bluesky": share(
                    where="bluesky",
                    url="https://bsky.app/profile/someone/post/1",
                )
            },
        ) as root:
            self.assert_builds(root)
            for page, expected_src in (
                (item_of(read(root, "index.html"), ID), "assets/brands/bluesky.svg"),
                (read(root, f"p/{ID}/index.html"), "../../assets/brands/bluesky.svg"),
            ):
                found = badges(page)
                self.assertEqual(len(found), 1, msg=page)
                self.assertIn('aria-label="Bluesky"', found[0])
                self.assertRegex(found[0], rf'<img\b[^>]*\bsrc="{re.escape(expected_src)}"')
                self.assertRegex(found[0], r'<img\b[^>]*\balt=""')

    def test_Q_share_a_bad_share_row_is_a_build_error_naming_its_line(self):
        base = share()
        cases = {
            "not-json": "{ not json",
            "not-object": [base],
            "missing-post": {k: v for k, v in base.items() if k != "post"},
            "extra-key": {**base, "extra": 1},
            "no-such-post": {**base, "post": "20990101-000000"},
            "unknown-place": {**base, "where": "myspace"},
            "http-url": {**base, "url": "http://x.com/1"},
            "bad-at": {**base, "at": "2024-02-04 00:00"},
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                with temporary_site(posts=SHARE_POSTS, shares={"good": base, name: value}) as root:
                    self.assert_fails_naming(root, 2)

    def test_Q_share_Q_build_brand_logos_are_copied_byte_for_byte(self):
        source_dir = Path(__file__).resolve().parents[1] / "public" / "assets" / "brands"
        output_dir = self.common_root / "docs" / "assets" / "brands"
        for filename in BRAND_FILES.values():
            source = source_dir / filename
            output = output_dir / filename
            self.assertTrue(source.is_file(), msg=f"missing official source asset: {source}")
            self.assertTrue(output.is_file(), msg=f"missing copied asset: {output}")
            self.assertEqual(output.read_bytes(), source.read_bytes(), msg=filename)

    def test_Q_share_badges_use_icon_paths_relative_to_each_page(self):
        shares = {
            "linkedin": share(
                where="linkedin",
                url="https://www.linkedin.com/posts/1",
                at="2024-02-06T00:00:00Z",
            ),
            "threads": share(
                where="threads",
                url="https://www.threads.net/@someone/post/1",
                at="2024-02-05T00:00:00Z",
            ),
            "x": share(at="2024-02-04T00:00:00Z"),
        }
        with temporary_site(posts=SHARE_POSTS, shares=shares) as root:
            self.assert_builds(root)
            pages = (
                item_of(read(root, "index.html"), ID),
                read(root, f"p/{ID}/index.html"),
            )
            expected = ["assets/brands/x.svg", "assets/brands/threads.svg", "assets/brands/linkedin.png"]

            for page, prefix in zip(pages, ("", "../../")):
                found = badges(page)
                self.assertEqual(len(found), 3, msg=page)
                labels = [re.search(r'aria-label="([^"]+)"', badge).group(1) for badge in found]
                self.assertEqual(labels, ["X", "Threads", "LinkedIn"])
                actual = []
                for badge in found:
                    image = re.search(r'<img\b[^>]*>', badge)
                    self.assertIsNotNone(image, msg=badge)
                    self.assertRegex(image.group(0), r'\balt=""')
                    self.assertNotRegex(badge, r'\bsrc="https?://')
                    actual.append(re.search(r'\bsrc="([^"]+)"', image.group(0)).group(1))
                self.assertEqual(actual, [prefix + path for path in expected])

if __name__ == "__main__":
    unittest.main()
