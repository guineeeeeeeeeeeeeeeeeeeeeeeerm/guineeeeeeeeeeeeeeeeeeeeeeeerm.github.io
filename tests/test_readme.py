import json
import re
import tempfile
import unittest
from pathlib import Path
from support import ROOT, run_build


README = ROOT / "README.md"

FENCED_EXAMPLE = re.compile(
    r"(?ms)^```(?P<kind>post|link|patch|about|share|tag)[ \t]+(?P<path>content/[^\s`]+)[ \t]*\n"
    r"(?P<body>.*?)^```[ \t]*$"
)
FENCED_BLOCK = re.compile(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$")


def readme_text():
    return README.read_text(encoding="utf-8")


def section(text, heading):
    match = re.search(
        rf"(?ms)^##[ \t]+[^\n]*{re.escape(heading)}[^\n]*\n.*?(?=^##[ \t]+|\Z)",
        text,
    )
    return match.group(0) if match else ""


def examples_from(text):
    return [match.groupdict() for match in FENCED_EXAMPLE.finditer(text)]


class QReadmeContractTests(unittest.TestCase):
    def readme_or_fail(self):
        self.assertTrue(README.is_file(), "README.md must exist at the repository root")
        return readme_text()

    def test_Q_readme_exists_and_is_a_Korean_author_guide(self):
        text = self.readme_or_fail()
        outside_code = FENCED_BLOCK.sub("", text)
        letters = [character for character in outside_code if character.isalpha()]
        hangul = [character for character in letters if "가" <= character <= "힣"]

        self.assertIn("`post`", text)
        self.assertGreater(len(letters), 0)
        self.assertGreaterEqual(
            len(hangul) * 2,
            len(letters),
            "at least half of prose letters outside code fences must be Hangul",
        )

    def test_Q_readme_has_the_four_required_sections_and_covers_the_author_workflow(self):
        text = self.readme_or_fail()
        post = section(text, "새 글")
        link = section(text, "링크")
        patch = section(text, "패치")
        build = section(text, "빌드")
        tag = section(text, "태그")

        for name, content in {
            "새 글": post,
            "링크": link,
            "패치": patch,
            "빌드": build,
            "태그": tag,
        }.items():
            with self.subTest(section=name):
                self.assertTrue(content, f"README needs a ## section for {name}")

        self.assertIn("content/posts/", post)
        for field in ("written", "type", "title"):
            with self.subTest(post_header=field):
                self.assertRegex(post, rf"\b{field}\b")
        self.assertRegex(post, r"(?i)본문|마크다운|markdown")
        self.assertIn("이미지", post)
        self.assertRegex(post, r"!\[[^\]]*\]\([^)]*\)")

        self.assertIn("content/links.jsonl", link)   # the link table (Q-link)
        for field in ("link", "from", "to", "anchor", "action", "at", "why"):
            with self.subTest(link_field=field):
                self.assertRegex(link, rf"[\"'`]?{field}[\"'`]?\b")
        for action in ("created", "reason-changed", "removed"):
            with self.subTest(link_action=action):
                self.assertIn(action, link)
        self.assertRegex(link, r"사유|이유")

        self.assertIn("content/patches.jsonl", patch)   # the patch table (Q-patch)
        for field in ("id", "post", "at", "why", "op", "anchor", "text"):
            with self.subTest(patch_field=field):
                self.assertRegex(patch, rf"[\"'`]?{field}[\"'`]?\b")
        for operation in ("replace", "insert-before", "insert-after", "delete"):
            with self.subTest(patch_operation=operation):
                self.assertIn(operation, patch)

        for required in ("python3 build.py", "docs/", "stderr", "파일 경로", "한 줄"):
            with self.subTest(build_instruction=required):
                self.assertIn(required, build)

        self.assertIn("content/tags.jsonl", tag)   # the tag table (Q-tag)
        for field in ("post", "tag", "action", "at", "why", "added", "removed"):
            with self.subTest(tag_field=field):
                self.assertRegex(tag, rf"[\"'`]?{field}[\"'`]?\b")

    def test_Q_readme_fenced_post_link_and_patch_examples_build_and_render(self):
        text = self.readme_or_fail()
        examples = examples_from(text)
        by_kind = {kind: [] for kind in ("post", "link", "patch", "about", "share", "tag")}
        for example in examples:
            by_kind[example["kind"]].append(example)

        for kind in by_kind:
            with self.subTest(example_kind=kind):
                self.assertTrue(
                    by_kind[kind],
                    f"README must include a fenced {kind} example with its content path",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for example in examples:
                path = root / example["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(example["body"].lstrip("\n") + "\n", encoding="utf-8")
                for image in re.findall(r"!\[[^\]]*\]\((images/[^)]+)\)", example["body"]):
                    (root / "content" / image).parent.mkdir(parents=True, exist_ok=True)
                    (root / "content" / image).write_bytes(b"image")   # an example's image stands in as bytes

            result = run_build(root)
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
            )

            for example in by_kind["post"]:
                post_id = Path(example["path"]).stem
                document = root / "docs" / "p" / post_id / "index.html"
                with self.subTest(post=post_id):
                    self.assertTrue(document.is_file())
                    rendered = document.read_text(encoding="utf-8")
                    self.assertTrue(rendered.strip())
                    header, separator, body = example["body"].partition("\n\n")
                    title = re.search(r"(?m)^title:\s*(.+?)\s*$", header)
                    if title:
                        marker = title.group(1).strip(" '\"")
                    else:
                        words = re.findall(r"[A-Za-z0-9가-힣]{2,}", body if separator else header)
                        self.assertTrue(words, "the post example must contain visible text")
                        marker = words[0]
                    self.assertIn(marker, rendered)

            rows = lambda example: [json.loads(line) for line in example["body"].splitlines() if line.strip()]
            for example in by_kind["link"]:
                link = next(row for row in rows(example) if row.get("action") == "created")
                source_page = root / "docs" / "p" / link["from"] / "index.html"
                with self.subTest(link=link.get("link")):
                    self.assertTrue(source_page.is_file())
                    self.assertRegex(
                        source_page.read_text(encoding="utf-8"),
                        r"\[\d+\]",
                        "the rendered source post must carry the link marker",
                    )

            for example in by_kind["patch"]:
                for patch in rows(example):
                    post_page = root / "docs" / "p" / patch["post"] / "index.html"
                    with self.subTest(patch=patch.get("id")):
                        self.assertTrue(post_page.is_file())
                        document = post_page.read_text(encoding="utf-8")
                        if patch.get("op") != "delete":
                            self.assertTrue(patch.get("text"))
                            self.assertIn(patch["text"], document)

            for example in by_kind["tag"]:
                current = {}
                for row in rows(example):
                    current[(row["post"], row["tag"])] = row["action"]
                for (post_id, tag), action in current.items():
                    with self.subTest(tag=tag):
                        page = root / "docs" / "tags" / tag / "index.html"
                        if action == "added":
                            self.assertTrue(page.is_file())
                            self.assertIn(f"p/{post_id}/", page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
