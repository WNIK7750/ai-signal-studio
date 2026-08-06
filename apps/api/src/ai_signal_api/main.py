from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ai_signal_api.config import Settings, get_settings
from ai_signal_api.database import (
    Base,
    build_engine,
    build_session_factory,
    ensure_runtime_schema,
)
from ai_signal_api.integrations.llm.chat import OpenAICompatibleModelChat
from ai_signal_api.agent_runtime.contracts import WORKFLOW_VERSION
from ai_signal_api.agent_runtime.harness import (
    RecoveryScanner,
    build_sqlite_checkpointer,
    process_turn,
)
from ai_signal_api.modules.automation.service import seed_common_plans
from ai_signal_api.modules.collection.service import (
    seed_demo_sources as seed_default_sources,
    seed_live_sources,
)
from ai_signal_api.modules.models.service import (
    build_model_configuration_service,
)
from ai_signal_api.modules.agent_assets.transcription import (
    FakeRealtimeTranscriptionProvider,
)
from ai_signal_api.modules.agent_assets.agent_packs import (
    seed_default_agent_pack,
)
from langgraph.checkpoint.memory import MemorySaver
from ai_signal_api.capabilities.core import CapabilityExecutionError
from ai_signal_api.routers import (
    agent,
    agent_assets,
    automation,
    cards,
    information,
    models,
    review,
    sources,
    tasks,
    timeline,
)
from ai_signal_api.scheduler import build_scheduler


def create_app(
    database_url: str | None = None,
    *,
    settings: Settings | None = None,
    seed_demo_sources: bool | None = None,
    enable_scheduler: bool = False,
) -> FastAPI:
    base_settings = settings or get_settings()
    requested_source_seed_mode = (
        "demo"
        if seed_demo_sources is True
        else "none"
        if seed_demo_sources is False
        else base_settings.source_seed_mode
    )
    runtime_settings = base_settings.model_copy(
        update={
            "database_url": database_url or base_settings.database_url,
            "enable_scheduler": enable_scheduler,
            "source_seed_mode": requested_source_seed_mode,
        }
    )
    engine = build_engine(runtime_settings.database_url)
    session_factory = build_session_factory(engine)
    model_configuration = build_model_configuration_service(
        runtime_settings
    )
    source_seed_mode = runtime_settings.source_seed_mode
    if runtime_settings.agent_checkpoint_path is not None:
        checkpoint_path = runtime_settings.agent_checkpoint_path
    elif runtime_settings.database_url.startswith("sqlite:///"):
        database_path = runtime_settings.database_url.removeprefix(
            "sqlite:///"
        )
        checkpoint_path = (
            Path(database_path).with_name("agent-checkpoints.db")
            if database_path != ":memory:"
            else Path("data/agent-checkpoints.db")
        )
    else:
        checkpoint_path = Path("data/agent-checkpoints.db")
    agent_checkpointer, checkpoint_connection = build_sqlite_checkpointer(
        checkpoint_path
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        ensure_runtime_schema(engine)
        with session_factory() as session:
            if source_seed_mode == "demo":
                seed_default_sources(session)
            elif source_seed_mode == "live":
                seed_live_sources(session)
            seed_common_plans(session)
            seed_default_agent_pack(
                session,
                runtime_settings.agent_pack_root,
            )
            recoverable_turn_ids = RecoveryScanner(session).scan()

        for recoverable_turn_id in recoverable_turn_ids:
            process_turn(
                session_factory,
                runtime_settings,
                model_configuration,
                agent_checkpointer,
                recoverable_turn_id,
                None,
            )

        if runtime_settings.enable_scheduler:
            scheduler, sync_task, sync_collection_task = build_scheduler(
                session_factory,
                runtime_settings,
            )
            app.state.scheduler = scheduler
            app.state.sync_scheduled_task = sync_task
            app.state.sync_collection_task = sync_collection_task
            scheduler.start()
        try:
            yield
        finally:
            if app.state.scheduler is not None:
                app.state.scheduler.shutdown(wait=False)
            checkpoint_connection.close()
            engine.dispose()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.model_chat = OpenAICompatibleModelChat(runtime_settings)
    app.state.model_configuration = model_configuration
    app.state.agent_checkpointer = agent_checkpointer
    app.state.poster_checkpointer = MemorySaver()
    app.state.transcription_provider = FakeRealtimeTranscriptionProvider()
    app.state.json_loads = json.loads
    app.state.scheduler = None
    app.state.sync_scheduled_task = lambda _task_id: None
    app.state.sync_collection_task = lambda _task_id: None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sources.router)
    app.include_router(timeline.router)
    app.include_router(agent.router)
    app.include_router(agent_assets.router)
    app.include_router(automation.router)
    app.include_router(tasks.router)
    app.include_router(information.router)
    app.include_router(models.router)
    app.include_router(review.router)
    app.include_router(cards.router)

    @app.exception_handler(CapabilityExecutionError)
    def capability_error(
        _request: Request,
        error: CapabilityExecutionError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.code},
        )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        default_model = (
            model_configuration.select_for_request(None).effective_model
        )
        return {
            "status": "ok",
            "workflow_version": WORKFLOW_VERSION,
            "providers": {
                "llm": {
                    "provider": default_model.provider,
                    "configured": (
                        default_model.provider == "heuristic"
                        or default_model.has_api_key
                    ),
                    "model": default_model.model_id,
                },
                "search": {
                    "configured": runtime_settings.search_api_key is not None
                    and bool(
                        runtime_settings.search_api_key.get_secret_value().strip()
                    )
                },
                "github": {
                    "configured": runtime_settings.github_token is not None
                    and bool(
                        runtime_settings.github_token.get_secret_value().strip()
                    )
                },
            },
        }

    return app


app = create_app(enable_scheduler=True)
