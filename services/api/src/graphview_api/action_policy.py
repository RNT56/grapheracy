from __future__ import annotations

from collections.abc import Iterable


DEFAULT_SAFE_ACTION_TYPES = (
    "mark_source_stale",
    "mark_source_refreshed",
    "create_notification",
    "create_external_ticket",
    "connector_sync",
    "create_graph_proposal",
    "request_owner_confirmation",
)


def normalize_safe_action_types(value: Iterable[str] | str | None = None) -> frozenset[str]:
    if value is None:
        return frozenset(DEFAULT_SAFE_ACTION_TYPES)
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    return frozenset(item.strip() for item in items if item.strip())
