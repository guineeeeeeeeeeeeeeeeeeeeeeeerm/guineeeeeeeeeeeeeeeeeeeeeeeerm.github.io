import re
import unittest
from urllib.parse import quote
from support import read, run_build, temporary_site


OLD_AT, NEW_AT = "2024-02-03T04:05:06Z", "2024-02-04T04:05:06Z"
OLD, NEW = "20240203-040506", "20240204-040506"   # Q-post: a post's id is the moment it was written


def post_text(written, body):
    return f"written: {written}\ntype: short\n\n{body}"


def tag(post, name, action="added", at="2024-02-05T00:00:00Z", why="이유"):
    """One row of the tag table (Q-tag)."""
    return {"post": post, "tag": name, "action": action, "at": at, "why": why}


TAG_POSTS = {
    f"posts/{OLD}.md": post_text(OLD_AT, "오래된 글"),
    f"posts/{NEW}.md": post_text(NEW_AT, "새 글"),
}


def cloud(feed):
    match = re.search(r'(?s)<aside class="tag-cloud">(.*?)</aside>', feed)
    return match.group(1) if match else None


def cloud_entries(feed):
    """(tag, count, font size) in the order shown."""
    return [(name, int(count), float(size)) for size, name, count in
            re.findall(r'<a class="tag" href="[^"]*" style="font-size: ([0-9.]+)rem">([^<]*)</a><span class="count">(\d+)</span>', cloud(feed) or "")]


class TagContractTests(unittest.TestCase):
    """Q-tag: tagging is an event with a time and a reason in the tag table; what is current is computed by the build."""

    def build(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def assert_fails_at(self, rows, line):
        with temporary_site(posts=TAG_POSTS, tags=rows) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn(f"tags.jsonl:{line}", result.stderr)

    def test_without_tags_there_is_no_cloud_and_no_tag_page(self):
        with temporary_site(posts=TAG_POSTS) as root:
            self.build(root)
            self.assertIsNone(cloud(read(root, "index.html")))
            self.assertFalse((root / "docs" / "tags").exists())
            self.assertNotIn('class="tags"', read(root, f"p/{OLD}/index.html"))

    def test_the_cloud_sits_beside_the_feed_and_counts_each_current_tag(self):
        rows = [tag(OLD, "기록"), tag(NEW, "기록"), tag(NEW, "AI")]
        with temporary_site(posts=TAG_POSTS, tags=rows) as root:
            self.build(root)
            feed = read(root, "index.html")
            self.assertRegex(feed, r'(?s)<div class="feed-layout">\s*<main>.*</main>\s*<aside class="tag-cloud">')
            entries = cloud_entries(feed)
            self.assertEqual([(name, count) for name, count, _ in entries], [("AI", 1), ("기록", 2)])
            sizes = dict((name, size) for name, _, size in entries)
            self.assertGreater(sizes["기록"], sizes["AI"], msg="more posts, larger")
            self.assertTrue(all(0.9 <= size <= 1.6 for size in sizes.values()))
            self.assertIn(f'href="tags/{quote("기록", safe="")}/"', cloud(feed))
            css = read(root, "assets/site.css")
            self.assertRegex(css, r"@media \(min-width: 64rem\)")
            self.assertRegex(css, r"\.feed-layout\s*\{[^}]*grid-template-columns")

    def test_a_tag_page_lists_its_posts_newest_first_with_why_the_tag_is_there(self):
        rows = [tag(OLD, "기록", why="처음 쓴 기록"), tag(NEW, "기록", at="2024-02-06T00:00:00Z", why="이어진 기록")]
        with temporary_site(posts=TAG_POSTS, tags=rows) as root:
            self.build(root)
            page = read(root, "tags/기록/index.html")
            self.assertIn("<title>태그: 기록</title>", page)
            self.assertLess(page.index(f"p/{NEW}/"), page.index(f"p/{OLD}/"))
            self.assertIn("처음 쓴 기록", page)
            self.assertIn("이어진 기록", page)
            self.assertIn('datetime="2024-02-06T00:00:00Z"', page)
            self.assertIn('href="../../p/', page, msg="links lead back to the site root")

    def test_the_post_page_links_its_current_tags(self):
        rows = [tag(NEW, "하네스"), tag(NEW, "AI")]
        with temporary_site(posts=TAG_POSTS, tags=rows) as root:
            self.build(root)
            tags = re.search(r'(?s)<div class="tags">(.*?)</div>', read(root, f"p/{NEW}/index.html"))
            self.assertIsNotNone(tags)
            hrefs = re.findall(r'<a class="tag" href="([^"]+)">([^<]+)</a>', tags.group(1))
            self.assertEqual([name for _, name in hrefs], ["AI", "하네스"])
            self.assertEqual(hrefs[1][0], f'../../tags/{quote("하네스", safe="")}/')

    def test_a_removed_tag_is_gone_from_pages_and_the_cloud_but_can_be_added_again(self):
        removed = [tag(NEW, "AI"), tag(NEW, "AI", "removed", at="2024-02-06T00:00:00Z", why="주제가 아님")]
        with temporary_site(posts=TAG_POSTS, tags=removed) as root:
            self.build(root)
            self.assertIsNone(cloud(read(root, "index.html")))
            self.assertFalse((root / "docs" / "tags" / "AI").exists())
            self.assertNotIn('class="tags"', read(root, f"p/{NEW}/index.html"))
        again = removed + [tag(NEW, "AI", at="2024-02-07T00:00:00Z", why="다시 보니 맞음")]
        with temporary_site(posts=TAG_POSTS, tags=again) as root:
            self.build(root)
            self.assertEqual([name for name, _, _ in cloud_entries(read(root, "index.html"))], ["AI"])
            self.assertIn("다시 보니 맞음", read(root, "tags/AI/index.html"))

    def test_bad_rows_are_build_errors_naming_the_line(self):
        good = tag(NEW, "AI")
        cases = {
            "not json": (["{ not json"], 1),
            "extra key": ([{**good, "extra": 1}], 1),
            "missing why": ([{k: v for k, v in good.items() if k != "why"}], 1),
            "unknown post": ([tag("20990101-000000", "AI")], 1),
            "unknown action": ([{**good, "action": "renamed"}], 1),
            "bad time": ([{**good, "at": "2024-02-05 00:00"}], 1),
            "removed first": ([tag(NEW, "AI", "removed")], 1),
            "added twice": ([good, {**good, "at": "2024-02-06T00:00:00Z"}], 2),
            "time goes back": ([good, tag(NEW, "AI", "removed", at="2024-02-04T00:00:00Z")], 2),
        }
        for name in ("", " AI", "AI ", "a/b", "a\\b", ".", "..", "가" * 41):
            cases[f"name {name!r}"] = ([tag(NEW, name)], 1)
        for case, (rows, line) in cases.items():
            with self.subTest(case=case):
                self.assert_fails_at(rows, line)


if __name__ == "__main__":
    unittest.main()
