from __future__ import annotations

from pydantic import Field

from .base import PDABaseModel
from .documents import ChunkMetadataDigest
from .locators import SourceLocator


class RankSignals(PDABaseModel):
    structured_filter_applied: bool = False
    bm25_rank: int | None = None
    dense_rank: int | None = None
    rrf_rank: int | None = None


class EvidencePackItem(PDABaseModel):
    evidence_id: str
    doc_id: str
    doc_version_id: str
    locator: SourceLocator
    safe_summary: str
    metadata_digest: ChunkMetadataDigest
    rank_signals: RankSignals


class EvidencePack(PDABaseModel):
    items: list[EvidencePackItem] = Field(default_factory=list)
    token_budget: int | None = None
    per_doc_limit: int | None = None
