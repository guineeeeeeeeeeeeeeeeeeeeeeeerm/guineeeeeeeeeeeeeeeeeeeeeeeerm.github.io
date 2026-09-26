import html
import re
import struct
import unittest
from pathlib import Path
from urllib.parse import quote

from support import pid, read, run_build, temporary_site


BASE = "https://guineeeeeeeeeeeeeeeeeeeeeeeerm.github.io"
SITE_NAME = "GuinEeeeeeeeeeeeeeeeeeeeeeeerm"
KO_DESCRIPTION = "생각난 것들을 쓰고, 만들고, 부숩니다."
EN_DESCRIPTION = "I write, build, and break whatever comes to mind."
WRITTEN = "2024-02-03T04:05:06Z"
UNTITLED_WRITTEN = "2024-02-03T04:05:07Z"
POST_ID = pid(WRITTEN)
UNTITLED_ID = pid(UNTITLED_WRITTEN)
TAG = "기록"
UNPAIRED_TAG = "한국만"


def post_text(written, body, post_type="medium", title=None):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def translation_text(body, title=None):
    header = [] if title is None else [f"title: {title}"]
    return "\n".join(header) + "\n\n" + body


def tag_row(post, tag_name):
    return {
        "post": post,
        "tag": tag_name,
        "action": "added",
        "at": "2024-02-04T00:00:00Z",
        "why": "분류 이유",
    }


def attrs(markup):
    return {
        key: html.unescape(value)
        for key, value in re.findall(r'([:\w-]+)="([^"]*)"', markup)
    }


def head(document):
    match = re.search(r"(?s)<head\b[^>]*>(.*?)</head>", document)
    if not match:
        raise AssertionError(f"document has no head: {document[:500]!r}")
    return match.group(1)


def links(document, rel):
    return [
        attrs(markup)
        for markup in re.findall(r"<link\b[^>]*>", head(document))
        if attrs(markup).get("rel") == rel
    ]


def meta_values(document, **wanted):
    values = []
    for markup in re.findall(r"<meta\b[^>]*>", head(document)):
        values_attrs = attrs(markup)
        if all(values_attrs.get(key) == value for key, value in wanted.items()):
            values.append(values_attrs.get("content"))
    return values


def one_meta(document, **wanted):
    values = meta_values(document, **wanted)
    if len(values) != 1:
        raise AssertionError(f"expected one meta {wanted}, got {values!r}")
    return values[0]


def png_dimensions(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError("asset is not a PNG with an IHDR chunk")
    return struct.unpack(">II", data[16:24])


class MetaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.applied_ko = "적용된 첫 문단 " + "가" * 180
        cls.english_first_paragraph = "Applied first paragraph " + "e" * 180
        cls.untitled_first_paragraph = "제목 없는 글의 첫 문단 " + "가" * 90
        cls._site = temporary_site(
            about="소개 본문\n",
            about_en="About body\n",
            posts={
                f"posts/{POST_ID}.md": post_text(
                    WRITTEN,
                    "원래 첫 문단\n\n둘째 문단",
                    title="한국 글 제목",
                ),
                f"posts/{UNTITLED_ID}.md": post_text(
                    UNTITLED_WRITTEN,
                    cls.untitled_first_paragraph + "\n\n둘째 문단",
                    post_type="long",
                ),
            },
            translations={
                POST_ID: translation_text(
                    cls.english_first_paragraph + "\n\nSecond paragraph",
                    title="English post title",
                )
            },
            patches={
                "meta": {
                    "id": "meta",
                    "post": POST_ID,
                    "at": "2024-02-04T00:00:00Z",
                    "why": "본문을 고침",
                    "op": "replace",
                    "anchor": "원래 첫 문단",
                    "text": cls.applied_ko,
                }
            },
            tags=[tag_row(POST_ID, TAG), tag_row(UNTITLED_ID, UNPAIRED_TAG)],
        )
        cls.root = cls._site.__enter__()
        result = run_build(cls.root)
        if result.returncode != 0:
            cls._site.__exit__(RuntimeError, RuntimeError(result.stderr), None)
            raise RuntimeError(f"shared metadata fixture failed to build: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._site.__exit__(None, None, None)
        super().tearDownClass()

    @classmethod
    def pages(cls):
        encoded_tag = quote(TAG, safe="")
        return {
            "ko_feed": {
                "path": "index.html",
                "asset_root": "",
                "url": BASE + "/",
                "locale": "ko_KR",
                "alternate": "en_US",
                "title": SITE_NAME,
                "description": KO_DESCRIPTION,
                "type": "website",
            },
            "en_feed": {
                "path": "en/index.html",
                "asset_root": "../",
                "url": BASE + "/en/",
                "locale": "en_US",
                "alternate": "ko_KR",
                "title": SITE_NAME,
                "description": EN_DESCRIPTION,
                "type": "website",
            },
            "ko_post": {
                "path": f"p/{POST_ID}/index.html",
                "asset_root": "../../",
                "url": BASE + f"/p/{POST_ID}/",
                "locale": "ko_KR",
                "alternate": "en_US",
                "title": "한국 글 제목",
                "description": cls.applied_ko[:160] + "…",
                "type": "article",
            },
            "en_post": {
                "path": f"en/p/{POST_ID}/index.html",
                "asset_root": "../../../",
                "url": BASE + f"/en/p/{POST_ID}/",
                "locale": "en_US",
                "alternate": "ko_KR",
                "title": "English post title",
                "description": cls.english_first_paragraph[:160] + "…",
                "type": "article",
            },
            "ko_untitled_post": {
                "path": f"p/{UNTITLED_ID}/index.html",
                "asset_root": "../../",
                "url": BASE + f"/p/{UNTITLED_ID}/",
                "locale": "ko_KR",
                "alternate": None,
                "title": cls.untitled_first_paragraph[:80] + "…",
                "description": cls.untitled_first_paragraph,
                "type": "article",
            },
            "ko_about": {
                "path": "about/index.html",
                "asset_root": "../",
                "url": BASE + "/about/",
                "locale": "ko_KR",
                "alternate": "en_US",
                "title": "소개",
                "description": KO_DESCRIPTION,
                "type": "website",
            },
            "en_about": {
                "path": "en/about/index.html",
                "asset_root": "../../",
                "url": BASE + "/en/about/",
                "locale": "en_US",
                "alternate": "ko_KR",
                "title": "About",
                "description": EN_DESCRIPTION,
                "type": "website",
            },
            "ko_tag": {
                "path": f"tags/{TAG}/index.html",
                "asset_root": "../../",
                "url": BASE + f"/tags/{encoded_tag}/",
                "locale": "ko_KR",
                "alternate": "en_US",
                "title": f"태그: {TAG}",
                "description": KO_DESCRIPTION,
                "type": "website",
            },
            "en_tag": {
                "path": f"en/tags/{TAG}/index.html",
                "asset_root": "../../../",
                "url": BASE + f"/en/tags/{encoded_tag}/",
                "locale": "en_US",
                "alternate": "ko_KR",
                "title": f"Tag: {TAG}",
                "description": EN_DESCRIPTION,
                "type": "website",
            },
            "ko_unpaired_tag": {
                "path": f"tags/{UNPAIRED_TAG}/index.html",
                "asset_root": "../../",
                "url": BASE + f"/tags/{quote(UNPAIRED_TAG, safe='')}/",
                "locale": "ko_KR",
                "alternate": None,
                "title": f"태그: {UNPAIRED_TAG}",
                "description": KO_DESCRIPTION,
                "type": "website",
            },
        }

    def document(self, page):
        return read(self.root, self.pages()[page]["path"])

    def test_Q_meta_all_pages_have_relative_favicon_links_and_folder_canonical_urls(self):
        for name, expected in self.pages().items():
            with self.subTest(page=name):
                document = self.document(name)
                icon = links(document, "icon")
                self.assertEqual(len(icon), 1, msg=document)
                self.assertEqual(icon[0].get("type"), "image/png")
                self.assertEqual(icon[0].get("sizes"), "32x32")
                self.assertEqual(icon[0].get("href"), expected["asset_root"] + "assets/favicon-32.png")
                apple = links(document, "apple-touch-icon")
                self.assertEqual(len(apple), 1, msg=document)
                self.assertEqual(apple[0].get("href"), expected["asset_root"] + "assets/apple-touch-icon.png")
                self.assertEqual(one_meta(document, property="og:url"), expected["url"])
                canonical = links(document, "canonical")
                self.assertEqual(len(canonical), 1, msg=document)
                self.assertEqual(canonical[0].get("href"), expected["url"])
                self.assertEqual(canonical[0].get("href"), one_meta(document, property="og:url"))

    def test_Q_meta_every_page_has_the_shared_site_name_image_dimensions_alt_and_twitter_card(self):
        image_url = BASE + "/assets/og-default.png"
        for name in self.pages():
            with self.subTest(page=name):
                document = self.document(name)
                self.assertEqual(one_meta(document, property="og:site_name"), SITE_NAME)
                self.assertEqual(one_meta(document, property="og:image"), image_url)
                self.assertEqual(one_meta(document, property="og:image:width"), "1200")
                self.assertEqual(one_meta(document, property="og:image:height"), "630")
                self.assertEqual(one_meta(document, property="og:image:alt"), SITE_NAME)
                self.assertEqual(one_meta(document, name="twitter:card"), "summary_large_image")

    def test_Q_meta_page_type_and_titles_are_specific_without_a_site_suffix_in_og_title(self):
        for name, expected in self.pages().items():
            with self.subTest(page=name):
                document = self.document(name)
                page_title = expected["title"]
                tab_title = SITE_NAME if name.endswith("feed") else f"{page_title} — {SITE_NAME}"
                title = re.search(r"(?s)<title>(.*?)</title>", document)
                self.assertIsNotNone(title, msg=document)
                self.assertEqual(title.group(1), tab_title)
                self.assertEqual(one_meta(document, property="og:title"), page_title)
                self.assertEqual(one_meta(document, property="og:type"), expected["type"])

    def test_Q_meta_descriptions_use_the_applied_post_first_paragraph_and_language_site_sentences(self):
        for name, expected in self.pages().items():
            with self.subTest(page=name):
                document = self.document(name)
                self.assertEqual(one_meta(document, name="description"), expected["description"])
                self.assertEqual(one_meta(document, property="og:description"), expected["description"])

    def test_Q_meta_locales_have_an_alternate_only_when_the_page_has_a_pair(self):
        for name, expected in self.pages().items():
            with self.subTest(page=name):
                document = self.document(name)
                self.assertEqual(one_meta(document, property="og:locale"), expected["locale"])
                alternates = meta_values(document, property="og:locale:alternate")
                if expected["alternate"] is None:
                    self.assertEqual(alternates, [])
                else:
                    self.assertEqual(alternates, [expected["alternate"]])

    def test_Q_meta_public_preview_images_are_copied_byte_for_byte_with_declared_dimensions(self):
        project_root = Path(__file__).resolve().parents[1]
        expected = {
            "favicon-32.png": (32, 32),
            "apple-touch-icon.png": (180, 180),
            "og-default.png": (1200, 630),
        }
        for filename, dimensions in expected.items():
            with self.subTest(asset=filename):
                source = (project_root / "public" / "assets" / filename).read_bytes()
                copied = (self.root / "docs" / "assets" / filename).read_bytes()
                self.assertEqual(png_dimensions(source), dimensions)
                self.assertEqual(png_dimensions(copied), dimensions)
                self.assertEqual(copied, source)


if __name__ == "__main__":
    unittest.main()
