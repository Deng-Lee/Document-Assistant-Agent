from __future__ import annotations

import re

from server.app.core import EvidencePack, LiteraryAnchor, LiteraryFinalAnswer


class LiteraryService:
    def run(self, user_query: str, evidence_pack: EvidencePack) -> LiteraryFinalAnswer:
        anchors = self._select_anchors(evidence_pack)
        answer_text = self._compose_answer(user_query, anchors)
        return LiteraryFinalAnswer(text=answer_text, anchors=anchors)

    def _select_anchors(self, evidence_pack: EvidencePack) -> list[LiteraryAnchor]:
        anchors: list[LiteraryAnchor] = []
        seen_docs: set[str] = set()
        for item in evidence_pack.items:
            if item.doc_id in seen_docs:
                continue
            seen_docs.add(item.doc_id)
            anchors.append(
                LiteraryAnchor(
                    evidence_id=item.evidence_id,
                    doc_version_id=item.doc_version_id,
                    locator=item.locator,
                    citation=f"{item.doc_version_id}:{item.locator.line_range.start}",
                    heading_path=item.metadata_digest.heading_path,
                )
            )
            if len(anchors) >= 3:
                break
        return anchors

    def _compose_answer(self, user_query: str, anchors: list[LiteraryAnchor]) -> str:
        if not anchors:
            return f"围绕“{user_query}”，我先给你一个不依赖既有笔记的开放式写作起点。"
        citations = "、".join(anchor.citation for anchor in anchors)
        return (
            f"围绕“{user_query}”，我会优先沿着你笔记里已经出现的意象和语气继续推进。"
            f"当前参考锚点来自 {citations}。接下来适合先保留原有语感，再把主题推向更明确的冲突或反转。"
        )
