from __future__ import annotations

from pathlib import Path


class LocalFileStore:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def write_markdown_snapshot(self, doc_id: str, doc_version_id: str, raw_text: str) -> str:
        target_path = self.root_dir / doc_id / f"{doc_version_id}.md"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(raw_text, encoding="utf-8")
        return str(target_path)

    def read_markdown_snapshot(self, snapshot_ref: str) -> str:
        return Path(snapshot_ref).read_text(encoding="utf-8")
