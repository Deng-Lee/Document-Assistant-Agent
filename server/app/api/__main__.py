from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .app import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Personal Document Assistant API server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface for the local API server.")
    parser.add_argument("--port", type=int, default=8000, help="Port for the local API server.")
    parser.add_argument(
        "--root-dir",
        default=".",
        help="Runtime root used for data/, traces/, and other mutable state.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Instantiate the app and print the resolved runtime root without starting uvicorn.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = Path(args.root_dir).resolve()
    app = create_app(root_dir)
    if args.check:
        replan_status = app.state.pda.orchestrator_service.replanner.provider_status()
        print(f"app_check_ok root_dir={root_dir}")
        print(f"routes={len(app.routes)}")
        print(f"replan_provider_profile={replan_status['profile_name']}")
        print(f"replan_provider_name={replan_status['provider_name']}")
        print(f"replan_provider_configured={replan_status['configured']}")
        print(f"replan_provider_base_url={replan_status['base_url']}")
        return
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
