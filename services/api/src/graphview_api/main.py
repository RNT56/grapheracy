from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from graphview_api.auth import CurrentUser, get_current_user
from graphview_api.settings import Settings, get_settings
from graphview_api.version import VERSION


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Graphview API", version=VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "graphview-api"}

    @app.get("/version")
    async def version(settings: Settings = Depends(get_settings)) -> dict[str, str]:
        return {"service": "graphview-api", "version": VERSION, "environment": settings.environment}

    @app.get("/graph")
    async def graph(user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
        return {"project": None, "nodes": [], "edges": [], "user": user.id}

    @app.get("/sources")
    async def sources() -> dict[str, list[object]]:
        return {"sources": []}

    @app.get("/ingestion-runs")
    async def ingestion_runs() -> dict[str, list[object]]:
        return {"ingestion_runs": []}

    @app.get("/proposals")
    async def proposals() -> dict[str, list[object]]:
        return {"proposals": []}

    @app.get("/review-decisions")
    async def review_decisions() -> dict[str, list[object]]:
        return {"review_decisions": []}

    return app


app = create_app()
