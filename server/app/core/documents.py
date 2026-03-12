from __future__ import annotations

from datetime import date as CalendarDate
from datetime import datetime as DateTime

from pydantic import Field

from .base import PDABaseModel
from .enums import ChunkType, Distance, DocumentType, OpponentControl, Orientation, SummaryStatus
from .locators import SourceLocator


class BJJRecordFields(PDABaseModel):
    date: CalendarDate
    position: str
    orientation: Orientation
    distance: Distance
    goal: str
    your_action: str
    opponent_response: str
    opponent_control: OpponentControl | None = None
    your_adjustment: str | None = None
    notes: str | None = None


class ChunkMetadataDigest(PDABaseModel):
    date: CalendarDate | None = None
    position: str | None = None
    orientation: Orientation | None = None
    distance: Distance | None = None
    goal: str | None = None
    opponent_control: OpponentControl | None = None
    heading_path: list[str] = Field(default_factory=list)


class DocumentRecord(PDABaseModel):
    doc_id: str
    doc_type: DocumentType
    title: str
    latest_version_id: str | None = None
    created_at: DateTime
    updated_at: DateTime
    status: str = "active"


class DocVersionRecord(PDABaseModel):
    doc_version_id: str
    doc_id: str
    content_hash: str
    ingest_time: DateTime
    source_path: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class ChunkRecord(PDABaseModel):
    chunk_id: str
    doc_id: str
    doc_version_id: str
    doc_type: DocumentType
    chunk_type: ChunkType
    locator: SourceLocator
    metadata_digest: ChunkMetadataDigest
    safe_summary: str | None = None
    summary_model: str | None = None
    summary_prompt_version: str | None = None
    summary_status: SummaryStatus = SummaryStatus.PENDING
    summary_error_code: str | None = None
    summary_retry_count: int = Field(default=0, ge=0)
    summary_last_attempt_at: DateTime | None = None
    summary_next_retry_at: DateTime | None = None
    summary_last_error_at: DateTime | None = None
    clean_search_text: str | None = None
    clean_embed_text: str | None = None
    raw_text_ref: str | None = None


class EmbeddingRecord(PDABaseModel):
    chunk_id: str
    embedding_version_id: str
    provider: str
    model: str
    dimension: int = Field(..., ge=1)
