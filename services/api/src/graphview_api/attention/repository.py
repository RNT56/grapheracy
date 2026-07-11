from __future__ import annotations

from typing import Protocol

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


class AttentionRepositoryPort(Protocol):
    def list_signals(self, *, kind: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]: ...

    def get_signal(self, signal_id: str) -> dict | None: ...

    def create_signal(self, payload: SignalCreate, actor_id: str) -> dict: ...

    def list_observations(self, *, signal_id: str | None = None, limit: int = 50) -> list[dict]: ...

    def create_observation(self, payload: ObservationCreate, actor_id: str) -> dict: ...

    def list_alerts(self, *, status: str | None = None, severity: str | None = None, limit: int = 50) -> list[dict]: ...

    def assign_alert(self, alert_id: str, payload: AlertAssign, actor_id: str) -> dict | None: ...

    def list_attention(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        owner_id: str | None = None,
        limit: int = 50,
    ) -> dict: ...

    def transition_attention(
        self,
        attention_item_id: str,
        payload: AttentionTransition,
        actor_id: str,
    ) -> dict | None: ...

    def list_owners(self, *, scope_kind: str | None = None, limit: int = 100) -> list[dict]: ...

    def create_owner(self, payload: OwnerCreate) -> dict: ...

    def update_owner(self, owner_id: str, payload: OwnerUpdate) -> dict | None: ...

    def list_routing_policies(self, *, enabled: bool | None = None, limit: int = 100) -> list[dict]: ...

    def create_routing_policy(self, payload: RoutingPolicyCreate) -> dict: ...

    def update_routing_policy(self, policy_id: str, payload: RoutingPolicyUpdate) -> dict | None: ...
