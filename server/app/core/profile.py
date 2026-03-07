from __future__ import annotations

from pydantic import Field

from .base import PDABaseModel


class ProfileConstraint(PDABaseModel):
    kind: str
    value: str
    note: str | None = None


class ProfileSummary(PDABaseModel):
    profile_version_id: str
    ruleset_default: str = "Gi"
    injuries: list[ProfileConstraint] = Field(default_factory=list)
    forbidden_actions: list[ProfileConstraint] = Field(default_factory=list)
    preferences: list[ProfileConstraint] = Field(default_factory=list)
