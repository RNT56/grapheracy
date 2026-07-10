from __future__ import annotations

import json

from graphview_api.ingestion import EMBEDDING_MODEL, build_document, embed_text, generate_proposals
from graphview_api.llm import build_provider_registry
from graphview_api.schemas import (
    AgentRunCreate,
    GraphBuildSpecCreate,
    GraphQueryCreate,
    GraphResearchCreate,
    PlanningMessageCreate,
    SourceCreate,
)


class AiRuntime:
    """Durable AI application service; all graph mutations remain proposal/review gated."""

    def __init__(self, repository, settings) -> None:
        self.repository = repository
        self.settings = settings

    def provider_registry(self):
        return build_provider_registry(
            self.settings,
            provider_api_keys=self.repository.ai_provider_api_keys(),
            default_provider=self.repository.ai_default_provider(),
        )

    async def planning_message(self, session_id: str, payload: PlanningMessageCreate, *, actor_id: str) -> dict:
        session = self.repository.get_planning_session(session_id)
        if session is None:
            raise KeyError(session_id)
        provider = self.provider_registry().resolve(payload.provider or session.get("provider"), payload.model or session.get("model"))
        context = self.repository.graph_query_context(
            GraphQueryCreate(question=f"{session['goal']}\n{payload.content}", graph_id=session.get("graph_id"), lens=session["lens"]),
            actor_id=actor_id,
        )
        response = await provider.complete(
            system="Create a concise cited Graphview planning response and graph build spec. Graph mutations remain review-gated.",
            user=json.dumps(
                {
                    "title": session["title"],
                    "goal": session["goal"],
                    "message": payload.content,
                    "lens": session["lens"],
                    "citations": context["citations"],
                },
                sort_keys=True,
                default=str,
            ),
            response_format="graph_build_spec",
        )
        build_spec = response.structured or {}
        updated = self.repository.add_planning_message(
            session_id,
            payload,
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            assistant_content=response.text,
            assistant_metadata={"buildSpec": build_spec, "confidence": response.confidence, "citations": context["citations"]},
            agent_run_output={
                "message": response.text,
                "build_spec": build_spec,
                "confidence": response.confidence,
                "citations": context["citations"],
            },
        )
        if build_spec:
            self.repository.upsert_graph_build_spec(
                session_id,
                GraphBuildSpecCreate(
                    title=str(build_spec.get("title") or session["title"]),
                    objective=str(build_spec.get("objective") or session["goal"]),
                    status="draft",
                    spec={**build_spec, "citations": context["citations"]},
                ),
            )
            updated = self.repository.get_planning_session(session_id) or updated
        return updated

    async def agent_run(self, payload: AgentRunCreate, *, actor_id: str) -> dict:
        provider = self.provider_registry().resolve(payload.provider, payload.model)
        response = await provider.complete(
            system="Execute a Graphview agent run without direct graph mutation.",
            user=json.dumps(payload.input, sort_keys=True),
            response_format="text",
        )
        return self.repository.create_agent_run(
            payload,
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            output={"message": response.text, "structured": response.structured, "confidence": response.confidence},
        )

    async def graph_query(self, payload: GraphQueryCreate, *, actor_id: str) -> dict:
        context = self.repository.graph_query_context(payload, actor_id=actor_id)
        if not context["citations"]:
            raise ValueError("Graph answer blocked because no supporting citations were retrieved")
        provider = self.provider_registry().resolve(payload.provider, payload.model)
        response = await provider.complete(
            system="Answer only from the supplied Graphview context and cite the supplied evidence. Do not mutate graph state.",
            user=json.dumps(
                {"question": payload.question, "citations": context["citations"], "nodes": context["nodes"], "sources": context["sources"]},
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
            AgentRunCreate(kind="graph_query", input={"question": payload.question, "graph_id": payload.graph_id, "lens": payload.lens}),
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            output=output,
        )
        return {**output, "agent_run": run}

    async def research(self, payload: GraphResearchCreate, *, actor_id: str) -> dict:
        context = self.repository.graph_query_context(
            GraphQueryCreate(
                question=payload.query,
                graph_id=payload.graph_id,
                lens=payload.lens,
                node_id=payload.node_id,
                source_id=payload.source_id,
                source_chunk_id=payload.source_chunk_id,
            ),
            actor_id=actor_id,
        )
        if not context["citations"]:
            raise ValueError("Research blocked because no supporting citations were retrieved")
        provider = self.provider_registry().resolve(payload.provider, payload.model)
        response = await provider.complete(
            system="Create a concise cited research note that becomes reviewable Graphview proposals.",
            user=json.dumps(
                {"query": payload.query, "source_policy": payload.source_policy, "lens": payload.lens, "citations": context["citations"]},
                sort_keys=True,
                default=str,
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
                    "citationIds": [citation["id"] for citation in context["citations"]],
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
            AgentRunCreate(kind="research", input={"query": payload.query, "graph_id": payload.graph_id, "lens": payload.lens}),
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            output={
                "message": response.text,
                "source_id": ingestion["source"]["id"],
                "proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]],
                "confidence": response.confidence,
                "citations": context["citations"],
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
                "citations": context["citations"],
            },
        )
        if ingestion["proposals"]:
            self.repository.create_agent_action_proposal(
                agent_run_id=run["id"],
                action_type="review_proposals",
                title="Review AI research proposals",
                summary=f"{len(ingestion['proposals'])} cited proposals are ready for human review.",
                payload={"proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]]},
                citations=context["citations"],
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
