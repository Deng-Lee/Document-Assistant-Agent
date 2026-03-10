from __future__ import annotations

import importlib.util
import json
from typing import Any, Protocol

from pydantic import Field

from server.app.core import PDABaseModel

from .prompting import build_policy_prompt


class PolicyInferenceBackendError(RuntimeError):
    pass


class PolicyInferenceResult(PDABaseModel):
    output: dict[str, Any]
    token_usage: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyInferenceBackend(Protocol):
    def generate(self, artifact: dict[str, Any], input_payload: dict[str, Any], max_new_tokens: int = 1024) -> PolicyInferenceResult: ...

    def status(self) -> dict[str, object]: ...


class HFLoRAQLoRAInferenceBackend:
    backend_name = "hf_lora_qlora_inference_v1"
    required_modules = ("torch", "transformers", "peft")

    def __init__(self):
        self._cache_key: tuple[str, str, str] | None = None
        self._cached_model = None
        self._cached_tokenizer = None

    def generate(self, artifact: dict[str, Any], input_payload: dict[str, Any], max_new_tokens: int = 1024) -> PolicyInferenceResult:
        status = self.status()
        if not status["configured"]:
            missing = ",".join(status["missing_dependencies"])
            raise PolicyInferenceBackendError(f"missing_inference_dependencies:{missing}")

        base_model = str(artifact.get("base_model") or "").strip()
        adapter_path = str(artifact.get("adapter_path") or "").strip()
        tokenizer_path = str(artifact.get("tokenizer_path") or "").strip()
        if not base_model:
            raise PolicyInferenceBackendError("missing_base_model")
        if not adapter_path:
            raise PolicyInferenceBackendError("missing_adapter_path")
        if not tokenizer_path:
            raise PolicyInferenceBackendError("missing_tokenizer_path")

        torch, model, tokenizer = self._load_model(base_model, adapter_path, tokenizer_path)
        prompt_text = build_policy_prompt(input_payload)
        encoded = tokenizer(prompt_text, return_tensors="pt")
        if hasattr(model, "device"):
            encoded = {key: value.to(model.device) for key, value in encoded.items()}
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        prompt_length = encoded["input_ids"].shape[1]
        new_tokens = generated[0][prompt_length:]
        completion_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        output = _extract_json_object(completion_text)
        return PolicyInferenceResult(
            output=output,
            token_usage={
                "prompt_tokens": int(encoded["input_ids"].shape[1]),
                "completion_tokens": int(new_tokens.shape[0]),
            },
            metadata={
                "backend_name": self.backend_name,
                "base_model": base_model,
                "adapter_path": adapter_path,
                "tokenizer_path": tokenizer_path,
            },
        )

    def status(self) -> dict[str, object]:
        required = {name: _module_available(name) for name in self.required_modules}
        missing_dependencies = [name for name, available in required.items() if not available]
        return {
            "backend_name": self.backend_name,
            "configured": not missing_dependencies,
            "missing_dependencies": missing_dependencies,
            "required_modules": required,
        }

    def _load_model(self, base_model: str, adapter_path: str, tokenizer_path: str):
        key = (base_model, adapter_path, tokenizer_path)
        if self._cache_key == key and self._cached_model is not None and self._cached_tokenizer is not None:
            torch = _import_module("torch")
            return torch, self._cached_model, self._cached_tokenizer

        torch = _import_module("torch")
        peft = _import_module("peft")
        transformers = _import_module("transformers")
        tokenizer = transformers.AutoTokenizer.from_pretrained(tokenizer_path, use_fast=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model_kwargs: dict[str, Any] = {}
        if torch.cuda.is_available():
            model_kwargs["torch_dtype"] = torch.float16
        model = transformers.AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
        model = peft.PeftModel.from_pretrained(model, adapter_path)
        if torch.cuda.is_available():
            model = model.to("cuda")
        model.eval()
        self._cache_key = key
        self._cached_model = model
        self._cached_tokenizer = tokenizer
        return torch, model, tokenizer


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise PolicyInferenceBackendError("empty_policy_completion")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise PolicyInferenceBackendError("policy_completion_not_json") from None
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise PolicyInferenceBackendError("policy_completion_not_object")
    return parsed


def _import_module(name: str):
    module = __import__(name)
    return module


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None
