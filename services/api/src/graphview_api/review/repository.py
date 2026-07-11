from __future__ import annotations

from typing import Protocol

from graphview_api.schemas import ProposalCreate, ReviewDecisionCreate


class ReviewRepositoryPort(Protocol):
    def list_proposals(self, graph_id: str | None = None, lens: str | None = None) -> list[dict]: ...

    def review_queue(self, *, limit: int = 25, graph_id: str | None = None, lens: str | None = None) -> dict: ...

    def review_dashboard(self, graph_id: str | None = None, lens: str | None = None) -> dict: ...

    def review_activity(self, *, limit: int = 10, graph_id: str | None = None, lens: str | None = None) -> dict: ...

    def source_review_coverage(
        self,
        *,
        limit: int = 25,
        graph_id: str | None = None,
        lens: str | None = None,
    ) -> dict: ...

    def create_proposal(self, payload: ProposalCreate, actor_id: str) -> dict: ...

    def list_review_decisions(self, graph_id: str | None = None) -> list[dict]: ...

    def review(self, payload: ReviewDecisionCreate, reviewer_id: str) -> dict: ...
