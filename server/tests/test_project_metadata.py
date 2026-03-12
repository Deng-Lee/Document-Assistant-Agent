from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


class ProjectMetadataTests(unittest.TestCase):
    def test_base_dependencies_include_cross_encoder_ragas_and_sft_runtime(self) -> None:
        project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
        payload = tomllib.loads(project_file.read_text(encoding="utf-8"))

        dependencies = set(payload["project"]["dependencies"])

        self.assertIn("accelerate>=0.28,<2.0", dependencies)
        self.assertIn("datasets>=2.18,<4.0", dependencies)
        self.assertIn("langchain-openai>=0.1,<1.0", dependencies)
        self.assertIn("peft>=0.10,<1.0", dependencies)
        self.assertIn("ragas>=0.1,<1.0", dependencies)
        self.assertIn("torch>=2.2,<3.0", dependencies)
        self.assertIn("transformers>=4.40,<5.0", dependencies)
