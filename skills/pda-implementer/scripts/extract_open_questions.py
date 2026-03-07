#!/usr/bin/env python3
import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TBD_PATTERNS = [
    re.compile(r"待讨论"),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"color:#dc2626"),
]


@dataclass
class Finding:
    kind: str  # spec_tbd | missing_path
    question: str
    impact: list[str]
    recommended_default: str
    requires_confirmation: bool
    source_path: str | None = None
    source_line: int | None = None
    evidence: str | None = None


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def scan_spec(spec_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not spec_path.exists():
        return [
            Finding(
                kind="missing_path",
                question=f"Missing spec file: {spec_path}",
                impact=["planning"],
                recommended_default="Provide the correct --spec path to DEV_SPEC.md",
                requires_confirmation=True,
            )
        ]

    lines = spec_path.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines, start=1):
        if any(p.search(line) for p in TBD_PATTERNS):
            cleaned = _strip_html(line)
            findings.append(
                Finding(
                    kind="spec_tbd",
                    question=cleaned,
                    impact=["spec"],
                    recommended_default="Proceed with documented recommended defaults; record as ASSUMPTION and tune via golden-set grid search.",
                    requires_confirmation=False,
                    source_path=str(spec_path),
                    source_line=idx,
                    evidence=cleaned,
                )
            )

    return findings


def scan_repo_structure(repo_root: Path) -> list[Finding]:
    # Expected minimal module paths from DEV_SPEC (V1)
    expected_paths = [
        "DEV_SPEC.md",
        "server/app/ingestion",
        "server/app/retrieval",
        "server/app/orchestrator",
        "server/app/agents",
        "server/app/observability",
        "server/app/evaluation",
        "server/app/sft",
        "web",
        "datasets",
        "data",
    ]

    findings: list[Finding] = []
    for rel in expected_paths:
        p = repo_root / rel
        if not p.exists():
            findings.append(
                Finding(
                    kind="missing_path",
                    question=f"Missing expected path: {rel}",
                    impact=["scaffold"],
                    recommended_default="Run scaffold_repo.py in dry-run; then apply scaffold after confirmation.",
                    requires_confirmation=False,
                    source_path=str(p),
                    source_line=None,
                    evidence=None,
                )
            )

    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract open questions / TBDs from DEV_SPEC and repo structure.")
    parser.add_argument("--repo", default=".", help="Repo root (default: .)")
    parser.add_argument("--spec", default="DEV_SPEC.md", help="Path to DEV_SPEC.md (default: DEV_SPEC.md)")
    parser.add_argument("--out", default="OPEN_QUESTIONS.json", help="Output JSON path (default: OPEN_QUESTIONS.json in CWD)")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    spec_path = (repo_root / args.spec).resolve() if not Path(args.spec).is_absolute() else Path(args.spec).resolve()

    findings = []
    findings.extend(scan_spec(spec_path))
    findings.extend(scan_repo_structure(repo_root))

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path

    # Normalize for JSON
    payload: list[dict[str, Any]] = []
    for i, f in enumerate(findings, start=1):
        payload.append(
            {
                "id": f"q{i:04d}",
                "kind": f.kind,
                "question": f.question,
                "impact": f.impact,
                "recommended_default": f.recommended_default,
                "requires_confirmation": f.requires_confirmation,
                "source": {
                    "path": f.source_path,
                    "line": f.source_line,
                }
                if f.source_path
                else None,
                "evidence": f.evidence,
            }
        )

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Print a short summary for interactive use
    spec_tbd = sum(1 for f in findings if f.kind == "spec_tbd")
    missing = sum(1 for f in findings if f.kind == "missing_path")
    print(f"Wrote {out_path}")
    print(f"- spec_tbd: {spec_tbd}")
    print(f"- missing_path: {missing}")


if __name__ == "__main__":
    main()
