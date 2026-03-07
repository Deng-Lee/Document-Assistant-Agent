from __future__ import annotations

import hashlib
from pathlib import Path

from server.app.core import LocatorIndex

from .types import LoadedMarkdown


class MarkdownLoader:
    def load_file(self, path: str | Path) -> LoadedMarkdown:
        source_path = Path(path)
        raw_bytes = source_path.read_bytes()
        return self.load_text(raw_bytes.decode("utf-8"), source_path=str(source_path), size_bytes=len(raw_bytes))

    def load_text(self, raw_text: str, source_path: str | None = None, size_bytes: int | None = None) -> LoadedMarkdown:
        normalized = self._normalize_newlines(raw_text)
        frontmatter = self._parse_frontmatter(normalized)
        encoded = normalized.encode("utf-8")
        return LoadedMarkdown(
            source_path=source_path,
            raw_text=normalized,
            locator_index=LocatorIndex(
                source_path=source_path,
                line_start_offsets=self._build_line_start_offsets(normalized),
            ),
            size_bytes=size_bytes if size_bytes is not None else len(encoded),
            content_hash=hashlib.sha256(encoded).hexdigest(),
            frontmatter=frontmatter,
        )

    @staticmethod
    def _normalize_newlines(raw_text: str) -> str:
        return raw_text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _build_line_start_offsets(raw_text: str) -> list[int]:
        offsets = [0]
        for index, char in enumerate(raw_text):
            if char == "\n":
                offsets.append(index + 1)
        return offsets

    @staticmethod
    def _parse_frontmatter(raw_text: str) -> dict[str, str]:
        lines = raw_text.splitlines()
        if len(lines) < 3 or lines[0].strip() != "---":
            return {}
        end_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                end_index = index
                break
        if end_index is None:
            return {}
        frontmatter: dict[str, str] = {}
        for line in lines[1:end_index]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()
        return frontmatter
