import re
import unittest
from urllib.parse import quote

from support import pid, read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
OTHER_WRITTEN = "2024-02-03T04:05:07Z"
THIRD_WRITTEN = "2024-02-03T04:05:08Z"
UNTRANSLATED_WRITTEN = "2024-02-03T04:05:09Z"
ID = pid(WRITTEN)
OTHER_ID = pid(OTHER_WRITTEN)
THIRD_ID = pid(THIRD_WRITTEN)
UNTRANSLATED_ID = pid(UNTRANSLATED_WRITTEN)
TAG = "기록"


def post_text(written=WRITTEN, body="본문", post_type="short", title=None):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def translation_text(body="English body", title=None):
    lines = [] if title is None else [f"title: {title}"]
    return "\n".join(lines) + "\n\n" + body


def tag_row(post, tag=TAG, why="태그를 붙인 이유", at="2024-02-04T00:00:00Z"):
    return {"post": post, "tag": tag, "action": "added", "at": at, "why": why}


def patch_row(patch_id, post, anchor, text, at="2024-02-04T00:00:00Z", lang=None):
    row = {
        "id": patch_id,
        "post": post,
        "at": at,
        "why": "패치 이유",
        "op": "replace",
        "anchor": anchor,
        "text": text,
    }
    if lang is not None:
        row["lang"] = lang
    return row


def link_rows(link_id, from_id, to_id, anchor, events=()):
    rows = [
        {
            "link": link_id,
            "from": from_id,
            "to": to_id,
            "anchor": anchor,
            "action": "created",
            "at": WRITTEN,
            "why": "한국어 사유",
        }
    ]
    rows.extend({"link": link_id, **event} for event in events)
    return rows


def translated_event(anchor, why, at="2024-02-04T00:00:00Z"):
    return {
        "action": "translated",
        "lang": "en",
        "anchor": anchor,
        "why": why,
        "at": at,
    }


def reason_changed(why, at="2024-02-05T00:00:00Z"):
    return {"action": "reason-changed", "why": why, "at": at}


def nav(document):
    match = re.search(
        r'(?s)<header class="site-header">\s*<nav class="site-nav">(.*?)</nav>\s*</header>',
        document,
    )
    return match.group(1) if match else None


def tag_cloud(document):
    match = re.search(r'(?s)<aside class="tag-cloud">(.*?)</aside>', document)
    return match.group(1) if match else ""


def attrs(markup):
    return dict(re.findall(r'([:\w-]+)="([^"]*)"', markup))


def nav_anchors(document):
    markup = nav(document)
    return [
        (attrs(attributes), text)
        for attributes, text in re.findall(r'<a\b([^>]*)>([^<]*)</a>', markup or "")
    ]


def alternate_href(document, hreflang):
    for markup in re.findall(r'<link\b[^>]*>', document):
        values = attrs(markup)
        if values.get("rel") == "alternate" and values.get("hreflang") == hreflang:
            return values.get("href")
    return None


class I18nContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def assert_fails_at(self, root, path):
        result = run_build(root)
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        self.assertIn(path, result.stderr.replace("\\", "/"))

    def test_Q_ui_source_loc_03_keeps_korean_source_and_puts_english_under_a_separate_tree(self):
        posts = {f"posts/{ID}.md": post_text(body="한국 본문")}
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("English body")},
            about="소개 본문\n",
            about_en="About body\n",
        ) as root:
            self.assert_builds(root)
            korean_feed = read(root, "index.html")
            english_feed = read(root, "en/index.html")
            self.assertIn("한국 본문", korean_feed)
            self.assertNotIn("English body", korean_feed)
            self.assertIn("English body", english_feed)
            self.assertNotIn("한국 본문", english_feed)
            self.assertIn('<html lang="ko">', read(root, f"p/{ID}/index.html"))
            self.assertIn('<html lang="en">', read(root, f"en/p/{ID}/index.html"))

    def test_Q_i18n_addresses_create_the_feed_post_about_and_tag_outputs(self):
        with temporary_site(
            posts={f"posts/{ID}.md": post_text(body="원문")},
            translations={ID: translation_text("translated")},
            tags=[tag_row(ID)],
        ) as root:
            self.assert_builds(root)
            paths = (
                "en/index.html",
                f"en/p/{ID}/index.html",
                "en/about/index.html",
                f"en/tags/{TAG}/index.html",
            )
            for relative in paths:
                with self.subTest(path=relative):
                    output = root / "docs" / relative
                    self.assertTrue(output.is_file(), msg=relative)
                    self.assertIn('<html lang="en">', output.read_text(encoding="utf-8"))
            self.assertTrue((root / "docs" / "index.html").is_file())
            self.assertTrue((root / "docs" / f"p/{ID}/index.html").is_file())

    def test_Q_i18n_translation_allows_only_title_and_uses_the_original_written_and_type(self):
        with temporary_site(
            posts={
                f"posts/{ID}.md": post_text(
                    body="원문 본문", post_type="medium", title="한국 제목"
                )
            },
            translations={ID: translation_text("English body", title="English title")},
        ) as root:
            self.assert_builds(root)
            document = read(root, f"en/p/{ID}/index.html")
            self.assertIn("English title", document)
            self.assertIn("English body", document)
            self.assertNotIn("한국 제목", document)
            self.assertIn(f'datetime="{WRITTEN}"', document)
            self.assertIn("2024-02-03 04:05 UTC", document)

    def test_Q_i18n_translation_body_uses_post_markdown_and_image_rules(self):
        body = "# English heading\n\n**bold**\n\n![picture](images/picture.png)"
        with temporary_site(
            posts={f"posts/{ID}.md": post_text(body="한국 본문", post_type="medium")},
            translations={ID: translation_text(body)},
            images={"picture.png": b"picture"},
        ) as root:
            self.assert_builds(root)
            document = read(root, f"en/p/{ID}/index.html")
            self.assertIn("<h1>English heading</h1>", document)
            self.assertIn("<strong>bold</strong>", document)
            self.assertRegex(document, r'<img\b[^>]*src="\.\./\.\./images/picture\.png"')

    def test_Q_i18n_bad_translation_files_are_errors_naming_the_translation_or_about_file(self):
        cases = (
            (
                "short-title",
                {f"posts/{ID}.md": post_text(body="한국 본문")},
                {ID: translation_text("English body", title="forbidden")},
                "content/posts/" + ID + ".en.md",
                "About\n",
            ),
            (
                "orphan",
                {f"posts/{ID}.md": post_text(body="한국 본문")},
                {"20990101-000000": translation_text("orphan")},
                "content/posts/20990101-000000.en.md",
                "About\n",
            ),
            (
                "empty-body",
                {f"posts/{ID}.md": post_text(body="한국 본문")},
                {ID: "\n\n   \n"},
                "content/posts/" + ID + ".en.md",
                "About\n",
            ),
            (
                "other-header",
                {f"posts/{ID}.md": post_text(body="한국 본문")},
                {ID: "type: short\n\nEnglish body"},
                "content/posts/" + ID + ".en.md",
                "About\n",
            ),
            (
                "missing-about-translation",
                {f"posts/{ID}.md": post_text(body="한국 본문")},
                {ID: translation_text("English body")},
                "content/about.en.md",
                None,
            ),
        )
        for name, posts, translations, path, about_en in cases:
            with self.subTest(case=name), temporary_site(
                posts=posts, translations=translations, about_en=about_en
            ) as root:
                self.assert_fails_at(root, path)

    def test_Q_i18n_posts_without_translations_are_absent_from_english_feed_tags_and_cloud(self):
        posts = {
            f"posts/{ID}.md": post_text(body="translated source"),
            f"posts/{OTHER_ID}.md": post_text(OTHER_WRITTEN, body="한국에만 있는 글"),
        }
        tags = [tag_row(ID, tag="공통", why="공통 태그 이유"), tag_row(OTHER_ID, tag="한국만", why="한국만 태그 이유")]
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("translated source")},
            tags=tags,
        ) as root:
            self.assert_builds(root)
            feed = read(root, "en/index.html")
            self.assertIn("translated source", feed)
            self.assertNotIn("한국에만 있는 글", feed)
            self.assertNotRegex(feed, rf'href="p/{OTHER_ID}/"')
            self.assertIn("공통", tag_cloud(feed))
            self.assertNotIn("한국만", tag_cloud(feed))
            common_tag = read(root, "en/tags/공통/index.html")
            self.assertRegex(common_tag, rf'href="../../p/{ID}/"')
            self.assertNotRegex(common_tag, rf'href="../../p/{OTHER_ID}/"')
            self.assertFalse((root / "docs" / "en" / "tags" / "한국만").exists())

    def test_Q_i18n_english_pages_use_the_declared_english_screen_text(self):
        posts = {
            f"posts/{ID}.md": post_text(body="source anchor plus"),
            f"posts/{OTHER_ID}.md": post_text(
                OTHER_WRITTEN, body="target body", post_type="medium", title="Target"
            ),
        }
        links = {
            "translated": link_rows(
                "translated", ID, OTHER_ID, "source anchor", [translated_event("source anchor", "English reason")]
            )
        }
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("source anchor plus"), OTHER_ID: translation_text("target body", title="Target")},
            links=links,
            patches={"english": patch_row("english", ID, "plus", "patched", lang="en")},
            tags=[tag_row(OTHER_ID, tag="topic")],
        ) as root:
            self.assert_builds(root)
            feed = read(root, "en/index.html")
            source = read(root, f"en/p/{ID}/index.html")
            target = read(root, f"en/p/{OTHER_ID}/index.html")
            tag_page = read(root, "en/tags/topic/index.html")
            self.assertIn("Feed", feed)
            self.assertIn("About", feed)
            self.assertIn("Notes", source)
            self.assertIn("Linked from", target)
            self.assertIn("Show patches", source)
            self.assertIn("Tags", target)
            self.assertIn("Tag: topic", tag_page)
            self.assertIn('aria-label="View post"', feed)

    def test_Q_i18n_language_switch_is_last_in_nav_and_points_to_the_pair_or_english_feed(self):
        tag_path = quote(TAG, safe="")
        posts = {
            f"posts/{ID}.md": post_text(body="translated"),
            f"posts/{OTHER_ID}.md": post_text(OTHER_WRITTEN, body="not translated"),
        }
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("translated")},
            tags=[tag_row(ID), tag_row(OTHER_ID, tag="한국만")],
        ) as root:
            self.assert_builds(root)
            pages = (
                ("ko-feed", read(root, "index.html"), "English", "en/"),
                ("en-feed", read(root, "en/index.html"), "한국어", "../"),
                ("ko-about", read(root, "about/index.html"), "English", "../en/about/"),
                ("en-about", read(root, "en/about/index.html"), "한국어", "../../about/"),
                ("ko-translated-post", read(root, f"p/{ID}/index.html"), "English", f"../../en/p/{ID}/"),
                ("en-translated-post", read(root, f"en/p/{ID}/index.html"), "한국어", f"../../../p/{ID}/"),
                ("ko-untranslated-post", read(root, f"p/{OTHER_ID}/index.html"), "English", "../../en/"),
                ("ko-tag", read(root, f"tags/{TAG}/index.html"), "English", f"../../en/tags/{tag_path}/"),
                ("en-tag", read(root, f"en/tags/{TAG}/index.html"), "한국어", f"../../../tags/{tag_path}/"),
                ("ko-untranslated-tag", read(root, "tags/한국만/index.html"), "English", "../../en/"),
            )
            for name, document, label, href in pages:
                with self.subTest(page=name):
                    links = nav_anchors(document)
                    self.assertTrue(links, msg=document)
                    switch_attrs, switch_text = links[-1]
                    self.assertEqual(switch_attrs.get("class"), "lang-switch")
                    self.assertEqual(switch_attrs.get("href"), href)
                    self.assertEqual(switch_text, label)
                    self.assertEqual(switch_attrs.get("hreflang"), "en" if label == "English" else "ko")
                    self.assertEqual(switch_attrs.get("lang"), "en" if label == "English" else "ko")
            self.assertEqual(alternate_href(read(root, "index.html"), "en"), "en/")
            self.assertEqual(alternate_href(read(root, "en/index.html"), "ko"), "../")
            self.assertEqual(alternate_href(read(root, f"p/{ID}/index.html"), "en"), f"../../en/p/{ID}/")
            self.assertEqual(alternate_href(read(root, f"en/p/{ID}/index.html"), "ko"), f"../../../p/{ID}/")
            self.assertEqual(alternate_href(read(root, "about/index.html"), "en"), "../en/about/")
            self.assertEqual(alternate_href(read(root, "en/about/index.html"), "ko"), "../../about/")
            self.assertEqual(alternate_href(read(root, f"tags/{TAG}/index.html"), "en"), f"../../en/tags/{tag_path}/")
            self.assertEqual(alternate_href(read(root, f"en/tags/{TAG}/index.html"), "ko"), f"../../../tags/{tag_path}/")

    def test_Q_i18n_translated_link_uses_the_last_translated_anchor_and_reason(self):
        links = {
            "history": link_rows(
                "history",
                ID,
                OTHER_ID,
                "원본 앵커",
                [
                    translated_event("English anchor", "first English reason"),
                    reason_changed("later Korean reason"),
                    translated_event("English anchor", "last English reason", "2024-02-06T00:00:00Z"),
                ],
            )
        }
        posts = {
            f"posts/{ID}.md": post_text(body="원본 앵커"),
            f"posts/{OTHER_ID}.md": post_text(OTHER_WRITTEN, body="도착 글", post_type="medium", title="도착 제목"),
        }
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("English anchor"), OTHER_ID: translation_text("English target", title="English target title")},
            links=links,
        ) as root:
            self.assert_builds(root)
            document = read(root, f"en/p/{ID}/index.html")
            self.assertIn(f'<a href="../{OTHER_ID}/">English anchor</a>', document)
            self.assertIn("Notes", document)
            self.assertIn("last English reason", document)
            self.assertNotIn("first English reason", document)
            self.assertNotIn("later Korean reason", document)

    def test_Q_i18n_english_links_and_linked_from_filter_to_live_fully_translated_links_with_events(self):
        target = THIRD_ID
        posts = {
            f"posts/{ID}.md": post_text(body="A anchor hidden target"),
            f"posts/{OTHER_ID}.md": post_text(OTHER_WRITTEN, body="B anchor"),
            f"posts/{target}.md": post_text(THIRD_WRITTEN, body="target", post_type="medium", title="Target"),
            f"posts/{UNTRANSLATED_ID}.md": post_text(
                UNTRANSLATED_WRITTEN, body="only Korean source"
            ),
        }
        links = {
            "good": link_rows("good", ID, target, "A anchor", [translated_event("A anchor", "good reason")]),
            "no-translation-event": link_rows("no-translation-event", OTHER_ID, target, "B anchor"),
            "untranslated-target": link_rows(
                "untranslated-target",
                ID,
                UNTRANSLATED_ID,
                "hidden target",
                [translated_event("hidden target", "untranslated target reason")],
            ),
            "untranslated-source": link_rows(
                "untranslated-source",
                UNTRANSLATED_ID,
                target,
                "only Korean source",
                [translated_event("only Korean source", "untranslated source reason")],
            ),
        }
        with temporary_site(
            posts=posts,
            translations={
                ID: translation_text("A anchor hidden target"),
                OTHER_ID: translation_text("B anchor"),
                target: translation_text("English target", title="English target title"),
            },
            links=links,
        ) as root:
            self.assert_builds(root)
            source = read(root, f"en/p/{ID}/index.html")
            other = read(root, f"en/p/{OTHER_ID}/index.html")
            receiving = read(root, f"en/p/{target}/index.html")
            self.assertIn("good reason", source)
            self.assertNotIn("Notes", other)
            self.assertIn("Linked from", receiving)
            self.assertIn("good reason", receiving)
            self.assertNotIn("B anchor", receiving)
            self.assertNotIn("no-translation-event", receiving)
            self.assertNotIn("untranslated target reason", source)
            self.assertNotIn("untranslated source reason", receiving)

    def test_Q_i18n_translated_anchor_missing_or_repeated_names_the_translated_event_line(self):
        for body in ("English body", "English anchor English anchor"):
            with self.subTest(body=body):
                links = {
                    "bad": link_rows(
                        "bad", ID, OTHER_ID, "원본 앵커", [translated_event("English anchor", "why")]
                    )
                }
                with temporary_site(
                    posts={
                        f"posts/{ID}.md": post_text(body="원본 앵커"),
                        f"posts/{OTHER_ID}.md": post_text(OTHER_WRITTEN, body="target"),
                    },
                    translations={ID: translation_text(body), OTHER_ID: translation_text("target")},
                    links=links,
                ) as root:
                    self.assert_fails_at(root, "links.jsonl:2")

    def test_Q_i18n_language_patches_apply_only_to_the_matching_body_and_english_patch_view(self):
        posts = {f"posts/{ID}.md": post_text(body="한국 원문")}
        patches = {
            "korean": patch_row("korean", ID, "한국 원문", "한국 수정", at="2024-02-04T00:00:00Z"),
            "english": patch_row("english", ID, "English source", "English fixed", at="2024-02-05T00:00:00Z", lang="en"),
        }
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("English source")},
            patches=patches,
        ) as root:
            self.assert_builds(root)
            korean = read(root, f"p/{ID}/index.html")
            english = read(root, f"en/p/{ID}/index.html")
            self.assertIn("한국 수정", korean)
            self.assertNotIn("English fixed", korean)
            self.assertIn("English fixed", english)
            self.assertNotIn("한국 수정", english)
            self.assertIn("Show patches", english)
            script = "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", english, re.DOTALL))
            self.assertIn("english", script)
            self.assertNotIn("korean", script)

    def test_Q_i18n_english_patch_on_an_untranslated_post_is_a_build_error_naming_the_patch_row(self):
        with temporary_site(
            posts={f"posts/{ID}.md": post_text(body="한국 원문")},
            patches={"english": patch_row("english", ID, "한국 원문", "English", lang="en")},
        ) as root:
            self.assert_fails_at(root, "patches.jsonl:1")

    def test_Q_i18n_english_patch_anchor_rules_are_checked_against_the_translated_body(self):
        for anchor, body in (("missing", "English body"), ("English", "English English")):
            with self.subTest(anchor=anchor), temporary_site(
                posts={f"posts/{ID}.md": post_text(body="한국 원문")},
                translations={ID: translation_text(body)},
                patches={"english": patch_row("english", ID, anchor, "changed", lang="en")},
            ) as root:
                self.assert_fails_at(root, "patches.jsonl:1")

    def test_Q_i18n_english_tags_count_only_translated_posts_and_show_no_tag_reason(self):
        posts = {
            f"posts/{ID}.md": post_text(body="translated"),
            f"posts/{OTHER_ID}.md": post_text(OTHER_WRITTEN, body="Korean only"),
        }
        tags = [
            tag_row(ID, tag="shared", why="English tag reason"),
            tag_row(OTHER_ID, tag="shared", why="Korean tag reason"),
            tag_row(OTHER_ID, tag="korean-only", why="only Korean reason"),
        ]
        with temporary_site(
            posts=posts,
            translations={ID: translation_text("translated")},
            tags=tags,
        ) as root:
            self.assert_builds(root)
            feed = read(root, "en/index.html")
            self.assertRegex(tag_cloud(feed), r'>shared</a>\s*<span class="count">1</span>')
            self.assertNotIn("korean-only", tag_cloud(feed))
            shared = read(root, "en/tags/shared/index.html")
            self.assertIn("translated", shared)
            self.assertNotIn("Korean only", shared)
            self.assertNotIn("English tag reason", shared)
            self.assertNotIn("Korean tag reason", shared)
            self.assertFalse((root / "docs" / "en" / "tags" / "korean-only").exists())

    def test_Q_i18n_about_en_is_the_english_about_page_and_keeps_external_link_rules(self):
        with temporary_site(
            posts={f"posts/{ID}.md": post_text(body="post")},
            translations={ID: translation_text("post")},
            about="한국 소개\n",
            about_en="English **about**\n\n[site](https://example.com)\n",
        ) as root:
            self.assert_builds(root)
            document = read(root, "en/about/index.html")
            self.assertIn("English <strong>about</strong>", document)
            self.assertIn('<a href="https://example.com">site</a>', document)
            self.assertNotIn("한국 소개", document)

        with temporary_site(
            posts={f"posts/{ID}.md": post_text(body="post")},
            translations={ID: translation_text("post")},
            about_en="[bad](javascript:alert(1))\n",
        ) as root:
            self.assert_fails_at(root, "content/about.en.md")

    def test_Q_i18n_share_badges_are_present_on_english_feed_and_post_pages(self):
        shares = {
            "x": {
                "post": ID,
                "where": "x",
                "url": "https://x.com/someone/status/1",
                "at": "2024-02-04T00:00:00Z",
            }
        }
        with temporary_site(
            posts={f"posts/{ID}.md": post_text(body="post")},
            translations={ID: translation_text("post")},
            shares=shares,
        ) as root:
            self.assert_builds(root)
            feed = read(root, "en/index.html")
            post = read(root, f"en/p/{ID}/index.html")
            for document, source in ((feed, "../assets/brands/x.svg"), (post, "../../../assets/brands/x.svg")):
                with self.subTest(page="post" if document is post else "feed"):
                    badge = re.search(r'(?s)<a class="share-badge".*?</a>', document)
                    self.assertIsNotNone(badge, msg=document)
                    self.assertIn('href="https://x.com/someone/status/1"', badge.group(0))
                    self.assertIn(f'src="{source}"', badge.group(0))


if __name__ == "__main__":
    unittest.main()
