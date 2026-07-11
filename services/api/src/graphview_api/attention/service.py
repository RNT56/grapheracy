from __future__ import annotations

from datetime import datetime, timezone

from graphview_api.attention.repository import AttentionRepositoryPort
from graphview_api.schemas import (
    AlertAssign,
    AttentionTransition,
    ObservationCreate,
    OwnerCreate,
    OwnerUpdate,
    RoutingPolicyCreate,
    RoutingPolicyUpdate,
    SignalCreate,
)


class AttentionService:
    def __init__(self, repository: AttentionRepositoryPort) -> None:
        self.repository = repository

    def signals(self, *, kind: str | None, status: str | None, limit: int) -> dict[str, list[dict]]:
        return {"signals": self.repository.list_signals(kind=kind, status=status, limit=limit)}

    def signal(self, signal_id: str) -> dict:
        value = self.repository.get_signal(signal_id)
        if value is None:
            raise KeyError(signal_id)
        return value

    def create_signal(self, payload: SignalCreate, *, actor_id: str) -> dict:
        return self.repository.create_signal(payload, actor_id)

    def observations(self, *, signal_id: str | None, limit: int) -> dict[str, list[dict]]:
        return {"observations": self.repository.list_observations(signal_id=signal_id, limit=limit)}

    def create_observation(self, payload: ObservationCreate, *, actor_id: str) -> dict:
        return self.repository.create_observation(payload, actor_id)

    def alerts(self, *, status_filter: str | None, severity: str | None, limit: int) -> dict[str, list[dict]]:
        return {"alerts": self.repository.list_alerts(status=status_filter, severity=severity, limit=limit)}

    def assign_alert(self, alert_id: str, payload: AlertAssign, *, actor_id: str) -> dict:
        value = self.repository.assign_alert(alert_id, payload, actor_id)
        if value is None:
            raise KeyError(alert_id)
        return value

    def attention(
        self,
        *,
        status_filter: str | None,
        severity: str | None,
        owner_id: str | None,
        limit: int,
    ) -> dict:
        return self.repository.list_attention(
            status=status_filter,
            severity=severity,
            owner_id=owner_id,
            limit=limit,
        )

    def transition(self, attention_item_id: str, payload: AttentionTransition, *, actor_id: str) -> dict:
        item = self.repository.transition_attention(attention_item_id, payload, actor_id)
        if item is None:
            raise KeyError(attention_item_id)
        return {"generated_at": datetime.now(timezone.utc), "returned_count": 1, "items": [item]}

    def owners(self, *, scope_kind: str | None, limit: int) -> dict[str, list[dict]]:
        return {"owners": self.repository.list_owners(scope_kind=scope_kind, limit=limit)}

    def create_owner(self, payload: OwnerCreate) -> dict:
        return self.repository.create_owner(payload)

    def update_owner(self, owner_id: str, payload: OwnerUpdate) -> dict:
        value = self.repository.update_owner(owner_id, payload)
        if value is None:
            raise KeyError(owner_id)
        return value

    def policies(self, *, enabled: bool | None, limit: int) -> dict[str, list[dict]]:
        return {"routing_policies": self.repository.list_routing_policies(enabled=enabled, limit=limit)}

    def create_policy(self, payload: RoutingPolicyCreate) -> dict:
        return self.repository.create_routing_policy(payload)

    def update_policy(self, policy_id: str, payload: RoutingPolicyUpdate) -> dict:
        value = self.repository.update_routing_policy(policy_id, payload)
        if value is None:
            raise KeyError(policy_id)
        return value
