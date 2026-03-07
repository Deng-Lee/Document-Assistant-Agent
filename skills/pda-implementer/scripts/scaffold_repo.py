#!/usr/bin/env python3
import argparse
from pathlib import Path


DIRS = [
    "server/app/api",
    "server/app/core",
    "server/app/ingestion",
    "server/app/retrieval",
    "server/app/orchestrator",
    "server/app/agents/bjj_coach",
    "server/app/agents/literary",
    "server/app/observability",
    "server/app/evaluation",
    "server/app/sft",
    "server/app/storage",
    "server/app/jobs",
    "server/tests",
    "web/app",
    "web/components",
    "web/lib",
    "datasets/golden",
    "datasets/sft",
    "data/sqlite",
    "data/chroma",
    "data/filestore",
    "data/traces",
    "data/jobs",
    "scripts",
]

PLACEHOLDER_FILES = {
    "server/app/__init__.py": "",
    "server/app/api/__init__.py": "",
    "server/app/core/__init__.py": "",
    "server/app/ingestion/__init__.py": "",
    "server/app/retrieval/__init__.py": "",
    "server/app/orchestrator/__init__.py": "",
    "server/app/agents/__init__.py": "",
    "server/app/agents/bjj_coach/__init__.py": "",
    "server/app/agents/literary/__init__.py": "",
    "server/app/observability/__init__.py": "",
    "server/app/evaluation/__init__.py": "",
    "server/app/sft/__init__.py": "",
    "server/app/storage/__init__.py": "",
    "server/app/jobs/__init__.py": "",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold repo directories for the PDA project (dry-run by default).")
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--apply", action="store_true", help="Actually create directories/files")
    parser.add_argument("--force", action="store_true", help="Overwrite placeholder files if they exist")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    actions = []
    for d in DIRS:
        p = root / d
        if not p.exists():
            actions.append(("mkdir", p))

    for rel, content in PLACEHOLDER_FILES.items():
        p = root / rel
        if not p.exists():
            actions.append(("write", p, content))

    if not actions:
        print("No scaffold actions needed.")
        return

    if not args.apply:
        print("DRY RUN. Planned actions:")
        for a in actions:
            if a[0] == "mkdir":
                print(f"- mkdir -p {a[1]}")
            else:
                print(f"- write {a[1]}")
        print("\nRun with --apply to perform these actions.")
        return

    for a in actions:
        if a[0] == "mkdir":
            a[1].mkdir(parents=True, exist_ok=True)
        else:
            path, content = a[1], a[2]
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and not args.force:
                continue
            path.write_text(content, encoding="utf-8")

    print(f"Applied {len(actions)} scaffold actions under {root}")


if __name__ == "__main__":
    main()
