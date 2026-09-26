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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tags = [
            {
                "post": ID,
                "tag": "기록",
                "action": "added",
                "at": "2024-02-04T00:00:00Z",
                "why": "분류",
            }
        ]
        cls._common_site = temporary_site(
            {"about.md": "![설명](images/a.png)\n", f"posts/{ID}.md": post_text("본문")},
            images={"a.png": b"source"},
            tags=tags,
        )
        cls.common_root = cls._common_site.__enter__()
        result = run_build(cls.common_root)
        if result.returncode != 0:
            cls._common_site.__exit__(RuntimeError, RuntimeError(result.stderr), None)
            raise RuntimeError(f"shared image-zoom fixture failed to build: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._common_site.__exit__(None, None, None)
        super().tearDownClass()

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

            wrapped = re.findall(
                r'<a class="image-zoom" href="([^"]+)"><img ([^>]+)></a>',
                document,
            )
            self.assertEqual(len(wrapped), 2, msg=document)
            self.assertEqual([href for href, _ in wrapped], ["../../images/a.png"] * 2)
            first_image = next(attrs for _, attrs in wrapped if 'alt="설명"' in attrs)
            self.assertIn('src="../../images/a.png"', first_image)
            self.assertIn('alt="설명"', first_image)
            self.assertNotIn("width=", first_image)
            width_image = next(attrs for _, attrs in wrapped if 'alt="너비 그림"' in attrs)
            self.assertIn('src="../../images/a.png"', width_image)
            self.assertIn('alt="너비 그림"', width_image)
            self.assertIn('width="240"', width_image)

    def test_Q_post_image_on_the_about_page_uses_the_about_page_original(self):
        document = read(self.common_root, "about/index.html")
        wrapper = re.search(
            r'<a class="image-zoom" href="([^"]+)"><img ([^>]+)></a>',
            document,
        )
        self.assertIsNotNone(wrapper, msg=document)
        self.assertEqual(wrapper.group(1), "../images/a.png")
        self.assertIn('src="../images/a.png"', wrapper.group(2))
        self.assertIn('alt="설명"', wrapper.group(2))
        self.assertNotIn("width=", wrapper.group(2))

    def test_Q_post_zoom_script_is_on_post_and_about_pages_but_not_feed_or_tag_pages(self):
        post = read(self.common_root, f"p/{ID}/index.html")
        about = read(self.common_root, "about/index.html")
        feed = read(self.common_root, "index.html")
        tag = read(self.common_root, "tags/기록/index.html")

        for document, src in ((post, "../../assets/zoom.js"), (about, "../assets/zoom.js")):
            script = next(
                (
                    tag
                    for tag in re.findall(r"<script\b[^>]*>\s*</script>", document)
                    if f'src="{src}"' in tag
                ),
                None,
            )
            self.assertIsNotNone(script, msg=document)
            self.assertIn(f'src="{src}"', script)
            self.assertRegex(script, r"\bdefer(?:\s*=\s*[\"']?[^\s>\"']+[\"']?)?\b")
        self.assertNotIn("zoom.js", feed)
        self.assertNotIn("zoom.js", tag)

    def test_Q_post_short_post_image_in_the_feed_is_not_an_image_zoom_link(self):
        with temporary_site(
            {f"posts/{ID}.md": post_text("![피드 그림](images/a.png)", post_type="short", title=None)},
            images={"a.png": b"source"},
        ) as root:
            self.assert_builds(root)
            feed = read(root, "index.html")
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
            wrapper = re.search(
                r'<a class="image-zoom" href="([^"]+)"><img ([^>]+)></a>',
                document,
            )
            self.assertIsNotNone(wrapper, msg=document)
            self.assertEqual(wrapper.group(1), "../../images/a.png")
            self.assertIn('src="../../images/a.png"', wrapper.group(2))
            self.assertIn('alt="패치 그림"', wrapper.group(2))
            self.assertNotIn("width=", wrapper.group(2))


if __name__ == "__main__":
    unittest.main()
