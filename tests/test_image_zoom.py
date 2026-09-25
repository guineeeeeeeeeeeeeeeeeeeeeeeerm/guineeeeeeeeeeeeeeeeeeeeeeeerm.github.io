import re
import unittest

from support import ROOT, pid, read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
ID = pid(WRITTEN)


def post_text(body, post_type="medium", title="제목"):
    lines = [f"written: {WRITTEN}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def patch_data(patch_id, post, anchor, text):
    return {
        "id": patch_id,
        "post": post,
        "at": "2024-02-04T00:00:00Z",
        "why": "그림 추가",
        "op": "replace",
        "anchor": anchor,
        "text": text,
    }


class ImageZoomContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")

    def test_Q_post_image_on_a_post_page_is_wrapped_and_keeps_the_original_and_width(self):
        body = "![설명](images/a.png)\n\n![너비 그림|240](images/a.png)"
        with temporary_site(
            {f"posts/{ID}.md": post_text(body)}, images={"a.png": b"source"}
        ) as root:
            self.assert_builds(root)
            document = read(root, f"p/{ID}/index.html")

            self.assertIn(
                '<a class="image-zoom" href="../../images/a.png">'
                '<img src="../../images/a.png" alt="설명"></a>',
                document,
            )
            wrapped = re.findall(
                r'<a class="image-zoom" href="([^"]+)"><img ([^>]+)></a>',
                document,
            )
            self.assertEqual(len(wrapped), 2, msg=document)
            self.assertEqual([href for href, _ in wrapped], ["../../images/a.png"] * 2)
            width_image = next(attrs for _, attrs in wrapped if 'alt="너비 그림"' in attrs)
            self.assertIn('src="../../images/a.png"', width_image)
            self.assertIn('width="240"', width_image)

    def test_Q_post_image_on_the_about_page_uses_the_about_page_original(self):
        with temporary_site(
            {"about.md": "![설명](images/a.png)\n"}, images={"a.png": b"source"}
        ) as root:
            self.assert_builds(root)
            document = read(root, "about/index.html")
            self.assertIn(
                '<a class="image-zoom" href="../images/a.png">'
                '<img src="../images/a.png" alt="설명"></a>',
                document,
            )

    def test_Q_post_zoom_script_is_on_post_and_about_pages_but_not_feed_or_tag_pages(self):
        tags = [
            {
                "post": ID,
                "tag": "기록",
                "action": "added",
                "at": "2024-02-04T00:00:00Z",
                "why": "분류",
            }
        ]
        with temporary_site(
            {"about.md": "소개\n", f"posts/{ID}.md": post_text("본문")}, tags=tags
        ) as root:
            self.assert_builds(root)
            post = read(root, f"p/{ID}/index.html")
            about = read(root, "about/index.html")
            feed = read(root, "index.html")
            tag = read(root, "tags/기록/index.html")

            self.assertIn('<script src="../../assets/zoom.js" defer></script>', post)
            self.assertIn('<script src="../assets/zoom.js" defer></script>', about)
            self.assertNotIn("zoom.js", feed)
            self.assertNotIn("zoom.js", tag)

    def test_Q_post_short_post_image_in_the_feed_is_not_an_image_zoom_link(self):
        with temporary_site(
            {f"posts/{ID}.md": post_text("![피드 그림](images/a.png)", post_type="short", title=None)},
            images={"a.png": b"source"},
        ) as root:
            self.assert_builds(root)
            feed = read(root, "index.html")
            self.assertIn('<img src="images/a.png" alt="피드 그림">', feed)
            self.assertNotIn('class="image-zoom"', feed)

    def test_Q_post_build_copies_zoom_asset_byte_for_byte(self):
        with temporary_site({f"posts/{ID}.md": post_text("본문")}) as root:
            self.assert_builds(root)
            source = ROOT / "public" / "assets" / "zoom.js"
            built = root / "docs" / "assets" / "zoom.js"
            self.assertTrue(source.is_file(), msg=f"missing source asset: {source}")
            self.assertTrue(built.is_file(), msg=f"missing built asset: {built}")
            self.assertEqual(built.read_bytes(), source.read_bytes())

    def test_Q_post_a_patch_added_image_is_wrapped_on_the_post_page(self):
        patch = patch_data(
            "add-image", ID, "그림 자리", "![패치 그림](images/a.png)"
        )
        with temporary_site(
            {f"posts/{ID}.md": post_text("그림 자리")},
            images={"a.png": b"source"},
            patches={"add-image": patch},
        ) as root:
            self.assert_builds(root)
            document = read(root, f"p/{ID}/index.html")
            self.assertIn(
                '<a class="image-zoom" href="../../images/a.png">'
                '<img src="../../images/a.png" alt="패치 그림"></a>',
                document,
            )


if __name__ == "__main__":
    unittest.main()
