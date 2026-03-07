from __future__ import annotations

from server.app.core import EntryPoint, ExecutionPlan, ExecutionPlanExplain, NextAction, TaskType, DomainType
from server.app.core.runtime_config import RuntimeConfigSnapshot


def maybe_short_circuit_write_flow(
    entrypoint: EntryPoint,
    user_message: str,
    runtime_config: RuntimeConfigSnapshot,
) -> ExecutionPlan | None:
    stripped = user_message.strip()
    if entrypoint == EntryPoint.RECORD:
        return ExecutionPlan(
            task=TaskType.META,
            domain=DomainType.BJJ,
            next_action=NextAction.WRITE_FLOW,
            explain=ExecutionPlanExplain(reason_codes=["ENTRYPOINT_RECORD"], probe_used=False),
        )

    for prefix in runtime_config.orchestrator.write_intent_prefixes:
        if stripped.startswith(prefix):
            return ExecutionPlan(
                task=TaskType.META,
                domain=DomainType.BJJ,
                next_action=NextAction.WRITE_FLOW,
                explain=ExecutionPlanExplain(reason_codes=["WRITE_INTENT_PREFIX_MATCH"], probe_used=False),
            )
    return None
