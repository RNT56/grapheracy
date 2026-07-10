from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.ingestion import EMBEDDING_MODEL, build_document, embed_text, generate_proposals
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    AgentActionApprovalCreate,
    AgentActionProposalOut,
    AgentRunCreate,
    GraphQueryAnswerOut,
    GraphQueryCreate,
    GraphResearchCreate,
    GraphResearchOut,
    SourceCreate,
)
from graphview_api.settings import Settings, get_settings


def create_retrieval_router(
    repo_provider: Callable[[], GraphRepository],
    *,
    provider_registry_factory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/agent-runs/{agent_run_id}/approve-action", response_model=AgentActionProposalOut)
    async def approve_agent_action(
        agent_run_id: str,
        payload: AgentActionApprovalCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        run = repository.get_agent_run(agent_run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
        action = repository.get_agent_action(payload.action_proposal_id)
        if action is None or action["agent_run_id"] != agent_run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        try:
            return repository.approve_agent_action(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error

    @router.post("/graph/query", response_model=GraphQueryAnswerOut)
    async def graph_query(
        payload: GraphQueryCreate,
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if graph_id or lens:
            payload = payload.model_copy(update={"graph_id": graph_id or payload.graph_id, "lens": lens or payload.lens})
        context = repository.graph_query_context(payload)
        try:
            provider = provider_registry_factory(settings, repository).resolve(payload.provider, payload.model)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        response = await provider.complete(
            system="Answer using only the supplied Graphview graph context and citations. Do not mutate graph state.",
            user=json.dumps(
                {
                    "question": payload.question,
                    "citations": context["citations"],
                    "nodes": context["nodes"],
                    "sources": context["sources"],
                },
                sort_keys=True,
                default=str,
            ),
            response_format="graph_query",
        )
        output = {
            "answer": response.structured.get("answer") or response.text,
            "confidence": response.structured.get("confidence", response.confidence),
            "citations": context["citations"],
        }
        run = repository.create_agent_run(
            AgentRunCreate(
                kind="graph_query",
                input={"question": payload.question, "graph_id": payload.graph_id, "lens": payload.lens},
            ),
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            output=output,
        )
        return {
            "answer": output["answer"],
            "confidence": output["confidence"],
            "citations": context["citations"],
            "agent_run": run,
        }

    @router.post("/graph/research", response_model=GraphResearchOut, status_code=status.HTTP_201_CREATED)
    async def graph_research(
        payload: GraphResearchCreate,
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if graph_id or lens:
            payload = payload.model_copy(update={"graph_id": graph_id or payload.graph_id, "lens": lens or payload.lens})
        try:
            provider = provider_registry_factory(settings, repository).resolve(payload.provider, payload.model)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        response = await provider.complete(
            system="Create a concise research note that can be ingested into Graphview as reviewable proposals.",
            user=json.dumps(
                {"query": payload.query, "source_policy": payload.source_policy, "lens": payload.lens},
                sort_keys=True,
            ),
            response_format="research",
        )
        title = str(response.structured.get("title") or f"AI research note: {payload.query[:96]}")
        content = str(response.structured.get("content") or response.text)
        document = await build_document(kind="markdown", title=title, content=content)
        generated = [
            proposal.__dict__
            for proposal in generate_proposals(
                document,
                limit=6,
                extraction_lenses=[payload.lens] if payload.lens in {"research", "engineering", "ops"} else None,
            )
        ]
        ingestion = repository.create_ingestion_result(
            source_payload=SourceCreate(
                kind="markdown",
                title=title,
                uri=f"agent-research://{payload.query[:80]}",
                checksum=document.checksum,
                metadata={
                    "agentProvider": response.provider,
                    "agentModel": response.model,
                    "researchQuery": payload.query,
                },
            ),
            generated_proposals=generated,
            embedding_model=EMBEDDING_MODEL,
            embedding_vector=embed_text(document.text),
            actor_id=user.id,
            source_text=document.text,
            graph_id=payload.graph_id,
        )
        run = repository.create_agent_run(
            AgentRunCreate(
                kind="research",
                input={"query": payload.query, "graph_id": payload.graph_id, "lens": payload.lens},
            ),
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            output={
                "message": response.text,
                "source_id": ingestion["source"]["id"],
                "proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]],
                "confidence": response.confidence,
            },
            status="waiting_for_review",
        )
        task = repository.create_research_task(
            payload,
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            agent_run_id=run["id"],
            result={
                "source_id": ingestion["source"]["id"],
                "proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]],
            },
        )
        if ingestion["proposals"]:
            repository.create_agent_action_proposal(
                agent_run_id=run["id"],
                action_type="review_proposals",
                title="Review AI research proposals",
                summary=f"{len(ingestion['proposals'])} proposals are ready for human review.",
                payload={"proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]]},
                citations=[],
                confidence=response.confidence,
            )
            run = repository.get_agent_run(run["id"]) or run
        return {
            "research_task": task,
            "agent_run": run,
            "source": ingestion["source"],
            "ingestion_run": ingestion["ingestion_run"],
            "proposals": ingestion["proposals"],
        }

    return router
