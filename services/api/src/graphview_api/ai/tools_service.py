from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from graphview_api.ai.repository import AiRepositoryPort
from graphview_api.lenses import normalize_graph_lens
from graphview_api.schemas import AgentToolCallCreate, GraphQueryCreate, ProposalCreate


class AgentToolsService:
    def __init__(self, repository: AiRepositoryPort) -> None:
        self.repository = repository

    def execute(self, payload: AgentToolCallCreate, *, actor_id: str) -> dict:
        timestamp = datetime.now(timezone.utc)
        tool_input = payload.input
        graph_id = tool_input.get("graph_id") if isinstance(tool_input.get("graph_id"), str) else None
        lens = normalize_graph_lens(tool_input.get("lens") if isinstance(tool_input.get("lens"), str) else "all")
        citations: list[dict[str, object]] = []
        affected_graph_ids: list[str] = []
        resulting_proposal_id: str | None = None
        call_status = "succeeded"
        summary = ""

        if payload.kind == "graph_query":
            question = str(tool_input.get("question") or tool_input.get("query") or "")
            if not question.strip():
                call_status = "blocked"
                summary = "Graph query requires a question."
            else:
                context = self.repository.graph_query_context(
                    GraphQueryCreate(
                        question=question,
                        graph_id=graph_id,
                        lens=lens,
                        node_id=tool_input.get("node_id") if isinstance(tool_input.get("node_id"), str) else None,
                        source_id=tool_input.get("source_id") if isinstance(tool_input.get("source_id"), str) else None,
                    )
                )
                citations = context["citations"]
                affected_graph_ids = [node["id"] for node in context["nodes"]] + [
                    source["id"] for source in context["sources"]
                ]
                summary = f"Collected {len(citations)} citations from graph context."
        elif payload.kind == "source_search":
            query = str(tool_input.get("query") or tool_input.get("q") or "")
            found_sources = self.repository.list_sources(query=query or None, graph_id=graph_id)[:8]
            citations = [
                {
                    "id": f"source-{source['id']}",
                    "label": source["title"],
                    "source_id": source["id"],
                    "source_title": source["title"],
                    "url": source.get("remote_url") or source.get("uri"),
                }
                for source in found_sources
            ]
            affected_graph_ids = [source["id"] for source in found_sources]
            summary = f"Found {len(found_sources)} matching sources."
        elif payload.kind == "source_open":
            source_id = str(tool_input.get("source_id") or "")
            source = self.repository.get_source(source_id) if source_id else None
            if source is None:
                call_status = "blocked"
                summary = "Source not found."
            else:
                chunks = self.repository.list_source_chunks(source_id=source_id, graph_id=graph_id)[:8]
                citations = [
                    {
                        "id": f"chunk-{chunk['id']}",
                        "label": source["title"],
                        "source_id": source["id"],
                        "source_title": source["title"],
                        "source_chunk_id": chunk["id"],
                        "locator": chunk["locator"],
                        "quote": chunk["text"][:360],
                    }
                    for chunk in chunks
                ]
                affected_graph_ids = [source_id]
                summary = f"Opened {source['title']} with {len(chunks)} readable chunks."
        elif payload.kind == "proposal_create":
            source_id = str(tool_input.get("source_id") or "")
            proposed_value = tool_input.get("proposed_value") if isinstance(tool_input.get("proposed_value"), dict) else None
            if source_id and proposed_value:
                proposal = self.repository.create_proposal(
                    ProposalCreate(
                        source_id=source_id,
                        kind=(
                            tool_input.get("kind")
                            if tool_input.get("kind") in {"content_node", "semantic_edge"}
                            else "content_node"
                        ),
                        proposed_value=proposed_value,
                        confidence=(
                            tool_input.get("confidence")
                            if isinstance(tool_input.get("confidence"), int | float)
                            else None
                        ),
                        locator=(
                            tool_input.get("locator")
                            if isinstance(tool_input.get("locator"), str)
                            else "agent tool"
                        ),
                    ),
                    actor_id,
                )
                call_status = "pending_review"
                resulting_proposal_id = proposal["id"]
                affected_graph_ids = [proposal["id"]]
                summary = "Created a review-gated graph proposal."
            else:
                call_status = "pending_review"
                summary = "Proposal creation is review-gated and needs source_id plus proposed_value."
        elif payload.kind in {"research_run", "review_action", "connector_sync"}:
            call_status = "pending_review"
            summary = f"{payload.kind.replace('_', ' ')} is queued for review-gated execution."
        elif payload.kind == "graph_layout":
            summary = f"Prepared {tool_input.get('layout') or 'overview'} graph layout update."

        return {
            "id": f"tool_{uuid4().hex[:20]}",
            "kind": payload.kind,
            "input": tool_input,
            "status": call_status,
            "citations": citations,
            "affected_graph_ids": affected_graph_ids,
            "resulting_proposal_id": resulting_proposal_id,
            "summary": summary,
            "started_at": timestamp,
            "finished_at": timestamp,
        }
