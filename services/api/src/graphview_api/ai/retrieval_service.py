from __future__ import annotations

import json

from graphview_api.ai.repository import AiRepositoryPort
from graphview_api.ingestion import EMBEDDING_MODEL, build_document, embed_text, generate_proposals
from graphview_api.schemas import (
    AgentActionApprovalCreate,
    AgentRunCreate,
    GraphQueryCreate,
    GraphResearchCreate,
    SourceCreate,
)
from graphview_api.settings import Settings


class RetrievalService:
    def __init__(self, repository: AiRepositoryPort, settings: Settings, *, provider_registry_factory) -> None:
        self.repository = repository
        self.settings = settings
        self.provider_registry_factory = provider_registry_factory

    def registry(self):
        return self.provider_registry_factory(self.settings, self.repository)

    def approve_action(self, agent_run_id: str, payload: AgentActionApprovalCreate, *, reviewer_id: str) -> dict:
        if self.repository.get_agent_run(agent_run_id) is None:
            raise KeyError("agent_run")
        action = self.repository.get_agent_action(payload.action_proposal_id)
        if action is None or action["agent_run_id"] != agent_run_id:
            raise KeyError("action_proposal")
        return self.repository.approve_agent_action(payload, reviewer_id)

    async def query(
        self,
        payload: GraphQueryCreate,
        *,
        graph_id: str | None,
        lens: str | None,
        actor_id: str,
    ) -> dict:
        if graph_id or lens:
            payload = payload.model_copy(update={"graph_id": graph_id or payload.graph_id, "lens": lens or payload.lens})
        context = self.repository.graph_query_context(payload)
        provider = self.registry().resolve(payload.provider, payload.model)
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
        run = self.repository.create_agent_run(
            AgentRunCreate(
                kind="graph_query",
                input={"question": payload.question, "graph_id": payload.graph_id, "lens": payload.lens},
            ),
            actor_id=actor_id,
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

    async def research(
        self,
        payload: GraphResearchCreate,
        *,
        graph_id: str | None,
        lens: str | None,
        actor_id: str,
    ) -> dict:
        if graph_id or lens:
            payload = payload.model_copy(update={"graph_id": graph_id or payload.graph_id, "lens": lens or payload.lens})
        response = await self.registry().resolve(payload.provider, payload.model).complete(
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
        ingestion = self.repository.create_ingestion_result(
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
            actor_id=actor_id,
            source_text=document.text,
            graph_id=payload.graph_id,
        )
        run = self.repository.create_agent_run(
            AgentRunCreate(
                kind="research",
                input={"query": payload.query, "graph_id": payload.graph_id, "lens": payload.lens},
            ),
            actor_id=actor_id,
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
        task = self.repository.create_research_task(
            payload,
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            agent_run_id=run["id"],
            result={
                "source_id": ingestion["source"]["id"],
                "proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]],
            },
        )
        if ingestion["proposals"]:
            self.repository.create_agent_action_proposal(
                agent_run_id=run["id"],
                action_type="review_proposals",
                title="Review AI research proposals",
                summary=f"{len(ingestion['proposals'])} proposals are ready for human review.",
                payload={"proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]]},
                citations=[],
                confidence=response.confidence,
            )
            run = self.repository.get_agent_run(run["id"]) or run
        return {
            "research_task": task,
            "agent_run": run,
            "source": ingestion["source"],
            "ingestion_run": ingestion["ingestion_run"],
            "proposals": ingestion["proposals"],
        }
