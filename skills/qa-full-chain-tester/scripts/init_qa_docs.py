#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import textwrap


MODULES = [
    "ingest",
    "query",
    "cross-encoder",
    "sft",
    "rerank",
    "evaluate",
    "trace",
]


@dataclass(frozen=True)
class FixtureDoc:
    path: Path
    doc_type: str
    title: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize QA_TEST.md and QA_TEST_PROGRESS.md from test/fixtures.")
    parser.add_argument("--repo-root", default=".", help="Repository root containing test/fixtures.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing QA docs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    fixtures_root = repo_root / "test" / "fixtures"
    if not fixtures_root.exists():
        raise SystemExit(f"Missing fixtures directory: {fixtures_root}")

    fixtures = load_fixtures(fixtures_root)
    if not fixtures:
        raise SystemExit("No markdown fixtures found under test/fixtures.")

    qa_test_path = repo_root / "QA_TEST.md"
    qa_progress_path = repo_root / "QA_TEST_PROGRESS.md"

    if not args.force:
        for target in (qa_test_path, qa_progress_path):
            if target.exists():
                raise SystemExit(f"{target} already exists. Re-run with --force to overwrite.")

    qa_test_path.write_text(render_qa_test(fixtures), encoding="utf-8")
    qa_progress_path.write_text(render_qa_progress(fixtures), encoding="utf-8")

    print(f"qa_docs_initialized fixture_count={len(fixtures)}")
    print(qa_test_path.relative_to(repo_root))
    print(qa_progress_path.relative_to(repo_root))


def load_fixtures(fixtures_root: Path) -> list[FixtureDoc]:
    docs: list[FixtureDoc] = []
    for path in sorted(fixtures_root.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(raw)
        docs.append(
            FixtureDoc(
                path=path,
                doc_type=frontmatter.get("type", ""),
                title=frontmatter.get("title", path.stem),
            )
        )
    return docs


def parse_frontmatter(raw: str) -> dict[str, str]:
    lines = raw.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}
    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    return frontmatter


def render_qa_test(fixtures: list[FixtureDoc]) -> str:
    bjj = [doc for doc in fixtures if doc.doc_type == "BJJ"]
    notes = [doc for doc in fixtures if doc.doc_type == "notes"]
    lines = [
        "# QA_TEST",
        "",
        "Canonical adversarial QA plan generated from `test/fixtures/`.",
        "",
        "## Fixture Inventory",
        "",
        f"- BJJ fixtures: {len(bjj)}",
        f"- Notes fixtures: {len(notes)}",
        "",
    ]
    for module in MODULES:
        lines.extend(render_module_cases(module, bjj, notes))
    return "\n".join(lines).rstrip() + "\n"


def render_module_cases(module: str, bjj: list[FixtureDoc], notes: list[FixtureDoc]) -> list[str]:
    cases = case_templates(module, bjj, notes)
    lines = [f"## Module: {module}", ""]
    for case in cases:
        lines.extend(
            [
                f"### Case ID: {case['case_id']}",
                f"- Status: pending",
                f"- Target: {case['target']}",
                f"- Fixture(s): {case['fixtures']}",
                f"- Setup command: `{case['setup_command']}`",
                f"- Test command: `{case['test_command']}`",
                f"- Assertion focus: {case['assertion_focus']}",
                f"- Failure evidence required: {case['failure_evidence']}",
                "",
            ]
        )
    return lines


def case_templates(module: str, bjj: list[FixtureDoc], notes: list[FixtureDoc]) -> list[dict[str, str]]:
    bjj_first = rel(bjj[0].path) if bjj else "test/fixtures/bjj"
    notes_first = rel(notes[0].path) if notes else "test/fixtures/notes"
    mixed_root = "test/fixtures"
    templates = {
        "ingest": [
            {
                "case_id": "ingest-bjj-single",
                "target": "Verify a single BJJ markdown ingests cleanly and produces chunks/jobs.",
                "fixtures": bjj_first,
                "setup_command": "python3 -m server.app.api --host 127.0.0.1 --port 8000",
                "test_command": f"curl -s -X POST http://127.0.0.1:8000/api/ingest/file -H 'Content-Type: application/json' -d '{{\"path\":\"{bjj_first}\"}}'",
                "assertion_focus": "doc_id/doc_version_id/chunk_ids/jobs are present and non-empty.",
                "failure_evidence": "Capture the raw response body and any server-side validation errors.",
            },
            {
                "case_id": "ingest-mixed-directory",
                "target": "Verify recursive directory ingest handles both BJJ and notes fixtures without silent skips.",
                "fixtures": mixed_root,
                "setup_command": "python3 -m server.app.api --host 127.0.0.1 --port 8000",
                "test_command": f"curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{{\"path\":\"{mixed_root}\",\"recursive\":true}}'",
                "assertion_focus": "imported_count matches actual markdown count and each result includes source_path/jobs.",
                "failure_evidence": "Capture the full JSON result and compare it against fixture inventory counts.",
            },
        ],
        "query": [
            {
                "case_id": "query-bjj-retrieval",
                "target": "Probe whether BJJ retrieval pulls the correct turtle/escape evidence from real fixture text.",
                "fixtures": bjj_first,
                "setup_command": f"curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{{\"path\":\"{mixed_root}\",\"recursive\":true}}'",
                "test_command": "curl -s -X POST http://127.0.0.1:8000/api/retrieve -H 'Content-Type: application/json' -d '{\"query_text\":\"我在 turtle 下位被抓袖子时怎么逃脱？\",\"mode\":\"full\"}'",
                "assertion_focus": "Evidence pack contains BJJ evidence with matching turtle/escape metadata, not note fragments.",
                "failure_evidence": "Record evidence ids, doc_type, and summaries exactly as returned by the endpoint.",
            },
            {
                "case_id": "query-notes-retrieval",
                "target": "Probe whether notes retrieval surfaces literary material instead of BJJ logs.",
                "fixtures": notes_first,
                "setup_command": f"curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{{\"path\":\"{mixed_root}\",\"recursive\":true}}'",
                "test_command": "curl -s -X POST http://127.0.0.1:8000/api/retrieve -H 'Content-Type: application/json' -d '{\"query_text\":\"Borges, mirrors, and memory\",\"mode\":\"full\"}'",
                "assertion_focus": "Returned evidence belongs to notes fixtures and carries relevant textual summaries.",
                "failure_evidence": "Paste the raw evidence pack and identify any domain bleed-through.",
            },
        ],
        "cross-encoder": [
            {
                "case_id": "cross-encoder-presence",
                "target": "Determine whether a true cross-encoder stage exists and can be invoked from the repo.",
                "fixtures": mixed_root,
                "setup_command": "rg -n \"cross-encoder|cross_encoder|rerank\" server scripts web",
                "test_command": "python3 -m server.app.api --check",
                "assertion_focus": "Expect an explicit runnable path or record a blocker that the module is absent.",
                "failure_evidence": "Quote the exact terminal lines proving presence or absence; do not infer capabilities.",
            }
        ],
        "sft": [
            {
                "case_id": "sft-export-and-trainability",
                "target": "Verify the repo can export SFT data and expose a real trainable request path from fixture-derived traces.",
                "fixtures": bjj_first,
                "setup_command": f"curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{{\"path\":\"{mixed_root}\",\"recursive\":true}}'",
                "test_command": "python3 -m server.app.api --check",
                "assertion_focus": "Training backend readiness, export path, and required dependency gaps are explicit and reproducible.",
                "failure_evidence": "Record missing dependencies, backend status, and any export/train errors verbatim.",
            }
        ],
        "rerank": [
            {
                "case_id": "rerank-ordering-behavior",
                "target": "Verify reranking changes or preserves ordering for a mixed-domain retrieval in a defensible way.",
                "fixtures": mixed_root,
                "setup_command": f"curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{{\"path\":\"{mixed_root}\",\"recursive\":true}}'",
                "test_command": "curl -s -X POST http://127.0.0.1:8000/api/retrieve -H 'Content-Type: application/json' -d '{\"query_text\":\"escape and memory\",\"mode\":\"full\"}'",
                "assertion_focus": "Ordering, ranks, and module notes expose rerank behavior instead of opaque results.",
                "failure_evidence": "Capture the returned rank signals or the absence of rerank metadata exactly.",
            }
        ],
        "evaluate": [
            {
                "case_id": "evaluate-base-run",
                "target": "Run an eval pass on fixture-derived traces and verify metrics, external stages, and manual rubric defaults are explicit.",
                "fixtures": mixed_root,
                "setup_command": "python3 -m server.app.api --check",
                "test_command": "python3 scripts/run_smoke_tests.py --profile fake",
                "assertion_focus": "Evaluation output must expose run_status, hard metrics, and stage status without silent skips.",
                "failure_evidence": "Paste the exact smoke/eval output lines and any eval result JSON used in diagnosis.",
            }
        ],
        "trace": [
            {
                "case_id": "trace-persistence-and-replay",
                "target": "Verify trace detail and replay expose enough real evidence to debug a fixture-based run.",
                "fixtures": mixed_root,
                "setup_command": "python3 -m server.app.api --check",
                "test_command": "curl -s http://127.0.0.1:8000/api/traces",
                "assertion_focus": "Traces exist, trace detail is retrievable, and replay can be invoked against a concrete trace id.",
                "failure_evidence": "Capture raw trace ids, trace detail payloads, and replay responses from terminal output.",
            }
        ],
    }
    return templates[module]


def render_qa_progress(fixtures: list[FixtureDoc]) -> str:
    inventory = ", ".join(rel(doc.path) for doc in fixtures)
    return textwrap.dedent(
        f"""\
        # QA_TEST_PROGRESS

        Track execution progress for the serial adversarial QA workflow.

        ## Run Meta

        - Scope: ingest -> query -> cross-encoder -> sft -> rerank -> evaluate -> trace
        - Fixture inventory: {inventory}
        - Max repair retries per failing case: 3
        - Current module: pending
        - Overall status: pending

        ## Execution Log

        ### Entry Template

        - Module:
        - Case ID:
        - Attempt:
        - Status:
        - Command:
        - Terminal Evidence:
        - Note:
        - Diagnosis:
        - Fix Applied:
        - Re-run Required:
        """
    )


def rel(path: Path) -> str:
    normalized = path.as_posix()
    if "/test/" in normalized:
        return "test/" + normalized.split("/test/", 1)[-1]
    return normalized


if __name__ == "__main__":
    main()
