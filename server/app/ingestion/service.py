from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from pathlib import Path
from uuid import uuid4

from server.app.core import DocVersionRecord, DocumentRecord, RuntimeConfigSnapshot, build_runtime_config
from server.app.storage import DocumentRepository, FileStore, VectorStore
from server.app.storage.vector_indexing import build_embedding_upsert_records

from .chunker import build_chunk_records
from .loader import MarkdownLoader
from .parser import MarkdownParser
from .types import IngestionJob, IngestionResult


class IngestionService:
    MARKDOWN_SUFFIXES = {".md", ".markdown"}

    def __init__(
        self,
        document_repository: DocumentRepository,
        file_store: FileStore,
        runtime_config: RuntimeConfigSnapshot | None = None,
        vector_store: VectorStore | None = None,
    ):
        self.document_repository = document_repository
        self.file_store = file_store
        self.runtime_config = runtime_config or build_runtime_config()
        self.vector_store = vector_store
        self.loader = MarkdownLoader()
        self.parser = MarkdownParser()

    def ingest_file(self, path: str | Path, doc_id: str | None = None) -> IngestionResult:
        loaded = self.loader.load_file(path)
        return self._ingest_loaded(loaded, doc_id=doc_id)

    def ingest_directory(self, path: str | Path, recursive: bool = True) -> list[IngestionResult]:
        return [self.ingest_file(file_path) for file_path in self.discover_markdown_files(path, recursive=recursive)]

    def ingest_text(self, raw_text: str, source_path_hint: str | None = None, doc_id: str | None = None) -> IngestionResult:
        loaded = self.loader.load_text(raw_text, source_path=source_path_hint)
        return self._ingest_loaded(loaded, doc_id=doc_id)

    @classmethod
    def discover_markdown_files(cls, path: str | Path, recursive: bool = True) -> list[Path]:
        root = Path(path).expanduser()
        if not root.exists():
            raise FileNotFoundError(f"ingest path does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"ingest path is not a directory: {root}")
        iterator = root.rglob("*") if recursive else root.glob("*")
        return sorted(
            candidate
            for candidate in iterator
            if candidate.is_file() and candidate.suffix.lower() in cls.MARKDOWN_SUFFIXES
        )

    def _ingest_loaded(self, loaded, doc_id: str | None = None) -> IngestionResult:
        parsed = self.parser.parse(loaded)
        resolved_doc_id = doc_id or self._build_doc_id(loaded.source_path or parsed.title)
        doc_version_id = self._build_doc_version_id(loaded.content_hash)
        snapshot_ref = self.file_store.write_markdown_snapshot(resolved_doc_id, doc_version_id, loaded.raw_text)

        document = DocumentRecord(
            doc_id=resolved_doc_id,
            doc_type=parsed.doc_type,
            title=parsed.title,
            latest_version_id=doc_version_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        doc_version = DocVersionRecord(
            doc_version_id=doc_version_id,
            doc_id=resolved_doc_id,
            content_hash=loaded.content_hash,
            ingest_time=datetime.utcnow(),
            source_path=snapshot_ref,
            size_bytes=loaded.size_bytes,
        )
        chunks = build_chunk_records(loaded=loaded, parsed=parsed, doc_id=resolved_doc_id, doc_version=doc_version)

        self.document_repository.init_schema()
        self.document_repository.upsert_document(document)
        self.document_repository.insert_doc_version(doc_version)
        for chunk in chunks:
            self.document_repository.insert_chunk(chunk)
        if self.vector_store is not None:
            self.vector_store.ensure_collection()
            self.vector_store.upsert_embeddings(build_embedding_upsert_records(chunks, self.runtime_config))

        jobs = [
            IngestionJob(
                job_id=f"job_{uuid4().hex[:12]}",
                job_type="safe_summary_build",
                payload={
                    "chunk_id": chunk.chunk_id,
                    "doc_version_id": chunk.doc_version_id,
                    "summary_prompt_version": self.runtime_config.prompt_versions.safe_summary,
                    "summary_model": self.runtime_config.model_routing.base_model,
                },
            )
            for chunk in chunks
        ]
        return IngestionResult(document=document, doc_version=doc_version, chunks=chunks, jobs=jobs)

    @staticmethod
    def _build_doc_id(seed: str) -> str:
        return f"doc_{sha1(seed.encode('utf-8')).hexdigest()[:12]}"

    @staticmethod
    def _build_doc_version_id(content_hash: str) -> str:
        return f"dv_{sha1(f'{content_hash}:{datetime.utcnow().isoformat()}'.encode('utf-8')).hexdigest()[:12]}"
