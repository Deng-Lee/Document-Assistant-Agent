from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import Field

from server.app.agents import BJJCoachService, LiteraryService
from server.app.core import (
    PDABaseModel,
    ProfileSummary,
    build_runtime_config,
)
from server.app.evaluation import EvaluationService
from server.app.ingestion import IngestionService
from server.app.jobs import JobService
from server.app.observability import TraceRecorder
from server.app.orchestrator import ConversationState, OrchestratorService
from server.app.retrieval import RetrievalService
from server.app.sft import SFTService
from server.app.storage import (
    ChromaVectorStoreAdapter,
    JSONTraceStore,
    LocalFileStore,
    SQLiteJobRepository,
    SQLiteDocumentRepository,
    SQLiteGoldenCaseRepository,
    SQLiteStore,
    StoragePaths,
)


class StoredConversation(PDABaseModel):
    conversation_id: str
    state: ConversationState = Field(default_factory=ConversationState)
    turns: list[dict] = Field(default_factory=list)


class AppState(PDABaseModel):
    root_dir: Path
    storage_paths: StoragePaths
    runtime_config: object
    document_repository: object
    golden_case_repository: object
    job_repository: object
    file_store: object
    trace_store: object
    ingestion_service: object
    retrieval_service: object
    orchestrator_service: object
    job_service: object
    bjj_coach_service: object
    literary_service: object
    evaluation_service: object
    sft_service: object
    current_profile: ProfileSummary
    conversations: dict[str, StoredConversation] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def get_or_create_conversation(self, conversation_id: str | None = None) -> StoredConversation:
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]
        resolved = conversation_id or f"conv_{uuid4().hex[:12]}"
        conversation = StoredConversation(conversation_id=resolved)
        self.conversations[resolved] = conversation
        return conversation


def create_app_state(root_dir: str | Path) -> AppState:
    root = Path(root_dir).resolve()
    storage_paths = StoragePaths.from_root(root)
    storage_paths.ensure_directories()

    sqlite_store = SQLiteStore(storage_paths.sqlite_db_path)
    document_repository = SQLiteDocumentRepository(sqlite_store)
    document_repository.init_schema()
    golden_case_repository = SQLiteGoldenCaseRepository(sqlite_store)
    job_repository = SQLiteJobRepository(sqlite_store)
    file_store = LocalFileStore(storage_paths.filestore_dir)
    trace_store = JSONTraceStore(storage_paths.traces_dir)
    vector_store = ChromaVectorStoreAdapter(storage_paths.chroma_dir, collection_name="chunks")
    vector_store.ensure_collection()

    runtime_config = build_runtime_config()
    retrieval_service = RetrievalService(document_repository, vector_store=vector_store, runtime_config=runtime_config)
    orchestrator_service = OrchestratorService(retrieval_service, runtime_config=runtime_config)
    job_service = JobService(document_repository, job_repository, runtime_config=runtime_config, vector_store=vector_store)

    return AppState(
        root_dir=root,
        storage_paths=storage_paths,
        runtime_config=runtime_config,
        document_repository=document_repository,
        golden_case_repository=golden_case_repository,
        job_repository=job_repository,
        file_store=file_store,
        trace_store=trace_store,
        ingestion_service=IngestionService(
            document_repository,
            file_store,
            runtime_config=runtime_config,
            vector_store=vector_store,
        ),
        retrieval_service=retrieval_service,
        orchestrator_service=orchestrator_service,
        job_service=job_service,
        bjj_coach_service=BJJCoachService(runtime_config=runtime_config),
        literary_service=LiteraryService(),
        evaluation_service=EvaluationService(
            trace_store=trace_store,
            golden_case_repository=golden_case_repository,
            repo_root=root,
        ),
        sft_service=SFTService(trace_store=trace_store),
        current_profile=ProfileSummary(profile_version_id="profile_default"),
    )
