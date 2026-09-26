import unittest
from support import run_build, temporary_site


def post_text(written, body="본문"):
    return f"written: {written}\ntype: short\n\n{body}"


class PostIdIsTheMomentItWasWrittenTests(unittest.TestCase):
    """Q-post: a post's id — its file name — is the moment it was written, YYYYMMDD-HHMMSS (UTC), the same instant as
    `written`. A title is metadata, not identity; the build keeps the rule, not a convention."""

    def assert_fails_naming(self, root, name):
        result = run_build(root)
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, msg=result.stderr)
        self.assertIn(f"content/posts/{name}", lines[0].replace("\\", "/"))

    def test_a_post_named_for_the_moment_it_was_written_builds_at_that_address(self):
        with temporary_site(post_files={"20260924-075921.md": post_text("2026-09-24T07:59:21Z")}) as root:
            result = run_build(root)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((root / "docs" / "p" / "20260924-075921" / "index.html").is_file())

    def test_a_name_that_is_not_a_moment_is_a_build_error(self):
        for name in ("hello.md", "20260924-0759.md"):
            with self.subTest(name=name):
                with temporary_site(post_files={name: post_text("2026-09-24T07:59:21Z")}) as root:
                    self.assert_fails_naming(root, name)

    def test_a_name_for_another_moment_than_written_is_a_build_error(self):
        for name in ("20260924-075922.md",):
            with self.subTest(name=name):
                with temporary_site(post_files={name: post_text("2026-09-24T07:59:21Z")}) as root:
                    self.assert_fails_naming(root, name)


if __name__ == "__main__":
    unittest.main()
