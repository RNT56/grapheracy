from __future__ import annotations

from graphview_api.operations.repository import DataOperationsRepositoryPort
from graphview_api.schemas import BackupBundle, ImportBundle


class DataOperationsService:
    def __init__(self, repository: DataOperationsRepositoryPort) -> None:
        self.repository = repository

    def search(self, *, query: str, graph_id: str | None) -> dict[str, list[object]]:
        return self.repository.search(query, graph_id)

    def export(self, *, graph_id: str | None) -> dict:
        return self.repository.export_bundle(graph_id)

    def backup(self, *, actor_id: str, include_agent_context_content: bool) -> dict:
        return self.repository.backup_bundle(
            actor_id=actor_id,
            include_agent_context_content=include_agent_context_content,
        )

    def restore(self, payload: BackupBundle, *, actor_id: str) -> dict:
        return self.repository.restore_bundle(payload.bundle, actor_id=actor_id)

    def import_bundle(self, payload: ImportBundle, *, actor_id: str) -> dict:
        for source in payload.sources:
            self.repository.create_source(source)
        for proposal in payload.proposals:
            self.repository.create_proposal(proposal, actor_id)
        return self.repository.export_bundle()
