from __future__ import annotations

import re
from datetime import date, timedelta

from server.app.core import DateRange, DocumentType, RetrievalFilters, RetrievalPlan


EXPLICIT_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
RECENT_DAYS_RE = re.compile(r"最近\s*(\d+)\s*天")


class QueryParser:
    def parse(
        self,
        query_text: str,
        filters_hint: RetrievalFilters | None = None,
        top_k: int = 12,
        per_doc_limit: int = 3,
        token_budget: int = 4000,
    ) -> RetrievalPlan:
        filters = filters_hint or RetrievalFilters()
        parsed_date_range = self._parse_date_range(query_text)
        if parsed_date_range and filters.date_range is None:
            filters.date_range = parsed_date_range
        if filters.doc_type is None:
            filters.doc_type = self._infer_doc_type(query_text)
        return RetrievalPlan(
            doc_type=filters.doc_type.value if filters.doc_type else "ALL",
            filters=filters,
            query_original=query_text,
            query_text=query_text.strip(),
            top_k=top_k,
            per_doc_limit=per_doc_limit,
            token_budget=token_budget,
        )

    @staticmethod
    def _infer_doc_type(query_text: str) -> DocumentType | None:
        lowered = query_text.lower()
        if any(keyword in lowered for keyword in ("bjj", "训练", "过腿", "龟防", "缠斗", "guard")):
            return DocumentType.BJJ
        if any(keyword in lowered for keyword in ("笔记", "写作", "阅读", "notes", "小说", "诗")):
            return DocumentType.NOTES
        return None

    @staticmethod
    def _parse_date_range(query_text: str) -> DateRange | None:
        explicit = EXPLICIT_DATE_RE.search(query_text)
        if explicit:
            parsed = date.fromisoformat(explicit.group(1))
            return DateRange(start=parsed, end=parsed, expression=explicit.group(1))

        recent = RECENT_DAYS_RE.search(query_text)
        if recent:
            days = int(recent.group(1))
            today = date.today()
            return DateRange(start=today - timedelta(days=days), end=today, expression=recent.group(0))

        today = date.today()
        if "本周" in query_text:
            start = today - timedelta(days=today.weekday())
            return DateRange(start=start, end=today, expression="本周")
        if "上周" in query_text:
            end = today - timedelta(days=today.weekday() + 1)
            start = end - timedelta(days=6)
            return DateRange(start=start, end=end, expression="上周")
        if "本月" in query_text:
            start = today.replace(day=1)
            return DateRange(start=start, end=today, expression="本月")
        if "上个月" in query_text:
            month_anchor = today.replace(day=1) - timedelta(days=1)
            start = month_anchor.replace(day=1)
            return DateRange(start=start, end=month_anchor, expression="上个月")
        return None
