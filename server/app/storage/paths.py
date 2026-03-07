from __future__ import annotations

from pathlib import Path

from server.app.core import PDABaseModel


class StoragePaths(PDABaseModel):
    root: Path
    sqlite_dir: Path
    chroma_dir: Path
    filestore_dir: Path
    traces_dir: Path
    jobs_dir: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "StoragePaths":
        root_path = Path(root)
        data_root = root_path / "data"
        return cls(
            root=root_path,
            sqlite_dir=data_root / "sqlite",
            chroma_dir=data_root / "chroma",
            filestore_dir=data_root / "filestore",
            traces_dir=data_root / "traces",
            jobs_dir=data_root / "jobs",
        )

    def ensure_directories(self) -> None:
        for path in (
            self.sqlite_dir,
            self.chroma_dir,
            self.filestore_dir,
            self.traces_dir,
            self.jobs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def sqlite_db_path(self) -> Path:
        return self.sqlite_dir / "app.db"
