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
        retrieval_status = app.state.pda.retrieval_service.provider_status()
        replan_status = app.state.pda.orchestrator_service.replanner.provider_status()
        evaluation_status = app.state.pda.evaluation_service.provider_status()
        sft_status = app.state.pda.sft_service.training_backend_status()
        sft_inference_status = app.state.pda.sft_service.inference_backend_status()
        print(f"app_check_ok root_dir={root_dir}")
        print(f"routes={len(app.routes)}")
        print(f"retrieval_reranker_enabled={retrieval_status['enabled']}")
        print(f"retrieval_reranker_name={retrieval_status['provider_name']}")
        print(f"retrieval_reranker_configured={retrieval_status['configured']}")
        print(f"retrieval_reranker_model={retrieval_status['model']}")
        print(f"retrieval_reranker_base_url={retrieval_status['base_url']}")
        print(f"retrieval_reranker_missing_dependencies={','.join(retrieval_status['missing_dependencies'])}")
        print(f"replan_provider_profile={replan_status['profile_name']}")
        print(f"replan_provider_name={replan_status['provider_name']}")
        print(f"replan_provider_configured={replan_status['configured']}")
        print(f"replan_provider_base_url={replan_status['base_url']}")
        print(f"eval_ragas_provider_name={evaluation_status['ragas']['evaluator_name']}")
        print(f"eval_ragas_provider_configured={evaluation_status['ragas']['configured']}")
        print(f"eval_ragas_provider_base_url={evaluation_status['ragas']['base_url']}")
        print(f"eval_ragas_provider_missing_dependencies={','.join(evaluation_status['ragas']['missing_dependencies'])}")
        print(f"eval_judge_provider_name={evaluation_status['judge']['evaluator_name']}")
        print(f"eval_judge_provider_configured={evaluation_status['judge']['configured']}")
        print(f"eval_judge_provider_base_url={evaluation_status['judge']['base_url']}")
        print(f"eval_judge_provider_missing_dependencies={','.join(evaluation_status['judge']['missing_dependencies'])}")
        print(f"sft_training_backend_name={sft_status['backend_name']}")
        print(f"sft_training_backend_available={sft_status['configured']}")
        print(f"sft_training_backend_script_path={sft_status['script_path']}")
        print(f"sft_training_backend_missing_dependencies={','.join(sft_status['missing_dependencies'])}")
        print(f"sft_inference_backend_name={sft_inference_status['backend_name']}")
        print(f"sft_inference_backend_available={sft_inference_status['configured']}")
        print(f"sft_inference_backend_missing_dependencies={','.join(sft_inference_status['missing_dependencies'])}")
        return
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
