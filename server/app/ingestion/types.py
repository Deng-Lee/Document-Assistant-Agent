from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from server.app.core import (
    BJJRecordFields,
    ChunkRecord,
    DocVersionRecord,
    DocumentRecord,
    DocumentType,
    JobStatus,
    LineRange,
    LocatorIndex,
    PDABaseModel,
)


class LoadedMarkdown(PDABaseModel):
    source_path: str | None = None
    raw_text: str
    locator_index: LocatorIndex
    size_bytes: int = Field(..., ge=0)
    content_hash: str
    frontmatter: dict[str, str] = Field(default_factory=dict)


class ParsedBJJRecord(PDABaseModel):
    fields: BJJRecordFields
    line_range: LineRange
    raw_record_text: str


class ParsedNotesChunk(PDABaseModel):
    heading_path: list[str] = Field(default_factory=list)
    line_range: LineRange
    text: str


class ParsedDocument(PDABaseModel):
    doc_type: DocumentType
    title: str
    frontmatter: dict[str, str] = Field(default_factory=dict)
    bjj_records: list[ParsedBJJRecord] = Field(default_factory=list)
    notes_chunks: list[ParsedNotesChunk] = Field(default_factory=list)


class IngestionJob(PDABaseModel):
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    payload: dict[str, Any] = Field(default_factory=dict)


class IngestionResult(PDABaseModel):
    document: DocumentRecord
    doc_version: DocVersionRecord
    chunks: list[ChunkRecord] = Field(default_factory=list)
    jobs: list[IngestionJob] = Field(default_factory=list)
