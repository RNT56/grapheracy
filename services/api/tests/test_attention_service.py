import pytest

from graphview_api.attention.service import AttentionService
from graphview_api.schemas import AttentionTransition, OwnerUpdate, SignalCreate


class RecordingAttentionRepository:
    def __init__(self) -> None:
        self.signal_value = {"id": "signal-1"}
        self.attention_value = {"id": "attention-1", "status": "assigned"}
        self.owner_value = {"id": "owner-1", "display_name": "Owner"}

    def list_signals(self, **kwargs):
        return [{"id": "signal-1", **kwargs}]

    def get_signal(self, signal_id):
        return self.signal_value

    def create_signal(self, payload, actor_id):
        return {"id": "signal-1", "kind": payload.kind, "actor_id": actor_id}

    def list_observations(self, **kwargs):
        return []

    def create_observation(self, payload, actor_id):
        return {"id": "observation-1", "actor_id": actor_id}

    def list_alerts(self, **kwargs):
        return []

    def assign_alert(self, alert_id, payload, actor_id):
        return {"id": alert_id, "actor_id": actor_id}

    def list_attention(self, **kwargs):
        return {"items": [self.attention_value], "filters": kwargs}

    def transition_attention(self, attention_item_id, payload, actor_id):
        return self.attention_value

    def list_owners(self, **kwargs):
        return [self.owner_value]

    def create_owner(self, payload):
        return self.owner_value

    def update_owner(self, owner_id, payload):
        return self.owner_value

    def list_routing_policies(self, **kwargs):
        return []

    def create_routing_policy(self, payload):
        return {"id": "policy-1"}

    def update_routing_policy(self, policy_id, payload):
        return {"id": policy_id}


def test_attention_service_preserves_signal_actor_and_normalized_projection() -> None:
    service = AttentionService(RecordingAttentionRepository())
    created = service.create_signal(
        SignalCreate(kind="anomaly_detected", title="Drift", summary="Metric moved unexpectedly."),
        actor_id="agent-1",
    )
    listed = service.signals(kind="anomaly_detected", status="new", limit=10)

    assert created["actor_id"] == "agent-1"
    assert listed["signals"][0]["limit"] == 10


def test_attention_service_wraps_transition_as_attention_projection() -> None:
    result = AttentionService(RecordingAttentionRepository()).transition(
        "attention-1",
        AttentionTransition(status="assigned", assignee_id="owner-1"),
        actor_id="reviewer-1",
    )

    assert result["returned_count"] == 1
    assert result["items"][0]["status"] == "assigned"


def test_attention_service_exposes_missing_entities_as_domain_errors() -> None:
    repository = RecordingAttentionRepository()
    repository.signal_value = None
    repository.owner_value = None
    service = AttentionService(repository)

    with pytest.raises(KeyError):
        service.signal("missing")
    with pytest.raises(KeyError):
        service.update_owner("missing", OwnerUpdate(display_name="Missing"))
