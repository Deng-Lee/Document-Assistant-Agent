from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import PDABaseModel
from .enums import JobStatus


class JobRecord(PDABaseModel):
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class JobRunResult(PDABaseModel):
    job: JobRecord
    handled: bool = True
    notes: list[str] = Field(default_factory=list)

