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


def pid(written):
    """Q-post: a post's id — its file name — is the moment it was written, YYYYMMDD-HHMMSS (UTC)."""
    return written[0:4] + written[5:7] + written[8:10] + "-" + written[11:13] + written[14:16] + written[17:19]


# the posts these tests name, each written at its own moment (seconds apart, one minute), and its id
W = {name: "2024-02-03T04:05:%02dZ" % (6 + i) for i, name in enumerate(['from', 'to', 'one', 'two', 'from-a', 'from-b', 'from-c', 'from-removed', 'target', 'only', 'other'])}
I = {name: pid(w) for name, w in W.items()}


def post_text(post_type="short", written=WRITTEN, title=None, body="본문"):
    lines = [f"written: {written}", f"type: {post_type}"]
    if title is not None:
        lines.append(f"title: {title}")
    return "\n".join(lines) + "\n\n" + body


@contextmanager
def temporary_site(posts, links):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        content.mkdir()
        (content / "about.md").write_text("소개\n", encoding="utf-8")   # Q-about: every site has its about page

        for filename, text in posts.items():
            path = content / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        links_directory = content / "links"
        links_directory.mkdir()
        for filename, data in links.items():
            path = links_directory / filename
            if isinstance(data, str):
                path.write_text(data, encoding="utf-8")
            else:
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


def link_data(link_id, from_id, anchor, to_id, events):
    return {
        "id": link_id,
        "from": from_id,
        "anchor": anchor,
        "to": to_id,
        "events": events,
    }


def created(at, why):
    return {"at": at, "action": "created", "why": why}


def changed(at, why):
    return {"at": at, "action": "reason-changed", "why": why}


def removed(at, why):
    return {"at": at, "action": "removed", "why": why}


def page(root, post_id):
    return (root / "docs" / "p" / post_id / "index.html").read_text(encoding="utf-8")


class S2LinkContractTests(unittest.TestCase):
    def assert_build_succeeds(self, root):
        result = run_build(root)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return result

    def test_Q_link_file_shape_and_event_rules_are_validated(self):
        posts = {
            f"{I['from']}.md": post_text(body="anchor", written=W['from']),
            f"{I['to']}.md": post_text("medium", title="To", body="target", written=W['to']),
        }
        invalid_links = {
            "missing-id.json": {
                "from": I['from'],
                "anchor": "anchor",
                "to": I['to'],
                "events": [created(WRITTEN, "why")],
            },
            "missing-from.json": {
                "id": "missing-from",
                "anchor": "anchor",
                "to": I['to'],
                "events": [created(WRITTEN, "why")],
            },
            "missing-anchor.json": {
                "id": "missing-anchor",
                "from": I['from'],
                "to": I['to'],
                "events": [created(WRITTEN, "why")],
            },
            "missing-to.json": {
                "id": "missing-to",
                "from": I['from'],
                "anchor": "anchor",
                "events": [created(WRITTEN, "why")],
            },
            "missing-events.json": {
                "id": "missing-events",
                "from": I['from'],
                "anchor": "anchor",
                "to": I['to'],
            },
            "events-not-list.json": {
                "id": "events-not-list",
                "from": I['from'],
                "anchor": "anchor",
                "to": I['to'],
                "events": {"at": WRITTEN, "action": "created", "why": "why"},
            },
            "event-missing-at.json": link_data(
                "event-missing-at",
                I['from'],
                "anchor",
                I['to'],
                [{"action": "created", "why": "why"}],
            ),
            "event-missing-why.json": link_data(
                "event-missing-why",
                I['from'],
                "anchor",
                I['to'],
                [{"at": WRITTEN, "action": "created"}],
            ),
            "wrong-first-event.json": link_data(
                "wrong-first-event",
                I['from'],
                "anchor",
                I['to'],
                [changed("2024-02-03T04:05:06Z", "why")],
            ),
            "unknown-action.json": link_data(
                "unknown-action",
                I['from'],
                "anchor",
                I['to'],
                [
                    {
                        "at": "2024-02-03T04:05:06Z",
                        "action": "paused",
                        "why": "why",
                    }
                ],
            ),
            "non-utc-at.json": link_data(
                "non-utc-at",
                I['from'],
                "anchor",
                I['to'],
                [created("2024-02-03T13:05:06+09:00", "why")],
            ),
            "descending-time.json": link_data(
                "descending-time",
                I['from'],
                "anchor",
                I['to'],
                [
                    created("2024-02-03T04:05:07Z", "first"),
                    changed("2024-02-03T04:05:06Z", "second"),
                ],
            ),
        }

        for filename, link in invalid_links.items():
            with self.subTest(filename=filename), temporary_site(
                posts, {filename: link}
            ) as root:
                result = run_build(root)
                self.assertEqual(result.returncode, 1)
                self.assertIn(filename, result.stderr)

        with temporary_site(
            posts,
            {
                "valid.json": link_data(
                    "valid", I['from'], "anchor", I['to'], [created(WRITTEN, "why")]
                )
            },
        ) as root:
            self.assert_build_succeeds(root)

    def test_Q_link_current_reason_is_last_created_or_reason_changed_and_time_is_created_at(self):
        created_at = "2024-02-03T04:05:06Z"
        posts = {
            f"{I['from']}.md": post_text(body="source anchor", written=W['from']),
            f"{I['to']}.md": post_text("medium", title="Target", body="target", written=W['to']),
        }
        links = {
            "reason.json": link_data(
                "reason",
                I['from'],
                "anchor",
                I['to'],
                [
                    created(created_at, "initial reason"),
                    changed("2024-02-04T04:05:06Z", "current reason"),
                ],
            )
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, I['from'])
            self.assertIn("current reason", document)
            self.assertNotIn("initial reason", document)
            time_elements = re.findall(
                r"<time\b[^>]*>.*?</time>", document, flags=re.DOTALL
            )
            self.assertTrue(any(created_at in element for element in time_elements))

    def test_Q_link_removed_link_stays_in_content_but_is_not_rendered(self):
        posts = {
            f"{I['from']}.md": post_text(body="source anchor", written=W['from']),
            f"{I['to']}.md": post_text("medium", title="Target", body="target", written=W['to']),
        }
        links = {
            "removed.json": link_data(
                "removed",
                I['from'],
                "anchor",
                I['to'],
                [
                    created("2024-02-03T04:05:06Z", "should disappear"),
                    removed("2024-02-04T04:05:06Z", "no longer relevant"),
                ],
            )
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            self.assertTrue((root / "content" / "links" / "removed.json").is_file())
            self.assertNotIn(f'href="../{I["to"]}/"', page(root, I['from']))
            self.assertNotIn("should disappear", page(root, I['from']))
            self.assertNotIn("이 글을 가리키는 글", page(root, I['to']))

    def test_Q_link_anchor_missing_or_repeated_is_an_error_naming_the_link_file(self):
        posts = {
            f"{I['from']}.md": post_text(body="no link text here", written=W['from']),
            f"{I['to']}.md": post_text(body="target", written=W['to']),
        }
        for body in ("no link text here", "anchor appears anchor"):
            with self.subTest(body=body), temporary_site(
                {**posts, f"{I['from']}.md": post_text(body=body, written=W['from'])},
                {
                    "bad-anchor.json": link_data(
                        "bad-anchor", I['from'], "anchor", I['to'], [created(WRITTEN, "why")]
                    )
                },
            ) as root:
                result = run_build(root)
                self.assertEqual(result.returncode, 1)
                self.assertIn("bad-anchor.json", result.stderr)

        with temporary_site(
            {f"{I['from']}.md": post_text(body="anchor", written=W['from']), f"{I['to']}.md": post_text(body="target", written=W['to'])},
            {
                "valid.json": link_data(
                    "valid", I['from'], "anchor", I['to'], [created(WRITTEN, "why")]
                )
            },
        ) as root:
            self.assert_build_succeeds(root)

    def test_Q_link_anchor_links_to_to_post_and_superscripts_follow_appearance_order(self):
        posts = {
            f"{I['from']}.md": post_text(body="first anchor, then second anchor", written=W['from']),
            f"{I['one']}.md": post_text(body="one", written=W['one']),
            f"{I['two']}.md": post_text(body="two", written=W['two']),
        }
        links = {
            "first.json": link_data(
                "first", I['from'], "first", I['one'], [created(WRITTEN, "first why")]
            ),
            "second.json": link_data(
                "second",
                I['from'],
                "second",
                I['two'],
                [created("2024-02-04T04:05:06Z", "second why")],
            ),
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, I['from'])
            self.assertIn(
                f'<a href="../{I["one"]}/">first</a><sup><a href="#fn-1">[1]</a></sup>',
                document,
            )
            self.assertIn(
                f'<a href="../{I["two"]}/">second</a><sup><a href="#fn-2">[2]</a></sup>',
                document,
            )

    def test_Q_link_footnotes_are_an_ol_with_to_title_reason_created_time_and_ids(self):
        created_at = "2024-02-03T04:05:06Z"
        posts = {
            f"{I['from']}.md": post_text(body="source anchor", written=W['from']),
            f"{I['to']}.md": post_text("medium", title="Target title", body="target", written=W['to']),
        }
        links = {
            "note.json": link_data(
                "note", I['from'], "anchor", I['to'], [created(created_at, "because")]
            )
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, I['from'])
            self.assertIn("주석", document)
            self.assertIn("<ol", document)
            self.assertRegex(document, r'<li[^>]*id=["\']fn-1["\'][^>]*>')
            self.assertIn("Target title", document)
            self.assertIn("because", document)
            self.assertIn(created_at, document)

    def test_Q_link_footnote_uses_first_paragraph_80_character_standin_without_title(self):
        first_paragraph = "0123456789" * 10
        posts = {
            f"{I['from']}.md": post_text(body="source anchor", written=W['from']),
            f"{I['to']}.md": post_text(
                body=first_paragraph + "\n\nsecond paragraph must not be the stand-in"
            , written=W['to']),
        }
        links = {
            "standin.json": link_data(
                "standin", I['from'], "anchor", I['to'], [created(WRITTEN, "because")]
            )
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, I['from'])
            self.assertIn(first_paragraph[:80], document)
            self.assertNotIn(first_paragraph[:81], document)
            self.assertNotIn("second paragraph must not be the stand-in", document)

    def test_Q_link_receiving_page_lists_from_titles_and_current_reasons(self):
        posts = {
            f"{I['from-a']}.md": post_text("medium", title="From A", body="anchor-a", written=W['from-a']),
            f"{I['from-b']}.md": post_text("medium", title="From B", body="anchor-b", written=W['from-b']),
            f"{I['target']}.md": post_text("medium", title="Target", body="target", written=W['target']),
        }
        links = {
            "a.json": link_data(
                "a", I['from-a'], "anchor-a", I['target'], [created(WRITTEN, "reason A")]
            ),
            "b.json": link_data(
                "b",
                I['from-b'],
                "anchor-b",
                I['target'],
                [created("2024-02-04T04:05:06Z", "reason B")],
            ),
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, I['target'])
            self.assertIn("이 글을 가리키는 글", document)
            self.assertIn("From A", document)
            self.assertIn("reason A", document)
            self.assertIn("From B", document)
            self.assertIn("reason B", document)

    def test_Q_link_receiving_list_uses_fallback_and_created_time_desc_then_id_and_omits_removed(self):
        posts = {
            f"{I['from-a']}.md": post_text(body="A source stand-in", written=W['from-a']),
            f"{I['from-b']}.md": post_text(body="B source stand-in", written=W['from-b']),
            f"{I['from-c']}.md": post_text(body="C source stand-in", written=W['from-c']),
            f"{I['from-removed']}.md": post_text(body="removed source stand-in", written=W['from-removed']),
            f"{I['target']}.md": post_text(body="target", written=W['target']),
        }
        links = {
            "a.json": link_data(
                "a-link",
                I['from-a'],
                "stand-in",
                I['target'],
                [created("2024-02-03T04:05:06Z", "reason A")],
            ),
            "b.json": link_data(
                "b-link",
                I['from-b'],
                "stand-in",
                I['target'],
                [created("2024-02-03T04:05:06Z", "reason B")],
            ),
            "c.json": link_data(
                "c-link",
                I['from-c'],
                "stand-in",
                I['target'],
                [created("2024-02-04T04:05:06Z", "reason C")],
            ),
            "removed.json": link_data(
                "removed-link",
                I['from-removed'],
                "stand-in",
                I['target'],
                [
                    created("2024-02-05T04:05:06Z", "removed reason"),
                    removed("2024-02-06T04:05:06Z", "gone"),
                ],
            ),
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            document = page(root, I['target'])
            self.assertIn("A source stand-in", document)
            self.assertIn("B source stand-in", document)
            self.assertIn("C source stand-in", document)
            self.assertNotIn("removed source stand-in", document)
            self.assertIn("reason A", document)
            self.assertIn("reason B", document)
            self.assertIn("reason C", document)
            self.assertNotIn("removed reason", document)
            self.assertLess(document.index("C source stand-in"), document.index("A source stand-in"))
            self.assertLess(document.index("A source stand-in"), document.index("B source stand-in"))

    def test_Q_link_receiving_list_is_absent_when_no_link_points_to_the_post(self):
        posts = {
            f"{I['only']}.md": post_text(body="no incoming links", written=W['only']),
            f"{I['from']}.md": post_text(body="anchor", written=W['from']),
            f"{I['other']}.md": post_text(body="other", written=W['other']),
        }
        links = {
            "other.json": link_data(
                "other", I['from'], "anchor", I['other'], [created(WRITTEN, "other reason")]
            )
        }

        with temporary_site(posts, links) as root:
            self.assert_build_succeeds(root)
            self.assertNotIn("이 글을 가리키는 글", page(root, I['only']))

    def test_Q_link_unknown_from_or_to_is_a_build_error(self):
        cases = {
            "unknown-from.json": link_data(
                "unknown-from", "missing", "anchor", I['to'], [created(WRITTEN, "why")]
            ),
            "unknown-to.json": link_data(
                "unknown-to", I['from'], "anchor", "missing", [created(WRITTEN, "why")]
            ),
        }
        for filename, link in cases.items():
            with self.subTest(filename=filename), temporary_site(
                {
                    f"{I['from']}.md": post_text(body="anchor", written=W['from']),
                    f"{I['to']}.md": post_text(body="target", written=W['to']),
                },
                {filename: link},
            ) as root:
                result = run_build(root)
                self.assertEqual(result.returncode, 1)
                self.assertIn(filename, result.stderr)

        with temporary_site(
            {f"{I['from']}.md": post_text(body="anchor", written=W['from']), f"{I['to']}.md": post_text(body="target", written=W['to'])},
            {
                "valid.json": link_data(
                    "valid", I['from'], "anchor", I['to'], [created(WRITTEN, "why")]
                )
            },
        ) as root:
            self.assert_build_succeeds(root)


if __name__ == "__main__":
    unittest.main()
