from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from graphview_api.auth import CurrentUser, get_current_user
from graphview_api.db import create_app_engine
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    ExportBundle,
    GraphOut,
    ImportBundle,
    IngestionRunOut,
    ProposalCreate,
    ProposalOut,
    ReviewDecisionCreate,
    ReviewDecisionOut,
    SourceCreate,
    SourceOut,
    SourceUpdate,
)
from graphview_api.settings import Settings, get_settings
from graphview_api.version import VERSION


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Graphview API", version=VERSION)
    repository = GraphRepository(create_app_engine(settings.database_url))
    repository.initialize()
    app.state.repository = repository

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

    def repo() -> GraphRepository:
        return app.state.repository

    @app.get("/version")
    async def version(settings: Settings = Depends(get_settings)) -> dict[str, str]:
        return {"service": "graphview-api", "version": VERSION, "environment": settings.environment}

    @app.get("/graph", response_model=GraphOut)
    async def graph(
        user: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        project, nodes, edges = repository.graph()
        return {"project": project, "nodes": nodes, "edges": edges, "user": user.id}

    @app.get("/sources")
    async def sources(
        q: str | None = Query(default=None),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[SourceOut]]:
        return {"sources": repository.list_sources(q)}

    @app.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
    async def create_source(
        payload: SourceCreate,
        _: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_source(payload)

    @app.patch("/sources/{source_id}", response_model=SourceOut)
    async def update_source(
        source_id: str,
        payload: SourceUpdate,
        _: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        source = repository.update_source(source_id, payload)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return source

    @app.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_source(
        source_id: str,
        _: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> None:
        if not repository.delete_source(source_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    @app.get("/ingestion-runs")
    async def ingestion_runs(
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[IngestionRunOut]]:
        return {"ingestion_runs": repository.list_ingestion_runs()}

    @app.get("/proposals")
    async def proposals(repository: GraphRepository = Depends(repo)) -> dict[str, list[ProposalOut]]:
        return {"proposals": repository.list_proposals()}

    @app.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_proposal(
        payload: ProposalCreate,
        user: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.create_proposal(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error

    @app.get("/review-decisions")
    async def review_decisions(
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ReviewDecisionOut]]:
        return {"review_decisions": repository.list_review_decisions()}

    @app.post("/review-decisions", response_model=ReviewDecisionOut, status_code=status.HTTP_201_CREATED)
    async def create_review_decision(
        payload: ReviewDecisionCreate,
        user: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.review(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found") from error

    @app.get("/search")
    async def search(
        q: str = Query(min_length=1),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[object]]:
        return repository.search(q)

    @app.get("/export", response_model=ExportBundle)
    async def export(repository: GraphRepository = Depends(repo)) -> dict:
        return repository.export_bundle()

    @app.post("/import", response_model=ExportBundle)
    async def import_bundle(
        payload: ImportBundle,
        user: CurrentUser = Depends(get_current_user),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        for source in payload.sources:
            repository.create_source(source)
        for proposal in payload.proposals:
            repository.create_proposal(proposal, user.id)
        return repository.export_bundle()

    return app


app = create_app()
