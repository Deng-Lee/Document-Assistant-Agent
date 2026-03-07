from __future__ import annotations

from pydantic import Field

from .base import PDABaseModel


class LineRange(PDABaseModel):
    start: int = Field(..., ge=1)
    end: int = Field(..., ge=1)


class CharRange(PDABaseModel):
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)


class SourceLocator(PDABaseModel):
    doc_version_id: str
    source_path: str | None = None
    line_range: LineRange
    char_range: CharRange


class LocatorIndex(PDABaseModel):
    source_path: str | None = None
    line_start_offsets: list[int] = Field(default_factory=list)
