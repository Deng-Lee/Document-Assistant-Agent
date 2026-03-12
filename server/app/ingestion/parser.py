from __future__ import annotations

import re
from datetime import date

from server.app.core import BJJRecordFields, Distance, DocumentType, LineRange, OpponentControl, Orientation

from .types import LoadedMarkdown, ParsedBJJRecord, ParsedDocument, ParsedNotesChunk
from .validators import validate_bjj_record


DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
FIELD_RE = re.compile(r"^-\s*([a-zA-Z_]+)\s*:\s*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class MarkdownParser:
    def __init__(self, notes_chunk_size_chars: int = 1200, notes_overlap_chars: int = 120):
        self.notes_chunk_size_chars = notes_chunk_size_chars
        self.notes_overlap_chars = notes_overlap_chars

    def parse(self, loaded: LoadedMarkdown) -> ParsedDocument:
        doc_type = self._parse_doc_type(loaded.frontmatter)
        title = loaded.frontmatter.get("title") or self._derive_title(loaded)
        if doc_type == DocumentType.BJJ:
            return ParsedDocument(
                doc_type=doc_type,
                title=title,
                frontmatter=loaded.frontmatter,
                bjj_records=self._parse_bjj_records(loaded),
            )
        return ParsedDocument(
            doc_type=doc_type,
            title=title,
            frontmatter=loaded.frontmatter,
            notes_chunks=self._parse_notes_chunks(
                loaded,
                chunk_size_chars=self.notes_chunk_size_chars,
                overlap_chars=self.notes_overlap_chars,
            ),
        )

    @staticmethod
    def _parse_doc_type(frontmatter: dict[str, str]) -> DocumentType:
        raw_value = frontmatter.get("type")
        if raw_value is None:
            raise ValueError("frontmatter.type is required")
        normalized = raw_value.strip()
        if normalized == "BJJ":
            return DocumentType.BJJ
        if normalized.lower() == "notes":
            return DocumentType.NOTES
        raise ValueError(f"unsupported frontmatter.type: {raw_value}")

    def _parse_bjj_records(self, loaded: LoadedMarkdown) -> list[ParsedBJJRecord]:
        lines = loaded.raw_text.splitlines()
        start_line = self._body_start_line(lines)
        records: list[ParsedBJJRecord] = []
        current_date: date | None = None
        current_fields: dict[str, str] = {}
        current_start_line: int | None = None
        last_field: str | None = None

        def flush(end_line: int) -> None:
            nonlocal current_date, current_fields, current_start_line, last_field
            if current_date is None or current_start_line is None:
                current_fields = {}
                last_field = None
                return
            record = BJJRecordFields(
                date=current_date,
                position=current_fields.get("position", ""),
                orientation=Orientation(current_fields.get("orientation", "")),
                distance=Distance(current_fields.get("distance", "")),
                goal=current_fields.get("goal", ""),
                your_action=current_fields.get("your_action", ""),
                opponent_response=current_fields.get("opponent_response", ""),
                opponent_control=OpponentControl(current_fields["opponent_control"])
                if current_fields.get("opponent_control")
                else None,
                your_adjustment=current_fields.get("your_adjustment"),
                notes=current_fields.get("notes"),
            )
            errors = validate_bjj_record(record)
            if errors:
                raise ValueError("; ".join(errors))
            raw_record_text = "\n".join(lines[current_start_line - 1 : end_line])
            records.append(
                ParsedBJJRecord(
                    fields=record,
                    line_range=LineRange(start=current_start_line, end=end_line),
                    raw_record_text=raw_record_text,
                )
            )
            current_date = None
            current_fields = {}
            current_start_line = None
            last_field = None

        for line_number in range(start_line, len(lines) + 1):
            line = lines[line_number - 1]
            heading_match = DATE_HEADING_RE.match(line)
            if heading_match:
                if current_date is not None and current_start_line is not None:
                    flush(line_number - 1)
                current_date = date.fromisoformat(heading_match.group(1))
                current_start_line = line_number
                continue

            if current_date is None:
                continue

            field_match = FIELD_RE.match(line)
            if field_match:
                last_field = field_match.group(1).strip()
                current_fields[last_field] = field_match.group(2).strip()
                continue

            if last_field and line.strip():
                current_fields[last_field] = f"{current_fields[last_field]}\n{line.strip()}".strip()

        if current_date is not None and current_start_line is not None:
            flush(len(lines))

        return records

    def _parse_notes_chunks(self, loaded: LoadedMarkdown, chunk_size_chars: int = 1200, overlap_chars: int = 120) -> list[ParsedNotesChunk]:
        lines = loaded.raw_text.splitlines()
        start_line = self._body_start_line(lines)
        chunks: list[ParsedNotesChunk] = []
        heading_stack: list[tuple[int, str]] = []
        buffer_lines: list[tuple[int, str]] = []

        def flush_buffer() -> None:
            nonlocal buffer_lines
            if not buffer_lines:
                return
            grouped = self._group_notes_lines(buffer_lines, chunk_size_chars, overlap_chars)
            for line_range, text in grouped:
                chunks.append(
                    ParsedNotesChunk(
                        heading_path=[title for _, title in heading_stack],
                        line_range=line_range,
                        text=text,
                    )
                )
            buffer_lines = []

        for line_number in range(start_line, len(lines) + 1):
            line = lines[line_number - 1]
            heading_match = HEADING_RE.match(line)
            if heading_match:
                flush_buffer()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                heading_stack[:] = [item for item in heading_stack if item[0] < level]
                heading_stack.append((level, title))
                continue
            buffer_lines.append((line_number, line))

        flush_buffer()
        return [chunk for chunk in chunks if chunk.text.strip()]

    @staticmethod
    def _group_notes_lines(
        lines_with_numbers: list[tuple[int, str]],
        chunk_size_chars: int,
        overlap_chars: int,
    ) -> list[tuple[LineRange, str]]:
        groups: list[tuple[LineRange, str]] = []
        current_lines: list[tuple[int, str]] = []
        current_length = 0

        for line_number, text in lines_with_numbers:
            addition = len(text) + 1
            if current_lines and current_length + addition > chunk_size_chars:
                groups.append(
                    (
                        LineRange(start=current_lines[0][0], end=current_lines[-1][0]),
                        "\n".join(line for _, line in current_lines).strip(),
                    )
                )
                overlap_bucket: list[tuple[int, str]] = []
                overlap_length = 0
                for overlap_line in reversed(current_lines):
                    overlap_bucket.insert(0, overlap_line)
                    overlap_length += len(overlap_line[1]) + 1
                    if overlap_length >= overlap_chars:
                        break
                current_lines = overlap_bucket
                current_length = sum(len(value) + 1 for _, value in current_lines)
            current_lines.append((line_number, text))
            current_length += addition

        if current_lines:
            groups.append(
                (
                    LineRange(start=current_lines[0][0], end=current_lines[-1][0]),
                    "\n".join(line for _, line in current_lines).strip(),
                )
            )
        return groups

    @staticmethod
    def _body_start_line(lines: list[str]) -> int:
        if len(lines) < 3 or lines[0].strip() != "---":
            return 1
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return index + 2
        return 1

    @staticmethod
    def _derive_title(loaded: LoadedMarkdown) -> str:
        if loaded.source_path:
            return loaded.source_path.rsplit("/", 1)[-1]
        for line in loaded.raw_text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return "Untitled Markdown"
