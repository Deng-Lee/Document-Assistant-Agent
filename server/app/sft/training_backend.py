from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from server.app.core import PDABaseModel, PolicyTrainRequest


class PolicyTrainingBackendError(RuntimeError):
    pass


class PolicyTrainingArtifact(PDABaseModel):
    backend_name: str
    schema_version: str
    adapter_path: str
    tokenizer_path: str
    training_summary_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyTrainingBackend(Protocol):
    def run(self, request: PolicyTrainRequest) -> PolicyTrainingArtifact: ...

    def status(self) -> dict[str, object]: ...


class HFLoRAQLoRATrainingBackend:
    backend_name = "hf_lora_qlora_v1"
    required_modules = ("torch", "transformers", "peft", "accelerate")
    optional_modules = ("bitsandbytes",)

    def __init__(
        self,
        script_path: str | Path | None = None,
        python_executable: str | None = None,
    ):
        self.script_path = Path(script_path).resolve() if script_path is not None else _default_script_path()
        self.python_executable = python_executable or sys.executable

    def run(self, request: PolicyTrainRequest) -> PolicyTrainingArtifact:
        if request.training_backend != self.backend_name:
            raise PolicyTrainingBackendError(f"unsupported_training_backend:{request.training_backend}")
        if not self.script_path.exists():
            raise PolicyTrainingBackendError(f"missing_training_script:{self.script_path}")
        command = [
            self.python_executable,
            str(self.script_path),
            "--train",
            str(Path(request.train_path).resolve()),
            "--base_model",
            request.base_model or "",
            "--out",
            str(Path(request.output_path).resolve()),
            "--epochs",
            str(request.epochs),
            "--lr",
            str(request.learning_rate),
            "--batch_size",
            str(request.batch_size),
            "--max_seq_len",
            str(request.max_seq_len),
            "--lora_r",
            str(request.lora_r),
            "--lora_alpha",
            str(request.lora_alpha),
            "--lora_dropout",
            str(request.lora_dropout),
            "--validation_split",
            str(request.validation_split),
            "--eval_steps",
            str(request.eval_steps),
            "--early_stopping_patience",
            str(request.early_stopping_patience),
            "--early_stopping_threshold",
            str(request.early_stopping_threshold),
        ]
        if request.lora_targets:
            command.extend(["--lora_targets", ",".join(request.lora_targets)])
        if request.load_in_4bit:
            command.append("--load_in_4bit")
        completed = subprocess.run(
            command,
            cwd=self.script_path.parent.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown_training_error"
            raise PolicyTrainingBackendError(detail)
        output_dir = Path(request.output_path).resolve()
        adapter_path = output_dir / "adapter"
        tokenizer_path = output_dir / "tokenizer"
        summary_path = output_dir / "training_summary.json"
        if not adapter_path.exists():
            raise PolicyTrainingBackendError(f"missing_adapter_output:{adapter_path}")
        if not tokenizer_path.exists():
            raise PolicyTrainingBackendError(f"missing_tokenizer_output:{tokenizer_path}")
        return PolicyTrainingArtifact(
            backend_name=self.backend_name,
            schema_version=self.backend_name,
            adapter_path=str(adapter_path),
            tokenizer_path=str(tokenizer_path),
            training_summary_path=str(summary_path) if summary_path.exists() else None,
            metadata={
                "script_path": str(self.script_path),
                "python_executable": self.python_executable,
                "load_in_4bit": request.load_in_4bit,
                "lora_targets": list(request.lora_targets),
                "validation_split": request.validation_split,
                "eval_steps": request.eval_steps,
                "early_stopping_patience": request.early_stopping_patience,
                "early_stopping_threshold": request.early_stopping_threshold,
            },
        )

    def status(self) -> dict[str, object]:
        required = {name: _module_available(name) for name in self.required_modules}
        optional = {name: _module_available(name) for name in self.optional_modules}
        missing_dependencies = [name for name, available in required.items() if not available]
        return {
            "backend_name": self.backend_name,
            "script_path": str(self.script_path),
            "script_exists": self.script_path.exists(),
            "configured": self.script_path.exists() and all(required.values()),
            "missing_dependencies": missing_dependencies,
            "qlora_supported": optional["bitsandbytes"],
            "required_modules": required,
            "optional_modules": optional,
        }


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _default_script_path() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "train_policy_lora.py"
