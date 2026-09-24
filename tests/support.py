import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build.py"
DEFAULT_WRITTEN = "2024-02-03T04:05:06Z"


def pid(written=DEFAULT_WRITTEN):
    """Q-post: a post id is the moment it was written, YYYYMMDD-HHMMSS (UTC)."""
    return written[0:4] + written[5:7] + written[8:10] + "-" + written[11:13] + written[14:16] + written[17:19]


def run_build(root):
    return subprocess.run(
        [sys.executable, str(BUILD)], cwd=root, capture_output=True, text=True
    )


def read(root, relative):
    return (root / "docs" / relative).read_text(encoding="utf-8")


def page(root, post_id):
    return read(root, f"p/{post_id}/index.html")


def _write_text_files(content, files):
    if not files:
        return
    if isinstance(files, dict):
        entries = files.items()
    else:
        entries = ((f"posts/{pid(written)}.md", text) for written, text in files)
    for relative, text in entries:
        path = content / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _write_jsonl(content, name, rows):
    if rows:
        (content / name).write_text("\n".join(rows) + "\n", encoding="utf-8")


def _json_rows(values):
    return [value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) for value in values]


def _link_rows(link):
    rows = []
    for event in link.get("events", []):
        row = {"link": link["id"], "action": event["action"], "at": event["at"], "why": event["why"]}
        if event["action"] == "created":
            row = {"link": link["id"], "from": link["from"], "to": link["to"], "anchor": link["anchor"], **row}
            row = {key: row[key] for key in ("link", "from", "to", "anchor", "action", "at", "why")}
        rows.append(json.dumps(row, ensure_ascii=False))
    return rows


@contextmanager
def temporary_site(
    files=None,
    images=None,
    old_docs=None,
    root_index=None,
    *,
    about="소개\n",
    posts=None,
    post_files=None,
    patches=None,
    links=None,
    shares=None,
    tags=None,
):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        content = root / "content"
        content.mkdir()

        if about is not None:
            (content / "about.md").write_text(about, encoding="utf-8")
        if post_files:
            _write_text_files(content / "posts", post_files)
        _write_text_files(content, posts)
        _write_text_files(content, files)

        if isinstance(images, dict):
            image_entries = images.items()
        else:
            image_entries = ((name, b"image") for name in (images or ()))
        for name, data in image_entries:
            path = content / "images" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        if patches:
            _write_jsonl(content, "patches.jsonl", _json_rows(patches.values()))
        if links:
            rows = []
            for link in links.values():
                rows.extend(_json_rows(link) if isinstance(link, list) else _link_rows(link))
            _write_jsonl(content, "links.jsonl", rows)
        if shares:
            _write_jsonl(content, "shares.jsonl", _json_rows(shares.values()))
        if tags:
            _write_jsonl(content, "tags.jsonl", _json_rows(tags))

        if old_docs is not None:
            docs = root / "docs"
            for filename, data in old_docs.items():
                path = docs / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

        if root_index is not None:
            (root / "index.html").write_text(root_index, encoding="utf-8")

        yield root
