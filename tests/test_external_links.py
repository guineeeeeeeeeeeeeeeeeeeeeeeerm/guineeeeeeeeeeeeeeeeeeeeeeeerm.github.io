import re
import unittest

from support import page, pid, read, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
HTTP = "http://example.com/plain"
HTTPS = "https://example.com/secure"
POST_ID = pid(WRITTEN)


def post_text(written, post_type="short", title=None, body="본문"):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def patch_data(patch_id, post, anchor, op="replace", text="", at=WRITTEN):
    data = {
        "id": patch_id,
        "post": post,
        "at": at,
        "why": "외부 링크 계약 테스트",
        "op": op,
        "anchor": anchor,
    }
    if op != "delete":
        data["text"] = text
    return data


def link_row(link_id, from_id, anchor, to_id):
    return {
        "link": link_id,
        "from": from_id,
        "to": to_id,
        "anchor": anchor,
        "action": "created",
        "at": WRITTEN,
        "why": "외부 링크 안 겹침 테스트",
    }


class ExternalLinkContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def test_Q_post_http_and_https_links_render_in_every_post_type(self):
        posts = {}
        for offset, post_type in enumerate(("short", "medium", "long")):
            written = f"2024-02-03T04:05:{6 + offset:02d}Z"
            post_id = pid(written)
            posts[f"{post_id}.md"] = post_text(
                written,
                post_type,
                title=f"{post_type} 제목" if post_type != "short" else None,
                body=f"HTTP [HTTP 글자]({HTTP}) HTTPS [HTTPS 글자]({HTTPS})",
            )

        with temporary_site(posts) as root:
            self.assert_builds(root)
            for written in (
                "2024-02-03T04:05:06Z",
                "2024-02-03T04:05:07Z",
                "2024-02-03T04:05:08Z",
            ):
                with self.subTest(post=pid(written)):
                    document = page(root, pid(written))
                    self.assertIn(f'<a href="{HTTP}">HTTP 글자</a>', document)
                    self.assertIn(f'<a href="{HTTPS}">HTTPS 글자</a>', document)

    def test_Q_post_non_http_external_address_is_an_error_naming_the_post_file(self):
        for address in ("javascript:alert(1)", "p/hello.html", "mailto:me@example.com", ""):
            with self.subTest(address=address):
                with temporary_site(
                    {f"posts/{POST_ID}.md": post_text(WRITTEN, body=f"[여기]({address})")}
                ) as root:
                    result = run_build(root)
                    self.assertEqual(result.returncode, 1, msg=result.stderr)
                    self.assertIn(
                        f"content/posts/{POST_ID}.md",
                        result.stderr.replace("\\", "/"),
                    )

    def test_Q_post_untitled_medium_and_long_feed_titles_contain_only_the_link_text(self):
        for offset, post_type in enumerate(("medium", "long")):
            written = f"2024-02-03T04:05:{6 + offset:02d}Z"
            post_id = pid(written)
            with self.subTest(post_type=post_type):
                with temporary_site(
                    {
                        f"posts/{post_id}.md": post_text(
                            written,
                            post_type,
                            body=f"[글자]({HTTPS})",
                        )
                    }
                ) as root:
                    self.assert_builds(root)
                    feed = read(root, "index.html")
                    item = re.search(
                        rf'(?s)<article class="feed-item">.*?p/{post_id}/.*?</article>',
                        feed,
                    )
                    self.assertIsNotNone(item, msg=feed)
                    title = re.search(
                        r'<h2 class="feed-title">(.*?)</h2>', item.group(0)
                    )
                    self.assertIsNotNone(title, msg=item.group(0))
                    self.assertEqual(title.group(1), "글자")
                    self.assertNotIn(HTTPS, title.group(1))

    def test_Q_post_short_feed_external_link_is_outside_the_item_link(self):
        with temporary_site(
            {f"posts/{POST_ID}.md": post_text(WRITTEN, body=f"[글자]({HTTPS})")}
        ) as root:
            self.assert_builds(root)
            feed = read(root, "index.html")
            item = re.search(
                rf'(?s)<article class="feed-item">.*?p/{POST_ID}/.*?</article>',
                feed,
            )
            self.assertIsNotNone(item, msg=feed)
            item_html = item.group(0)
            external = f'<a href="{HTTPS}">글자</a>'
            self.assertIn(external, item_html)
            item_link = re.search(
                r'(?s)<a class="item-link"[^>]*>(.*?)</a>', item_html
            )
            self.assertIsNotNone(item_link, msg=item_html)
            self.assertNotIn(external, item_link.group(1))

    def test_Q_post_link_anchor_overlapping_an_external_link_is_an_error_on_created_row(self):
        for anchor in ("글", HTTPS):
            with self.subTest(anchor=anchor):
                posts = {
                    f"{POST_ID}.md": post_text(WRITTEN, body=f"[글자]({HTTPS})"),
                    "20240203-040507.md": post_text(
                        "2024-02-03T04:05:07Z", "medium", title="도착 글", body="도착"
                    ),
                }
                link = link_row("overlap", POST_ID, anchor, "20240203-040507")
                with temporary_site(posts, links={"overlap": [link]}) as root:
                    result = run_build(root)
                    self.assertEqual(result.returncode, 1, msg=result.stderr)
                    self.assertIn("links.jsonl:1", result.stderr)

    def test_Q_post_patch_insert_after_can_add_an_external_link_to_the_applied_body(self):
        patch = patch_data(
            "insert-link",
            POST_ID,
            "시작",
            op="insert-after",
            text=f" [글자]({HTTPS})",
        )
        with temporary_site(
            {f"posts/{POST_ID}.md": post_text(WRITTEN, body="시작 끝")},
            patches={"insert-link": patch},
        ) as root:
            self.assert_builds(root)
            self.assertIn(f'<a href="{HTTPS}">글자</a>', page(root, POST_ID))

    def test_Q_post_patch_view_partial_external_link_region_is_an_error_on_the_patch_row(self):
        patch = patch_data(
            "partial-link",
            POST_ID,
            "seed",
            text="[글자",
        )
        with temporary_site(
            {f"posts/{POST_ID}.md": post_text(WRITTEN, body=f"seed](" f"{HTTPS})")},
            patches={"partial-link": patch},
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn("patches.jsonl:1", result.stderr)


if __name__ == "__main__":
    unittest.main()
