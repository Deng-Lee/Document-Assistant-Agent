from __future__ import annotations

from collections import Counter

from server.app.core import EvidencePack, GateActionHint, GateLabel, RuntimeConfigSnapshot

from .types import EvidenceSummary, GateDecision, RequestSemantics


CORE_SLOTS = ("position", "orientation", "distance", "goal")


def build_request_semantics(
    confirmed_slots: dict[str, str],
    profile_ruleset: str,
    profile_constraints: list[str],
) -> RequestSemantics:
    return RequestSemantics(
        position=confirmed_slots.get("position"),
        orientation=confirmed_slots.get("orientation"),
        distance=confirmed_slots.get("distance"),
        goal=confirmed_slots.get("goal"),
        date_range=confirmed_slots.get("date_range"),
        opponent_control=confirmed_slots.get("opponent_control"),
        ruleset=profile_ruleset or "Gi",
        constraints=profile_constraints,
    )


def summarize_evidence(evidence_pack: EvidencePack, request: RequestSemantics) -> EvidenceSummary:
    items = evidence_pack.items
    k_chunks = len(items)
    k_docs = len({item.doc_id for item in items})
    slot_coverage: dict[str, int] = {}
    slot_conflict: dict[str, bool] = {}
    topic_concentration: dict[str, float] = {}
    match_rates: dict[str, float | None] = {}
    risk_signals: list[str] = []

    for slot in (*CORE_SLOTS, "opponent_control"):
        values = []
        non_empty = 0
        for item in items:
            value = getattr(item.metadata_digest, slot, None)
            if hasattr(value, "value"):
                value = value.value
            if value:
                non_empty += 1
                values.append(value)
                if slot == "opponent_control" and value == "脖子":
                    risk_signals.append("NECK_CONTROL_PRESENT")
        slot_coverage[slot] = non_empty
        if values:
            counts = Counter(values)
            top_count = counts.most_common(1)[0][1]
            topic_concentration[slot] = top_count / k_chunks if k_chunks else 0.0
            slot_conflict[slot] = len(counts) > 1 and (top_count / len(values)) < 0.7
        else:
            topic_concentration[slot] = 0.0
            slot_conflict[slot] = False

    for slot in ("position", "orientation", "goal"):
        expected = getattr(request, slot)
        if not expected:
            match_rates[slot] = None
            continue
        matches = 0
        for item in items:
            value = getattr(item.metadata_digest, slot, None)
            if hasattr(value, "value"):
                value = value.value
            if value == expected:
                matches += 1
        match_rates[slot] = matches / k_chunks if k_chunks else 0.0

    # BJJ coach only consumes BJJ evidence packs in V1; keep purity explicit for gate math.
    doc_type_purity = 1.0 if k_chunks else 0.0

    return EvidenceSummary(
        k_chunks=k_chunks,
        k_docs=k_docs,
        slot_coverage=slot_coverage,
        slot_conflict=slot_conflict,
        topic_concentration=topic_concentration,
        doc_type_purity=doc_type_purity,
        match_rates=match_rates,
        risk_signals=sorted(set(risk_signals)),
    )


def evaluate_gate(
    request: RequestSemantics,
    evidence_summary: EvidenceSummary,
    runtime_config: RuntimeConfigSnapshot,
) -> GateDecision:
    thresholds = runtime_config.bjj_gate
    reasons: list[str] = []

    for slot in ("position", "orientation", "goal"):
        if not getattr(request, slot):
            reasons.append(f"MISSING_CORE_{slot.upper()}")
            return GateDecision(
                gate_label=GateLabel.LOW_EVIDENCE,
                reason_codes=reasons,
                action_hint=GateActionHint.ANSWER_WITH_CAVEATS,
            )

    if evidence_summary.k_chunks < thresholds.low_evidence_chunk_min:
        reasons.append("EVIDENCE_TOO_THIN")
        return GateDecision(
            gate_label=GateLabel.LOW_EVIDENCE,
            reason_codes=reasons,
            action_hint=GateActionHint.ANSWER_WITH_CAVEATS,
        )

    if evidence_summary.doc_type_purity < thresholds.doc_type_purity_min:
        reasons.append("DOC_SCOPE_MIXED")
        return GateDecision(
            gate_label=GateLabel.LOW_EVIDENCE,
            reason_codes=reasons,
            action_hint=GateActionHint.ANSWER_WITH_CAVEATS,
        )

    pos_match = evidence_summary.match_rates.get("position")
    if pos_match is not None and pos_match < thresholds.position_match_min:
        reasons.append("OFF_TOPIC")
        return GateDecision(
            gate_label=GateLabel.LOW_EVIDENCE,
            reason_codes=reasons,
            action_hint=GateActionHint.ANSWER_WITH_CAVEATS,
        )

    position_concentration = evidence_summary.topic_concentration.get("position", 0.0)
    if (
        evidence_summary.k_chunks >= 4
        and position_concentration < thresholds.low_evidence_concentration_floor
    ):
        reasons.append("NO_CONCENTRATION")
        return GateDecision(
            gate_label=GateLabel.LOW_EVIDENCE,
            reason_codes=reasons,
            action_hint=GateActionHint.ANSWER_WITH_CAVEATS,
        )

    opp_known = bool(request.opponent_control)
    if (
        evidence_summary.k_chunks >= thresholds.high_evidence_chunk_min
        and evidence_summary.doc_type_purity >= thresholds.doc_type_purity_min
        and position_concentration >= thresholds.position_concentration_min
        and opp_known
    ):
        return GateDecision(
            gate_label=GateLabel.HIGH_EVIDENCE,
            reason_codes=["EVIDENCE_SUFFICIENT"],
            action_hint=GateActionHint.ANSWER,
        )

    reasons.append("MISSING_TACTICAL_OPP_CONTROL" if not opp_known else "EVIDENCE_PARTIAL")
    return GateDecision(
        gate_label=GateLabel.AMBIGUOUS,
        reason_codes=reasons,
        missing_slot="opponent_control" if not opp_known else None,
        action_hint=GateActionHint.ANSWER_WITH_CAVEATS if not opp_known else GateActionHint.ANSWER,
    )
