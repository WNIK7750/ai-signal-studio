from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ai_signal_api.config import Settings, get_settings
from ai_signal_api.database import Base, build_engine, build_session_factory
from ai_signal_api.integrations.llm.chat import OpenAICompatibleModelChat
from ai_signal_api.modules.automation.service import seed_common_plans
from ai_signal_api.modules.collection.service import (
    seed_demo_sources as seed_default_sources,
    seed_live_sources,
)
from ai_signal_api.modules.models.service import (
    build_model_configuration_service,
)
from ai_signal_api.capabilities.core import CapabilityExecutionError
from ai_signal_api.routers import (
    agent,
    automation,
    cards,
    models,
    review,
    sources,
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
    runtime_settings = base_settings.model_copy(
        update={
            "database_url": database_url or base_settings.database_url,
            "enable_scheduler": enable_scheduler,
        }
    )
    engine = build_engine(runtime_settings.database_url)
    session_factory = build_session_factory(engine)
    model_configuration = build_model_configuration_service(
        runtime_settings
    )
    source_seed_mode = (
        "demo"
        if seed_demo_sources is True
        else "none"
        if seed_demo_sources is False
        else runtime_settings.source_seed_mode
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as session:
            if source_seed_mode == "demo":
                seed_default_sources(session)
            elif source_seed_mode == "live":
                seed_live_sources(session)
            seed_common_plans(session)

        if runtime_settings.enable_scheduler:
            scheduler, sync_task = build_scheduler(
                session_factory,
                runtime_settings,
            )
            app.state.scheduler = scheduler
            app.state.sync_scheduled_task = sync_task
            scheduler.start()
        try:
            yield
        finally:
            if app.state.scheduler is not None:
                app.state.scheduler.shutdown(wait=False)
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
    app.state.scheduler = None
    app.state.sync_scheduled_task = lambda _task_id: None

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
    app.include_router(automation.router)
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
