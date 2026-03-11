from __future__ import annotations

from enum import Enum


class DocumentType(str, Enum):
    BJJ = "BJJ"
    NOTES = "notes"


class ChunkType(str, Enum):
    BJJ_RECORD = "bjj_record"
    NOTES_SECTION = "notes_section"


class Orientation(str, Enum):
    TOP = "上位"
    BOTTOM = "下位"


class Distance(str, Enum):
    FAR = "远距离"
    CLOSE = "近距离"


class OpponentControl(str, Enum):
    COLLAR = "衣领"
    SLEEVE = "袖子"
    WRIST = "手腕"
    PANTS = "裤子"
    ANKLE = "脚腕"
    HIP = "胯"
    NECK = "脖子"
    UNKNOWN = "不确定"


class TaskType(str, Enum):
    RETRIEVE_SIMPLE = "RETRIEVE_SIMPLE"
    COACH_BJJ = "COACH_BJJ"
    COACH_LITERARY = "COACH_LITERARY"
    META = "META"
    MIXED = "MIXED"


class DomainType(str, Enum):
    BJJ = "BJJ"
    NOTES = "NOTES"
    MIXED = "MIXED"


class NextAction(str, Enum):
    CLARIFY = "CLARIFY"
    RETRIEVE = "RETRIEVE"
    WRITE_FLOW = "WRITE_FLOW"


class ClarifyWho(str, Enum):
    ORCHESTRATOR = "ORCHESTRATOR"
    BJJ_COACH = "BJJ_COACH"


class ClarifySlot(str, Enum):
    DOMAIN = "domain"
    POSITION = "position"
    ORIENTATION = "orientation"
    DISTANCE = "distance"
    GOAL = "goal"
    DATE_RANGE = "date_range"
    OPPONENT_CONTROL = "opponent_control"


class GateLabel(str, Enum):
    HIGH_EVIDENCE = "HIGH_EVIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_EVIDENCE = "LOW_EVIDENCE"


class GateActionHint(str, Enum):
    ANSWER = "ANSWER"
    ANSWER_WITH_CAVEATS = "ANSWER_WITH_CAVEATS"
    ASK_CLARIFY = "ASK_CLARIFY"


class BJJAnswerMode(str, Enum):
    FULL = "FULL"
    AMBIGUOUS_FINAL = "AMBIGUOUS_FINAL"
    LOW_EVIDENCE = "LOW_EVIDENCE"


class NextStepType(str, Enum):
    NONE = "NONE"
    RECORD_SUGGESTION = "RECORD_SUGGESTION"
    QUERY_REFINE = "QUERY_REFINE"


class PolicyVersion(str, Enum):
    BASE = "base"
    POLICY = "policy"


class TraceCaptureLevel(str, Enum):
    MINIMAL = "minimal"
    DEBUG = "debug"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SummaryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BUILT = "built"
    FALLBACK = "fallback"
    FAILED = "failed"


class EntryPoint(str, Enum):
    CHAT = "chat"
    RECORD = "record"


class EvalMetricName(str, Enum):
    SCHEMA_COMPLIANCE = "schema_compliance_rate"
    MODE_POLICY_CONSISTENCY = "mode_policy_consistency"
    ALLOWED_CITATION_ACCURACY = "allowed_citation_accuracy"
    CITATION_COVERAGE = "citation_coverage"
    PLAN_C_BRANCH_COUNT = "plan_c_branch_count"
    DRILL_COMPLETENESS = "drill_completeness_rate"
    LOW_EVIDENCE_SAFETY = "low_evidence_safety_proxy"
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"


class ModelVariant(str, Enum):
    BASE = "base"
    POLICY = "policy"


class EvalRunStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"


class EvalStageStatus(str, Enum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"
