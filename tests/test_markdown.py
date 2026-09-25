import json
import re
import unittest
from pathlib import Path

from support import page, pid, run_build, temporary_site


WRITTEN = "2024-02-03T04:05:06Z"
POST_ID = pid(WRITTEN)
OTHER_WRITTEN = "2024-02-03T04:05:07Z"
OTHER_ID = pid(OTHER_WRITTEN)


def post_text(body, post_type="short", written=WRITTEN, title=None):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def link_row(anchor):
    return {
        "link": "inside-code",
        "from": POST_ID,
        "to": OTHER_ID,
        "anchor": anchor,
        "action": "created",
        "at": WRITTEN,
        "why": "코드 안 앵커 검사",
    }


def patch_row(anchor, text):
    return {
        "id": "partial-code",
        "post": POST_ID,
        "at": WRITTEN,
        "why": "코드 일부를 덮는 패치 검사",
        "op": "replace",
        "anchor": anchor,
        "text": text,
    }


class MarkdownContractTests(unittest.TestCase):
    def assert_builds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def test_Q_post_commonmark_blocks_and_gfm_extensions_render_on_the_post_page(self):
        body = (
            "# 첫 제목\n\n"
            "1. 첫째\n"
            "2. 둘째\n\n"
            "- 바깥\n"
            "  - 안쪽\n\n"
            "> - 인용 목록\n"
            "> - 인용 목록 둘째\n"
            ">\n"
            "> 인용 문단\n\n"
            "```html\n"
            "<b>펜스 코드</b>\n"
            "```\n\n"
            "    <b>들여쓴 코드</b>\n\n"
            "#### 넷\n"
            "##### 다섯\n"
            "###### 여섯\n\n"
            "***\n\n"
            "| 이름 | 값 |\n"
            "| --- | --- |\n"
            "| 가 | 나 |\n\n"
            "~~취소된 글자~~\n\n"
            "<b>굵게</b>"
        )
        with temporary_site({f"posts/{POST_ID}.md": post_text(body)}) as root:
            self.assert_builds(root)
            package = json.loads(
                (Path(__file__).resolve().parents[1] / "package.json").read_text(
                    encoding="utf-8"
                )
            )
            declared_dependencies = {
                **package.get("dependencies", {}),
                **package.get("devDependencies", {}),
            }
            self.assertIn("markdown-it", declared_dependencies)
            document = page(root, POST_ID)

            self.assertRegex(document, r"<ol\b[^>]*>.*?<li>첫째</li>.*?<li>둘째</li>", re.DOTALL)
            self.assertRegex(
                document,
                r"<ul\b[^>]*>.*?<li>바깥.*?<ul\b[^>]*>.*?<li>안쪽</li>",
                re.DOTALL,
            )
            quote = re.search(r"<blockquote\b[^>]*>(.*?)</blockquote>", document, re.DOTALL)
            self.assertIsNotNone(quote, msg=document)
            self.assertIn("<ul>", quote.group(1))
            self.assertIn("<li>인용 목록</li>", quote.group(1))
            self.assertIn("<p>인용 문단</p>", quote.group(1))

            self.assertRegex(
                document,
                r"<pre><code[^>]*>&lt;b&gt;펜스 코드&lt;/b&gt;\s*</code></pre>",
            )
            self.assertRegex(
                document,
                r"<pre><code[^>]*>&lt;b&gt;들여쓴 코드&lt;/b&gt;\s*</code></pre>",
            )
            for level, heading in ((4, "넷"), (5, "다섯"), (6, "여섯")):
                self.assertRegex(document, rf"<h{level}\b[^>]*>{heading}</h{level}>")
            self.assertRegex(document, r"<hr\b[^>]*>")
            self.assertRegex(
                document,
                r"<table\b.*?<th>이름</th>.*?<td>나</td>.*?</table>",
                re.DOTALL,
            )
            self.assertIn("<s>취소된 글자</s>", document)
            self.assertIn("&lt;b&gt;굵게&lt;/b&gt;", document)
            self.assertNotIn("<b>굵게</b>", document)

    def test_Q_post_plain_addresses_and_footnote_marks_stay_literal_while_gfm_tables_render(self):
        body = (
            "주소: https://example.com\n\n"
            "각주 표식: [^1]\n\n"
            "| 주소 |\n"
            "| --- |\n"
            "| https://example.com |"
        )
        with temporary_site({f"posts/{POST_ID}.md": post_text(body)}) as root:
            self.assert_builds(root)
            document = page(root, POST_ID)
            self.assertIn("https://example.com", document)
            self.assertIn("[^1]", document)
            self.assertNotIn('<a href="https://example.com">', document)
            self.assertNotIn('href="https://example.com"', document)
            self.assertNotIn('class="footnotes"', document)
            self.assertRegex(
                document,
                r"<table\b.*?<th>주소</th>.*?<td>https://example.com</td>.*?</table>",
                re.DOTALL,
            )

    def test_Q_post_reference_links_and_angle_links_render_as_http_anchors(self):
        body = (
            "[참조 글][r]\n\n"
            "[r]: https://example.com/r\n\n"
            "<https://example.com/a>"
        )
        with temporary_site({f"posts/{POST_ID}.md": post_text(body)}) as root:
            self.assert_builds(root)
            document = page(root, POST_ID)
            self.assertIn('<a href="https://example.com/r">참조 글</a>', document)
            self.assertIn(
                '<a href="https://example.com/a">https://example.com/a</a>',
                document,
            )

    def test_Q_post_non_http_reference_and_angle_links_are_build_errors_on_the_post_file(self):
        cases = (
            "[글자][r]\n\n[r]: mailto:me@example.com",
            "[글자][r]\n\n[r]: javascript:alert(1)",
            "<mailto:me@example.com>",
            "<javascript:alert(1)>",
        )
        for body in cases:
            with self.subTest(body=body):
                with temporary_site({f"posts/{POST_ID}.md": post_text(body)}) as root:
                    result = run_build(root)
                    self.assertEqual(result.returncode, 1, msg=result.stderr)
                    self.assertIn(
                        f"content/posts/{POST_ID}.md",
                        result.stderr.replace("\\", "/"),
                    )

    def test_Q_post_paragraph_and_quote_line_breaks_render_as_br_with_extended_markdown(self):
        body = (
            "문단 첫 줄\n"
            "문단 둘째 줄\n\n"
            "> - 인용 목록\n"
            ">\n"
            "> 인용 첫 줄\n"
            "> 인용 둘째 줄\n\n"
            "###### 끝 제목"
        )
        with temporary_site({f"posts/{POST_ID}.md": post_text(body)}) as root:
            self.assert_builds(root)
            document = page(root, POST_ID)
            self.assertRegex(document, r"문단 첫 줄<br>\s*문단 둘째 줄")
            self.assertRegex(document, r"인용 첫 줄<br>\s*인용 둘째 줄")
            self.assertIn("<li>인용 목록</li>", document)

    def test_Q_post_links_and_images_inside_inline_or_fenced_code_stay_literal(self):
        body = (
            "`[글자](https://example.com)` `![설명](images/none.png)`\n\n"
            "```\n"
            "[코드 링크](https://example.com)\n"
            "![코드 그림](images/none.png)\n"
            "```"
        )
        with temporary_site({f"posts/{POST_ID}.md": post_text(body)}) as root:
            self.assert_builds(root)
            document = page(root, POST_ID)
            self.assertIn("<code>[글자](https://example.com)</code>", document)
            self.assertIn("<code>![설명](images/none.png)</code>", document)
            self.assertIn(
                "[코드 링크](https://example.com)\n![코드 그림](images/none.png)",
                document,
            )
            self.assertNotIn('<a href="https://example.com">글자</a>', document)
            self.assertNotIn('<img src="../../images/none.png"', document)

    def test_Q_post_link_anchor_inside_inline_code_is_an_error_on_links_row(self):
        posts = {
            f"{POST_ID}.md": post_text("앞 `코드 앵커` 뒤"),
            f"{OTHER_ID}.md": post_text(
                "도착", post_type="medium", written=OTHER_WRITTEN, title="도착 글"
            ),
        }
        with temporary_site(
            posts,
            links={"inside-code": [link_row("코드 앵커")]},
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn("links.jsonl:1", result.stderr)

    def test_Q_post_patch_region_partly_inside_inline_code_is_an_error_on_patch_row(self):
        with temporary_site(
            {f"posts/{POST_ID}.md": post_text("앞 `코드` 뒤")},
            patches={"partial-code": patch_row("코드", "새")},
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn("patches.jsonl:1", result.stderr)

    def test_Q_post_images_inside_lists_and_tables_use_image_zoom_and_width(self):
        body = (
            "- ![목록 그림|120](images/a.png)\n\n"
            "| 표 그림 |\n"
            "| --- |\n"
            "| ![표 그림|120](images/a.png) |"
        )
        with temporary_site(
            {f"posts/{POST_ID}.md": post_text(body)}, images=("a.png",)
        ) as root:
            self.assert_builds(root)
            document = page(root, POST_ID)
            zoom_links = re.findall(
                r'<a class="image-zoom"[^>]*>.*?</a>', document, re.DOTALL
            )
            self.assertEqual(len(zoom_links), 2, msg=document)
            for zoom_link in zoom_links:
                self.assertIn('href="../../images/a.png"', zoom_link)
                self.assertIn('src="../../images/a.png"', zoom_link)
                self.assertIn('width="120"', zoom_link)
            self.assertRegex(
                document,
                r"<table\b.*?<a class=\"image-zoom\".*?</table>",
                re.DOTALL,
            )


if __name__ == "__main__":
    unittest.main()
