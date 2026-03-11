from __future__ import annotations

import re
from hashlib import sha1

from server.app.core import ChunkMetadataDigest, ChunkRecord, ChunkType, DocVersionRecord, SourceLocator, SummaryStatus

from .types import LoadedMarkdown, ParsedDocument


def build_chunk_records(loaded: LoadedMarkdown, parsed: ParsedDocument, doc_id: str, doc_version: DocVersionRecord) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    if parsed.doc_type.value == "BJJ":
        for index, record in enumerate(parsed.bjj_records):
            locator = resolve_locator(
                loaded=loaded,
                doc_version_id=doc_version.doc_version_id,
                line_start=record.line_range.start,
                line_end=record.line_range.end,
            )
            chunk_id = _chunk_id(doc_version.doc_version_id, index)
            raw_text = record.raw_record_text
            clean_search_text = normalize_search_text(raw_text)
            clean_embed_text = build_bjj_embed_text(record.fields)
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    doc_version_id=doc_version.doc_version_id,
                    doc_type=parsed.doc_type,
                    chunk_type=ChunkType.BJJ_RECORD,
                    locator=locator,
                    metadata_digest=ChunkMetadataDigest(
                        date=record.fields.date,
                        position=record.fields.position,
                        orientation=record.fields.orientation,
                        distance=record.fields.distance,
                        goal=record.fields.goal,
                        opponent_control=record.fields.opponent_control,
                    ),
                    safe_summary="",
                    summary_status=SummaryStatus.PENDING,
                    clean_search_text=clean_search_text,
                    clean_embed_text=clean_embed_text,
                    raw_text_ref=raw_text,
                )
            )
    else:
        for index, note_chunk in enumerate(parsed.notes_chunks):
            locator = resolve_locator(
                loaded=loaded,
                doc_version_id=doc_version.doc_version_id,
                line_start=note_chunk.line_range.start,
                line_end=note_chunk.line_range.end,
            )
            chunk_id = _chunk_id(doc_version.doc_version_id, index)
            clean_search_text = normalize_search_text(note_chunk.text)
            clean_embed_text = build_notes_embed_text(note_chunk.heading_path, note_chunk.text)
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    doc_version_id=doc_version.doc_version_id,
                    doc_type=parsed.doc_type,
                    chunk_type=ChunkType.NOTES_SECTION,
                    locator=locator,
                    metadata_digest=ChunkMetadataDigest(heading_path=note_chunk.heading_path),
                    safe_summary="",
                    summary_status=SummaryStatus.PENDING,
                    clean_search_text=clean_search_text,
                    clean_embed_text=clean_embed_text,
                    raw_text_ref=note_chunk.text,
                )
            )
    return chunks


def resolve_locator(loaded: LoadedMarkdown, doc_version_id: str, line_start: int, line_end: int) -> SourceLocator:
    lines = loaded.raw_text.splitlines()
    line_offsets = loaded.locator_index.line_start_offsets
    char_start = line_offsets[line_start - 1]
    end_line_text = lines[line_end - 1] if line_end - 1 < len(lines) else ""
    char_end = line_offsets[line_end - 1] + len(end_line_text)
    return SourceLocator(
        doc_version_id=doc_version_id,
        source_path=loaded.source_path,
        line_range={"start": line_start, "end": line_end},
        char_range={"start": char_start, "end": char_end},
    )


def normalize_search_text(text: str) -> str:
    collapsed = re.sub(r"[>#*_`-]+", " ", text)
    collapsed = re.sub(r"\s+", " ", collapsed)
    return collapsed.strip()


def build_bjj_embed_text(record_fields) -> str:
    parts = [
        f"date: {record_fields.date.isoformat()}",
        f"position: {record_fields.position}",
        f"orientation: {record_fields.orientation.value}",
        f"distance: {record_fields.distance.value}",
        f"goal: {record_fields.goal}",
        f"opponent_control: {record_fields.opponent_control.value if record_fields.opponent_control else ''}",
        f"your_action: {record_fields.your_action}",
        f"opponent_response: {record_fields.opponent_response}",
        f"your_adjustment: {record_fields.your_adjustment or ''}",
        f"notes: {record_fields.notes or ''}",
    ]
    return "\n".join(parts).strip()


def build_notes_embed_text(heading_path: list[str], text: str) -> str:
    prefix = " / ".join(heading_path)
    return f"{prefix}\n\n{text}".strip()


def build_safe_summary_fallback(clean_search_text: str, limit: int = 120) -> str:
    return clean_search_text[:limit].strip()


def _chunk_id(doc_version_id: str, index: int) -> str:
    return f"chunk_{sha1(f'{doc_version_id}:{index}'.encode('utf-8')).hexdigest()[:12]}"
