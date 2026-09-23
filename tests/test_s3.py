import json
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


BUILD = Path(__file__).resolve().parents[1] / "build.py"
WRITTEN = "2024-02-03T04:05:06Z"


def post_text(post_type="short", written=WRITTEN, title=None, body="본문"):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


def patch_data(
    patch_id,
    post,
    anchor,
    op="replace",
    text="",
    at=WRITTEN,
    why="고친 이유",
):
    data = {
        "id": patch_id,
        "post": post,
        "at": at,
        "why": why,
        "op": op,
        "anchor": anchor,
    }
    if op != "delete":
        data["text"] = text
    return data


def link_data(link_id, from_id, anchor, to_id):
    return {
        "id": link_id,
        "from": from_id,
        "anchor": anchor,
        "to": to_id,
        "events": [{"at": WRITTEN, "action": "created", "why": "연결 이유"}],
    }


@contextmanager
def temporary_site(posts, patches=None, links=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        content.mkdir()

        for filename, text in posts.items():
            path = content / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        for filename, data in (patches or {}).items():
            path = content / "patches" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, str):
                path.write_text(data, encoding="utf-8")
            else:
                path.write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )

        if links:
            links_directory = content / "links"
            links_directory.mkdir()
            for filename, data in links.items():
                path = links_directory / filename
                path.write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )

        yield root


def run_build(root):
    return subprocess.run(
        [sys.executable, str(BUILD)],
        cwd=root,
        capture_output=True,
        text=True,
    )


def page(root, post_id):
    return (root / "docs" / "p" / f"{post_id}.html").read_text(encoding="utf-8")


def patch_script_source(document):
    scripts = re.findall(
        r"<script\b[^>]*>(.*?)</script>", document, flags=re.IGNORECASE | re.DOTALL
    )
    return "\n".join(scripts)


class S3PatchContractTests(unittest.TestCase):
    def assert_build_succeeds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def assert_bad_patch(self, filename, value, posts=None):
        with temporary_site(
            posts or {"post.md": post_text(body="anchor")},
            patches={filename: value},
        ) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(result.stderr.strip().splitlines()), 1)
            self.assertIn(f"patches/{filename}", result.stderr)

    def test_Q_patch_file_shape_and_validation_errors_name_the_patch_file(self):
        base = patch_data("valid", "post", "anchor", text="changed")
        with temporary_site({"post.md": post_text(body="anchor")}, {"valid.json": base}) as root:
            self.assert_build_succeeds(root)

        invalid = {
            "not-json.json": "{" + "not json",
            "missing-id.json": {key: value for key, value in base.items() if key != "id"},
            "extra-key.json": {**base, "extra": True},
            "id-not-string.json": {**base, "id": 7},
            "id-does-not-match.json": {**base, "id": "different"},
            "bad-op.json": {**base, "op": "append"},
            "delete-has-text.json": {**base, "op": "delete", "text": "forbidden"},
            "replace-missing-text.json": {key: value for key, value in base.items() if key != "text"},
            "bad-at.json": {**base, "at": "2024-02-03 04:05:06+00:00"},
            "missing-post.json": {**base, "post": "does-not-exist"},
        }
        for filename, value in invalid.items():
            with self.subTest(filename=filename):
                self.assert_bad_patch(filename, value)

    def test_Q_patch_applies_replace_insert_before_insert_after_and_delete_in_at_then_id_order(self):
        posts = {
            "target.md": post_text(body="alpha beta gamma"),
            "other.md": post_text(body="other post stays unchanged"),
        }
        patches = {
            "01-replace.json": patch_data(
                "01-replace", "target", "alpha", text="created", why="첫 변경"
            ),
            "02-before.json": patch_data(
                "02-before", "target", "created", op="insert-before", text="before-", why="앞에 삽입"
            ),
            "03-after.json": patch_data(
                "03-after", "target", "created", op="insert-after", text="-after", why="뒤에 삽입"
            ),
            "04-delete.json": patch_data(
                "04-delete", "target", "beta", op="delete", why="삭제"
            ),
        }
        before_target = posts["target.md"].encode("utf-8")

        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            self.assertEqual((root / "content" / "target.md").read_bytes(), before_target)

            feed = (root / "docs" / "index.html").read_text(encoding="utf-8")
            target_page = page(root, "target")
            for document in (feed, target_page):
                self.assertIn("before-created-after", document)
                self.assertNotIn("alpha", document)
                self.assertNotIn("beta", document)
                self.assertIn("gamma", document)
            self.assertIn("other post stays unchanged", page(root, "other"))

    def test_Q_patch_same_at_uses_string_id_order_and_later_patch_may_anchor_text_earlier_patch_made(self):
        posts = {"post.md": post_text(body="seed")}
        patches = {
            "a-first.json": patch_data(
                "a-first", "post", "seed", text="made", at=WRITTEN
            ),
            "b-second.json": patch_data(
                "b-second", "post", "made", text="finished", at=WRITTEN
            ),
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            self.assertIn("finished", page(root, "post"))
            self.assertNotIn(">seed<", page(root, "post"))

    def test_Q_patch_sorts_by_at_before_id(self):
        posts = {"post.md": post_text(body="one")}
        patches = {
            # The ids deliberately sort opposite to their chronological order.
            "z-earlier.json": patch_data(
                "z-earlier", "post", "one", text="two", at="2024-02-03T04:05:06Z"
            ),
            "a-later.json": patch_data(
                "a-later", "post", "two", text="three", at="2024-02-04T04:05:06Z"
            ),
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            self.assertIn("three", page(root, "post"))

    def test_Q_patch_anchor_must_occur_exactly_once_in_the_current_post_body(self):
        with temporary_site(
            {"post.md": post_text(body="anchor")},
            {"valid.json": patch_data("valid", "post", "anchor", text="changed")},
        ) as root:
            # This control keeps a blanket "all patch files are unsupported"
            # failure from satisfying the invalid-anchor cases below.
            self.assert_build_succeeds(root)

        cases = {
            "missing.json": patch_data("missing", "post", "absent", text="x"),
            "repeated.json": patch_data("repeated", "post", "anchor", text="x"),
            "other-post.json": patch_data("other-post", "post", "only-in-other", text="x"),
        }
        for filename, patch in cases.items():
            posts = {"post.md": post_text(body="anchor anchor" if filename == "repeated.json" else "anchor")}
            if filename == "other-post.json":
                posts["other.md"] = post_text(body="only-in-other")
            with self.subTest(filename=filename):
                self.assert_bad_patch(filename, patch, posts=posts)

    def test_Q_patch_has_no_length_limit_and_is_scoped_to_one_post(self):
        long_text = "긴 글자" * 3000
        posts = {
            "target.md": post_text(body="target-anchor"),
            "other.md": post_text(body="other-anchor"),
        }
        patches = {
            "long.json": patch_data(
                "long", "target", "target-anchor", text=long_text
            )
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            self.assertIn(long_text, page(root, "target"))
            self.assertIn("other-anchor", page(root, "other"))

    def test_Q_patch_link_anchor_can_exist_only_after_the_patch(self):
        posts = {
            "source.md": post_text(body="old anchor"),
            "target.md": post_text("medium", title="Target", body="target body"),
        }
        patches = {
            "rename.json": patch_data(
                "rename", "source", "old anchor", text="new anchor"
            )
        }
        links = {
            "after-patch.json": link_data("after-patch", "source", "new anchor", "target")
        }
        with temporary_site(posts, patches, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, "source")
            self.assertIn("new anchor", document)
            self.assertRegex(document, r'href=["\']target\.html["\']')


class S3PatchViewContractTests(unittest.TestCase):
    def assert_build_succeeds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def test_Q_patch_view_toggle_exists_only_for_patched_posts_and_is_off_by_default(self):
        posts = {
            "patched.md": post_text(body="old text"),
            "plain.md": post_text(body="plain body"),
        }
        patches = {
            "one.json": patch_data("one", "patched", "old", text="new")
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            patched = page(root, "patched")
            plain = page(root, "plain")
            toggle = re.search(
                r"<button\b[^>]*>\s*패치 보기\s*</button>", patched, flags=re.DOTALL
            )
            self.assertIsNotNone(toggle)
            self.assertRegex(toggle.group(0), r'aria-pressed=["\']false["\']')
            self.assertNotIn("패치 보기", plain)
            self.assertIn("new text", patched)
            assets = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / "docs" / "assets").rglob("*")
                if path.is_file() and path.suffix in {".css", ".js"}
            )
            self.assertRegex(assets, r"aria-pressed|patch[-_]view")
            self.assertRegex(assets, r"outline")
            self.assertRegex(assets, r"(?:classList|toggle|pressed)")

    def test_Q_patch_view_exposes_regions_history_and_time_data_for_a_script(self):
        posts = {"post.md": post_text(body="old text")}
        patches = {
            "one.json": patch_data(
                "one", "post", "old", text="new", at="2024-02-04T05:06:07Z", why="정정 이유"
            )
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            document = page(root, "post")
            source = patch_script_source(document)
            for value in ["one", "replace", "old", "정정 이유"]:
                self.assertIn(value, source)
            self.assertRegex(source, r"(?:region|patch)[_-]?(?:history|data|id)")
            self.assertRegex(
                document,
                r'<time\b[^>]*datetime=["\']2024-02-04T05:06:07Z["\'][^>]*>'
                r"2024-02-04 05:06 UTC</time>",
            )
            self.assertIn("new", document)

    def test_Q_patch_view_marks_deletions_as_zero_width_regions_with_previous_text(self):
        posts = {"post.md": post_text(body="keep gone")}
        patches = {
            "remove.json": patch_data(
                "remove", "post", "gone", op="delete", at="2024-02-05T00:00:00Z", why="없앰"
            )
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            document = page(root, "post")
            source = patch_script_source(document)
            for value in ["remove", "delete", "gone", "없앰"]:
                self.assertIn(value, source)
            self.assertRegex(
                document,
                r"(?:patch[^>]*deleted|deleted[^>]*patch|data-[^=]*delete)",
            )
            self.assertIn("keep", document)

    def test_Q_patch_view_later_patch_shrinks_the_earlier_region_and_keeps_each_final_owner_history(self):
        # "old tail" -> one: "new text tail" -> two ("text" occurs once): "new changed tail"
        posts = {"post.md": post_text(body="old tail")}
        patches = {
            "one.json": patch_data(
                "one", "post", "old", text="new text", at="2024-02-04T00:00:00Z", why="첫 정정"
            ),
            "two.json": patch_data(
                "two", "post", "text", text="changed", at="2024-02-05T00:00:00Z", why="부분 정정"
            ),
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            document = page(root, "post")
            source = patch_script_source(document)
            self.assertIn("new changed", document)
            self.assertIn("one", source)
            self.assertIn("two", source)
            self.assertIn("new ", source)
            self.assertRegex(source, r"(?:new\s+|changed)")
            self.assertRegex(source, r"one.*two|two.*one")
            self.assertLess(source.index("2024-02-04T00:00:00Z"), source.index("2024-02-05T00:00:00Z"))

    def test_Q_patch_view_insert_history_has_no_previous_text(self):
        posts = {"post.md": post_text(body="anchor")}
        patches = {
            "insert.json": patch_data(
                "insert", "post", "anchor", op="insert-before", text="new ", why="추가 이유"
            )
        }
        with temporary_site(posts, patches) as root:
            self.assert_build_succeeds(root)
            document = page(root, "post")
            source = patch_script_source(document)
            self.assertIn("insert-before", source)
            self.assertIn("추가 이유", source)
            self.assertIn("새로 넣음", document)


if __name__ == "__main__":
    unittest.main()
