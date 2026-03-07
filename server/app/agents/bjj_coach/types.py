from __future__ import annotations

from pydantic import Field

from server.app.core import GateActionHint, GateLabel, OpponentControl, PDABaseModel, ProfileSummary


class RequestSemantics(PDABaseModel):
    position: str | None = None
    orientation: str | None = None
    distance: str | None = None
    goal: str | None = None
    date_range: str | None = None
    opponent_control: str | None = None
    ruleset: str = "Gi"
    constraints: list[str] = Field(default_factory=list)
    user_intent: str = "coach_bjj"


class EvidenceSummary(PDABaseModel):
    k_chunks: int = 0
    k_docs: int = 0
    slot_coverage: dict[str, int] = Field(default_factory=dict)
    slot_conflict: dict[str, bool] = Field(default_factory=dict)
    topic_concentration: dict[str, float] = Field(default_factory=dict)
    doc_type_purity: float = 0.0
    match_rates: dict[str, float | None] = Field(default_factory=dict)
    risk_signals: list[str] = Field(default_factory=list)


class GateDecision(PDABaseModel):
    gate_label: GateLabel
    reason_codes: list[str] = Field(default_factory=list)
    missing_slot: str | None = None
    action_hint: GateActionHint


class BJJCoachInput(PDABaseModel):
    query_original: str
    query_clean: str
    confirmed_slots: dict[str, str] = Field(default_factory=dict)
    coach_clarify_round: int = 0
    coach_pending_slot: str | None = None
    profile_summary: ProfileSummary = Field(
        default_factory=lambda: ProfileSummary(profile_version_id="profile_default")
    )
