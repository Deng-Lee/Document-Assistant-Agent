from __future__ import annotations

from pathlib import Path

from server.app.core import TraceRecord

from .serialization import model_to_dict, read_json_file, write_json_file


class JSONTraceStore:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def write_trace(self, trace: TraceRecord) -> str:
        target_path = self.root_dir / f"{trace.trace_id}.json"
        write_json_file(target_path, model_to_dict(trace))
        return str(target_path)

    def read_trace(self, trace_id: str) -> TraceRecord:
        payload = read_json_file(self.root_dir / f"{trace_id}.json")
        return TraceRecord(**payload)

    def list_trace_ids(self) -> list[str]:
        return sorted(path.stem for path in self.root_dir.glob("*.json"))
