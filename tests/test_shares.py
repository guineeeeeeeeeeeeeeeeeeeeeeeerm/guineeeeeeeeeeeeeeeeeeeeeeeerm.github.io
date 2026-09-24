import re
import unittest
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

KNOWN_PLACES = ("x", "threads", "linkedin")


def item_of(feed, post_id):
    return next(item for item in re.findall(r'(?s)<article class="feed-item">(.*?)</article>', feed) if f'p/{post_id}/' in item)


def badges(html):
    return re.findall(r'(?s)<a class="share-badge"[^>]*>.*?</a>', html)


class ShareContractTests(unittest.TestCase):
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
        with temporary_site(posts=SHARE_POSTS, shares={"on-x": share()}) as root:
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

    def test_Q_share_the_first_places_are_x_threads_and_linkedin_in_share_time_order(self):
        shares = {
            "linkedin": share(where="linkedin", url="https://www.linkedin.com/posts/1", at="2024-02-06T00:00:00Z"),
            "threads": share(where="threads", url="https://www.threads.net/@someone/post/1", at="2024-02-05T00:00:00Z"),
            "x": share(where="x", url="https://x.com/someone/status/1", at="2024-02-04T00:00:00Z"),
        }
        with temporary_site(posts=SHARE_POSTS, shares=shares) as root:
            self.assert_builds(root)
            labels = [re.search(r'aria-label="([^"]+)"', b).group(1) for b in badges(read(root, f"p/{ID}/index.html"))]
            self.assertEqual(labels, ["X", "Threads", "LinkedIn"])

    def test_Q_share_a_bad_share_row_is_a_build_error_naming_its_line(self):
        base = share()
        cases = {
            "not-json": "{ not json",
            "missing-url": {k: v for k, v in base.items() if k != "url"},
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

    def test_Q_share_Q_build_icons_svg_defines_each_known_share_symbol_once(self):
        with temporary_site(posts=SHARE_POSTS, shares={"on-x": share()}) as root:
            self.assert_builds(root)
            icons_path = root / "docs" / "assets" / "icons.svg"
            self.assertTrue(icons_path.is_file(), "the build must emit docs/assets/icons.svg")
            icons = icons_path.read_text(encoding="utf-8")

            for place in KNOWN_PLACES:
                symbols = re.findall(
                    rf'<symbol\b[^>]*\bid="share-{place}"[^>]*>', icons
                )
                self.assertEqual(len(symbols), 1, msg=place)
                symbol = re.search(
                    rf'<symbol\b[^>]*\bid="share-{place}"[^>]*>(.*?)</symbol>',
                    icons,
                    re.DOTALL,
                )
                self.assertIsNotNone(symbol, msg=place)
                self.assertRegex(symbol.group(1), r"currentColor", msg=place)

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
            expected = [
                "assets/icons.svg#share-x",
                "assets/icons.svg#share-threads",
                "assets/icons.svg#share-linkedin",
            ]

            self.assertEqual(
                re.findall(r'<use\b[^>]*\bhref="([^"]+)"', pages[0]),
                expected,
            )
            self.assertEqual(
                re.findall(r'<use\b[^>]*\bhref="([^"]+)"', pages[1]),
                [href.replace("assets/", "../../assets/", 1) for href in expected],
            )

    def test_Q_share_badge_markup_has_no_repeated_path_shape(self):
        shares = {
            "x": share(),
            "threads": share(
                where="threads",
                url="https://www.threads.net/@someone/post/1",
                at="2024-02-05T00:00:00Z",
            ),
        }
        with temporary_site(posts=SHARE_POSTS, shares=shares) as root:
            self.assert_builds(root)
            for page in (
                item_of(read(root, "index.html"), ID),
                read(root, f"p/{ID}/index.html"),
            ):
                found = badges(page)
                self.assertEqual(len(found), 2, msg=page)
                for badge in found:
                    self.assertNotIn("<path", badge.lower())
                    self.assertRegex(badge, r"<svg\b")
                    self.assertRegex(badge, r"<use\b[^>]*\bhref=")

if __name__ == "__main__":
    unittest.main()
