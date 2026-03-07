#!/usr/bin/env python3
import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_traces(traces_dir: Path) -> list[Path]:
    if not traces_dir.exists():
        return []
    return sorted([p for p in traces_dir.glob("*.json") if p.is_file()])


def _get(obj: Any, *keys: str) -> Any:
    cur = obj
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def _extract_output(trace: dict[str, Any]) -> Any:
    return (
        _get(trace, "generation_log", "output")
        or _get(trace, "generation_log", "final_answer")
        or trace.get("final_answer")
        or trace.get("output")
    )


def _extract_latency_ms(trace: dict[str, Any]) -> float | None:
    # Best effort: common fields
    for path in [
        ("generation_log", "latency_ms"),
        ("request_log", "latency_ms"),
        ("latency_ms",),
    ]:
        v = _get(trace, *path)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Compute hard metrics from trace JSON files (best-effort).")
    p.add_argument("--traces-dir", default="data/traces", help="Directory with trace JSON files")
    p.add_argument("--out", default="eval_report.json", help="Output report path")
    args = p.parse_args()

    traces_dir = Path(args.traces_dir).resolve()
    trace_files = _iter_traces(traces_dir)

    counts = {
        "total": 0,
        "bjj": 0,
        "notes": 0,
        "mode_full": 0,
        "mode_ambiguous_final": 0,
        "mode_low": 0,
        "validator_pass": 0,
    }
    latencies = []

    for tf in trace_files:
        try:
            t = _load_json(tf)
        except Exception:
            continue
        if not isinstance(t, dict):
            continue
        counts["total"] += 1

        domain = _get(t, "request_log", "domain") or _get(t, "request", "domain")
        if domain == "BJJ":
            counts["bjj"] += 1
        if domain == "NOTES":
            counts["notes"] += 1

        out = _extract_output(t)
        if isinstance(out, dict):
            mode = out.get("mode")
            if mode == "FULL":
                counts["mode_full"] += 1
            elif mode == "AMBIGUOUS_FINAL":
                counts["mode_ambiguous_final"] += 1
            elif mode == "LOW_EVIDENCE":
                counts["mode_low"] += 1

        v = _get(t, "generation_log", "validator_report") or t.get("validator_report")
        if isinstance(v, dict) and v.get("pass") is True:
            counts["validator_pass"] += 1

        lm = _extract_latency_ms(t)
        if lm is not None:
            latencies.append(lm)

    report: dict[str, Any] = {
        "counts": counts,
        "latency_ms": {},
        "notes": "This is a best-effort hard-metrics report from trace JSON files. Extend to match your final trace schema.",
    }

    if latencies:
        latencies_sorted = sorted(latencies)
        report["latency_ms"] = {
            "n": len(latencies_sorted),
            "p50": statistics.median(latencies_sorted),
            "p95": latencies_sorted[int(0.95 * (len(latencies_sorted) - 1))],
            "min": latencies_sorted[0],
            "max": latencies_sorted[-1],
        }

    out_path = Path(args.out).resolve()
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
