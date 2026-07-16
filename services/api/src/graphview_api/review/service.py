from __future__ import annotations

from graphview_api.lenses import normalize_graph_lens
from graphview_api.review.repository import ReviewRepositoryPort
from graphview_api.schemas import ProposalCreate, ReviewDecisionCreate


class ReviewService:
    def __init__(self, repository: ReviewRepositoryPort) -> None:
        self.repository = repository

    def proposals(self, *, graph_id: str | None, lens: str | None) -> dict[str, list[dict]]:
        return {"proposals": self.repository.list_proposals(graph_id, lens=normalize_graph_lens(lens))}

    def queue(self, *, limit: int, graph_id: str | None, lens: str | None) -> dict[str, object]:
        return self.repository.review_queue(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    def dashboard(self, *, graph_id: str | None, lens: str | None) -> dict[str, object]:
        return self.repository.review_dashboard(graph_id, normalize_graph_lens(lens))

    def activity(self, *, limit: int, graph_id: str | None, lens: str | None) -> dict[str, object]:
        return self.repository.review_activity(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    def source_coverage(self, *, limit: int, graph_id: str | None, lens: str | None) -> dict[str, object]:
        return self.repository.source_review_coverage(
            limit=limit,
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
        )

    def create_proposal(self, payload: ProposalCreate, *, actor_id: str) -> dict:
        return self.repository.create_proposal(payload, actor_id)

    def decisions(self, *, graph_id: str | None) -> dict[str, list[dict]]:
        return {"review_decisions": self.repository.list_review_decisions(graph_id)}

    def decide(self, payload: ReviewDecisionCreate, *, reviewer_id: str) -> dict:
        return self.repository.review(payload, reviewer_id)
