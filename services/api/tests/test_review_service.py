from graphview_api.review.service import ReviewService
from graphview_api.schemas import ProposalCreate, ReviewDecisionCreate


class RecordingReviewRepository:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def list_proposals(self, graph_id=None, lens=None):
        self.calls.append(("proposals", graph_id, lens))
        return [{"id": "proposal-1"}]

    def review_queue(self, **kwargs):
        self.calls.append(("queue", kwargs))
        return {"items": []}

    def review_dashboard(self, graph_id=None, lens=None):
        self.calls.append(("dashboard", graph_id, lens))
        return {"pending": 1}

    def review_activity(self, **kwargs):
        return {"events": []}

    def source_review_coverage(self, **kwargs):
        return {"sources": []}

    def create_proposal(self, payload, actor_id):
        return {"id": "proposal-1", "source_id": payload.source_id, "actor_id": actor_id}

    def list_review_decisions(self, graph_id=None):
        return [{"id": "decision-1", "graph_id": graph_id}]

    def review(self, payload, reviewer_id):
        return {"id": "decision-1", "decision": payload.decision, "reviewer_id": reviewer_id}


def test_review_service_normalizes_lenses_for_all_projections() -> None:
    repository = RecordingReviewRepository()
    service = ReviewService(repository)

    assert service.proposals(graph_id="graph-1", lens="invalid")["proposals"][0]["id"] == "proposal-1"
    service.queue(limit=25, graph_id="graph-1", lens="engineering")
    service.dashboard(graph_id="graph-1", lens="invalid")

    assert repository.calls == [
        ("proposals", "graph-1", "all"),
        ("queue", {"limit": 25, "graph_id": "graph-1", "lens": "engineering"}),
        ("dashboard", "graph-1", "all"),
    ]


def test_review_service_preserves_review_gated_proposal_creation() -> None:
    service = ReviewService(RecordingReviewRepository())
    proposal = service.create_proposal(
        ProposalCreate(
            source_id="source-1",
            proposed_value={"id": "node-1", "label": "Evidence", "kind": "concept"},
        ),
        actor_id="agent-1",
    )

    assert proposal == {"id": "proposal-1", "source_id": "source-1", "actor_id": "agent-1"}


def test_review_service_preserves_reviewer_authority() -> None:
    decision = ReviewService(RecordingReviewRepository()).decide(
        ReviewDecisionCreate(proposal_id="proposal-1", decision="accept"),
        reviewer_id="reviewer-1",
    )

    assert decision == {"id": "decision-1", "decision": "accept", "reviewer_id": "reviewer-1"}
