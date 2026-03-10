#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repository unit tests and smoke tests.")
    parser.add_argument(
        "--profile",
        choices=["fake", "real"],
        default=os.getenv("PDA_MODEL_PROFILE", "fake"),
        help="Model/settings profile to activate before test commands.",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "unit", "smoke"],
        default="all",
        help="Which test layers to run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = dict(os.environ)
    env["PDA_MODEL_PROFILE"] = args.profile
    repo_root = Path(__file__).resolve().parent.parent

    commands: list[list[str]] = []
    if args.mode in {"all", "unit"}:
        commands.append(["npm", "--prefix", "web", "run", "contracts:check"])
        commands.append(["npm", "--prefix", "web", "run", "test"])
    if args.mode == "all":
        commands.append(["npm", "--prefix", "web", "run", "test:e2e"])
    if args.mode in {"all", "unit"}:
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "server/tests", "-p", "test_*.py"])
    if args.mode in {"all", "smoke"}:
        commands.append([sys.executable, "scripts/run_smoke_tests.py", "--profile", args.profile])

    for command in commands:
        print(f"running={' '.join(command)}")
        subprocess.run(command, cwd=repo_root, env=env, check=True)

    print("test_suite_ok")


if __name__ == "__main__":
    main()
