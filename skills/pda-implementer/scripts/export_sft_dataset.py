#!/usr/bin/env python3
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_trace_files(traces_dir: Path) -> list[Path]:
    if not traces_dir.exists():
        return []
    return sorted([p for p in traces_dir.glob("*.json") if p.is_file()])


def _safe_json(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return x
    if isinstance(x, (bytes, bytearray)):
        try:
            x = x.decode("utf-8")
        except Exception:
            return None
    if isinstance(x, str):
        x = x.strip()
        if not x:
            return None
        try:
            return json.loads(x)
        except Exception:
            return x
    return x


def _extract_final_answer(trace: dict[str, Any]) -> Any:
    for key_path in [
        ("generation_log", "output"),
        ("generation_log", "final_answer"),
        ("final_answer",),
        ("output",),
    ]:
        cur: Any = trace
        ok = True
        for k in key_path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _extract_evidence_pack(trace: dict[str, Any]) -> list[dict[str, Any]]:
    for key_path in [
        ("evidence_log", "evidence_pack"),
        ("evidence_pack",),
        ("evidence_log",),
    ]:
        cur: Any = trace
        ok = True
        for k in key_path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]
    return []


def _extract_runtime_config(trace: dict[str, Any]) -> Any:
    for key_path in [
        ("runtime_config_snapshot",),
        ("request_log", "runtime_config_snapshot"),
        ("request_log", "runtime_config"),
    ]:
        cur: Any = trace
        ok = True
        for k in key_path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _extract_validator_report(trace: dict[str, Any]) -> Any:
    for key_path in [
        ("generation_log", "validator_report"),
        ("validator_report",),
    ]:
        cur: Any = trace
        ok = True
        for k in key_path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _extract_gate_and_slots(final_answer: Any) -> tuple[str | None, Any, Any]:
    if not isinstance(final_answer, dict):
        return None, None, None
    rs = final_answer.get("reasoning_status")
    gate = rs.get("gate_label") if isinstance(rs, dict) else None
    slots = None
    opp = None
    assumptions = final_answer.get("assumptions")
    if isinstance(assumptions, dict):
        slots = assumptions.get("confirmed_slots")
        opp = assumptions.get("opponent_control")
    return gate, slots, opp


def _export_samples(traces: Iterable[dict[str, Any]], dataset_path: Path, limit: int) -> int:
    exported = 0
    with dataset_path.open("w", encoding="utf-8") as f:
        for trace in traces:
            if limit and exported >= limit:
                break
            if not isinstance(trace, dict):
                continue

            trace_id = trace.get("trace_id") or trace.get("id")
            if not trace_id:
                continue

            final_answer = _extract_final_answer(trace)
            evidence_pack = _extract_evidence_pack(trace)
            runtime_config = _extract_runtime_config(trace)
            validator_report = _extract_validator_report(trace)

            allowed_evidence_ids = []
            for ev in evidence_pack:
                eid = ev.get("evidence_id") or ev.get("chunk_id")
                if isinstance(eid, str) and eid:
                    allowed_evidence_ids.append(eid)
            seen = set()
            allowed_evidence_ids = [x for x in allowed_evidence_ids if not (x in seen or seen.add(x))]

            gate_label, confirmed_slots, opponent_control = _extract_gate_and_slots(final_answer)

            evidence_pack_selected = []
            for ev in evidence_pack[:6]:
                evidence_pack_selected.append(
                    {
                        "evidence_id": ev.get("evidence_id") or ev.get("chunk_id"),
                        "safe_summary": ev.get("safe_summary"),
                        "metadata_digest": ev.get("metadata_digest") or ev.get("metadata"),
                    }
                )

            sample = {
                "trace_id": trace_id,
                "runtime_config_snapshot": runtime_config,
                "gate_label": gate_label,
                "confirmed_slots": confirmed_slots,
                "opponent_control": opponent_control,
                "allowed_evidence_ids": allowed_evidence_ids,
                "evidence_pack_selected": evidence_pack_selected,
                "baseline_output": final_answer,
                "validator_report": validator_report,
            }

            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            exported += 1

    return exported


def _read_traces_from_dir(traces_dir: Path) -> list[dict[str, Any]]:
    traces = []
    for tf in _iter_trace_files(traces_dir):
        try:
            t = _load_json(tf)
        except Exception:
            continue
        if isinstance(t, dict) and "trace_id" not in t:
            t = {"trace_id": tf.stem, **t}
        if isinstance(t, dict):
            t["_source_file"] = str(tf)
        traces.append(t)
    return [t for t in traces if isinstance(t, dict)]


def _read_traces_from_sqlite(db_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "traces" not in tables:
        raise SystemExit(f"SQLite missing 'traces' table. Found tables: {sorted(tables)[:20]}")

    cols = [r[1] for r in cur.execute("PRAGMA table_info(traces)").fetchall()]
    rows = cur.execute("SELECT * FROM traces").fetchall()

    traces: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        # Common patterns
        if "trace_json" in d and d.get("trace_json"):
            payload = _safe_json(d.get("trace_json"))
            if isinstance(payload, dict):
                payload.setdefault("trace_id", d.get("trace_id") or d.get("id"))
                traces.append(payload)
                continue

        # Otherwise: attempt to assemble from json columns
        assembled: dict[str, Any] = {"trace_id": d.get("trace_id") or d.get("id")}
        for k in d:
            if k.endswith("_log") or k.endswith("_json") or k in {
                "request_log",
                "retrieval_log",
                "evidence_log",
                "generation_log",
                "validator_report",
                "runtime_config_snapshot",
            }:
                assembled[k] = _safe_json(d.get(k))
        traces.append(assembled)

    con.close()
    return [t for t in traces if isinstance(t, dict) and t.get("trace_id")]


def main() -> None:
    p = argparse.ArgumentParser(description="Export SFT dataset JSONL from traces (dir JSON or SQLite best-effort).")
    p.add_argument("--repo", default=".", help="Repo root")
    p.add_argument("--traces-dir", default="data/traces", help="Directory containing trace JSON files")
    p.add_argument("--sqlite", default="", help="SQLite db path containing a traces table (optional)")
    p.add_argument("--out", required=True, help="Output directory, e.g. datasets/sft/v1/20260307")
    p.add_argument("--limit", type=int, default=0, help="Limit number of traces (0 = no limit)")
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    out_dir = (repo / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = out_dir / "dataset_export.jsonl"
    manifest_path = out_dir / "manifest.json"

    traces: list[dict[str, Any]]
    source: dict[str, Any] = {"repo": str(repo)}

    if args.sqlite:
        db_path = (repo / args.sqlite).resolve() if not Path(args.sqlite).is_absolute() else Path(args.sqlite).resolve()
        traces = _read_traces_from_sqlite(db_path)
        source.update({"sqlite": str(db_path)})
    else:
        traces_dir = (repo / args.traces_dir).resolve() if not Path(args.traces_dir).is_absolute() else Path(args.traces_dir).resolve()
        traces = _read_traces_from_dir(traces_dir)
        source.update({"traces_dir": str(traces_dir)})

    exported = _export_samples(traces, dataset_path, args.limit)

    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "dataset_file": str(dataset_path),
        "count": exported,
        "notes": "Best-effort export. Ensure trace schema contains required fields for training.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {dataset_path} ({exported} samples)")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
