from __future__ import annotations

import re

from server.app.core import EvidencePack, LiteraryAnchor, LiteraryFinalAnswer, RuntimeConfigSnapshot, build_runtime_config
from server.app.storage import DocumentRepository

from .provider import LiteraryGenerationRequest, LiteraryGenerator, build_literary_generator


class LiteraryService:
    def __init__(
        self,
        document_repository: DocumentRepository | None = None,
        runtime_config: RuntimeConfigSnapshot | None = None,
        generator: LiteraryGenerator | None = None,
    ):
        self.document_repository = document_repository
        self.runtime_config = runtime_config or build_runtime_config()
        self.generator = generator or build_literary_generator(self.runtime_config)

    def run(self, user_query: str, evidence_pack: EvidencePack) -> LiteraryFinalAnswer:
        anchors = self._select_anchors(evidence_pack)
        answer_text = self.generator.generate(
            LiteraryGenerationRequest(
                user_query=user_query,
                anchors=anchors,
                runtime_config=self.runtime_config,
            )
        ).text
        return LiteraryFinalAnswer(text=answer_text, anchors=anchors)

    def _select_anchors(self, evidence_pack: EvidencePack) -> list[LiteraryAnchor]:
        anchors: list[LiteraryAnchor] = []
        seen_docs: set[str] = set()
        unique_items = []
        for item in evidence_pack.items:
            if item.doc_id in seen_docs:
                continue
            seen_docs.add(item.doc_id)
            unique_items.append(item)
            if len(unique_items) >= 3:
                break
        for index, item in enumerate(unique_items, start=1):
            anchor_type = "raw_excerpt" if index == 1 else "safe_summary"
            content = (
                self._build_raw_excerpt(item.evidence_id, item.excerpt_snapshot)
                if anchor_type == "raw_excerpt"
                else self._build_safe_summary_anchor(item.safe_summary)
            )
            anchors.append(
                LiteraryAnchor(
                    anchor_type=anchor_type,
                    doc_rank=index,
                    evidence_id=item.evidence_id,
                    doc_version_id=item.doc_version_id,
                    locator=item.locator,
                    citation=f"{item.doc_version_id}:{item.locator.line_range.start}",
                    content=content,
                    heading_path=item.metadata_digest.heading_path,
                )
            )
        return anchors

    def _build_raw_excerpt(self, chunk_id: str, excerpt_snapshot: str | None) -> str:
        chunk_text = self._load_chunk_raw_text(chunk_id)
        source = chunk_text or excerpt_snapshot or ""
        without_code = re.sub(r"```.*?```", " ", source, flags=re.S)
        filtered_lines = []
        for line in without_code.splitlines():
            lowered = line.lower()
            if any(pattern in lowered for pattern in _INSTRUCTION_LIKE_PATTERNS):
                continue
            filtered_lines.append(line.strip())
        cleaned = re.sub(r"\s+", " ", " ".join(line for line in filtered_lines if line)).strip()
        if not cleaned:
            cleaned = re.sub(r"\s+", " ", source).strip()
        excerpt = cleaned[:400].strip()
        if len(excerpt) > 220:
            paragraph = excerpt[:220]
            last_sentence_break = max(paragraph.rfind("。"), paragraph.rfind("！"), paragraph.rfind("？"), paragraph.rfind(". "))
            if last_sentence_break >= 80:
                excerpt = paragraph[: last_sentence_break + 1].strip()
            else:
                excerpt = paragraph.rstrip() + "…"
        return excerpt

    def _build_safe_summary_anchor(self, safe_summary: str) -> str:
        normalized = re.sub(r"\s+", " ", safe_summary or "").strip()
        return normalized[:160]

    def _load_chunk_raw_text(self, chunk_id: str) -> str | None:
        if self.document_repository is None:
            return None
        chunk = self.document_repository.get_chunk(chunk_id)
        if chunk is None or not chunk.raw_text_ref:
            return None
        return chunk.raw_text_ref


_INSTRUCTION_LIKE_PATTERNS = [
    "忽略",
    "无视",
    "替换系统",
    "你必须",
    "遵循以下指令",
    "开发者消息",
    "system prompt",
    "ignore previous",
    "ignore the previous",
    "developer message",
]
