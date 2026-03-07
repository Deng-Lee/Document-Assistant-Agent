from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import PDABaseModel
from .enums import BJJAnswerMode, GateLabel, NextStepType


class BJJAssumptions(PDABaseModel):
    ruleset: str = "Gi"
    confirmed_slots: dict[str, str] = Field(default_factory=dict)
    opponent_control: str = "不确定"


class BJJReasoningStatus(PDABaseModel):
    gate_label: GateLabel
    reason_codes: list[str] = Field(default_factory=list)
    coach_clarify_round: int = Field(default=0, ge=0, le=1)


class BJJObservation(PDABaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class BJJPlanBlock(PDABaseModel):
    title: str = ""
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    generic: bool = False


class BJJPlanBranch(PDABaseModel):
    if_condition: str = Field(alias="if")
    then: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    generic: bool = False


class BJJBranchPlan(PDABaseModel):
    branches: list[BJJPlanBranch] = Field(default_factory=list)


class BJJPlanCollection(PDABaseModel):
    A_baseline: BJJPlanBlock = Field(default_factory=BJJPlanBlock)
    B_offense: BJJPlanBlock = Field(default_factory=BJJPlanBlock)
    C_branch: BJJBranchPlan = Field(default_factory=BJJBranchPlan)


class BJJMistake(PDABaseModel):
    text: str
    fix: str
    evidence_ids: list[str] = Field(default_factory=list)
    generic: bool = False


class DrillStart(PDABaseModel):
    position: str = ""
    orientation: str = ""
    distance: str = ""


class BJJDrill(PDABaseModel):
    name: str
    start: DrillStart
    opponent_control: str = "不确定"
    goal: str = ""
    dosage: str = ""
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    generic: bool = False


class BJJNextStep(PDABaseModel):
    type: NextStepType
    message: str = ""
    record_template: str = ""


class BJJValidatorReport(PDABaseModel):
    validator_pass: bool
    errors: list[str] = Field(default_factory=list)
    repair_used: bool = False
    validator_fail_final: bool = False


class BJJFullAnswer(PDABaseModel):
    mode: Literal["FULL"] = "FULL"
    assumptions: BJJAssumptions = Field(default_factory=BJJAssumptions)
    reasoning_status: BJJReasoningStatus
    caveats: list[str] = Field(default_factory=list)
    observations: list[BJJObservation] = Field(default_factory=list)
    plans: BJJPlanCollection = Field(default_factory=BJJPlanCollection)
    mistakes: list[BJJMistake] = Field(default_factory=list)
    drills: list[BJJDrill] = Field(default_factory=list)
    next_step: BJJNextStep = Field(default_factory=lambda: BJJNextStep(type=NextStepType.NONE))
    citations: list[str] = Field(default_factory=list)


class BJJAmbiguousFinalAnswer(PDABaseModel):
    mode: Literal["AMBIGUOUS_FINAL"] = "AMBIGUOUS_FINAL"
    assumptions: BJJAssumptions = Field(default_factory=BJJAssumptions)
    reasoning_status: BJJReasoningStatus
    caveats: list[str] = Field(default_factory=list)
    observations: list[BJJObservation] = Field(default_factory=list)
    plans: BJJPlanCollection = Field(default_factory=BJJPlanCollection)
    mistakes: list[BJJMistake] = Field(default_factory=list)
    drills: list[BJJDrill] = Field(default_factory=list)
    next_step: BJJNextStep = Field(
        default_factory=lambda: BJJNextStep(type=NextStepType.RECORD_SUGGESTION)
    )
    citations: list[str] = Field(default_factory=list)


class BJJLowEvidenceAnswer(PDABaseModel):
    mode: Literal["LOW_EVIDENCE"] = "LOW_EVIDENCE"
    assumptions: BJJAssumptions = Field(default_factory=BJJAssumptions)
    reasoning_status: BJJReasoningStatus
    caveats: list[str] = Field(default_factory=list)
    observations: list[BJJObservation] = Field(default_factory=list)
    plans: BJJPlanCollection = Field(default_factory=BJJPlanCollection)
    mistakes: list[BJJMistake] = Field(default_factory=list)
    drills: list[BJJDrill] = Field(default_factory=list)
    next_step: BJJNextStep = Field(
        default_factory=lambda: BJJNextStep(type=NextStepType.QUERY_REFINE)
    )
    citations: list[str] = Field(default_factory=list)


BJJAnswerType = BJJFullAnswer | BJJAmbiguousFinalAnswer | BJJLowEvidenceAnswer
