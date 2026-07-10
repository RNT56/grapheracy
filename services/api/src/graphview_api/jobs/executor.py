from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

from graphview_api.connectors import build_connector_proposals, fetch_connector_documents
from graphview_api.action_adapters import ActionExecutor
from graphview_api.ai_runtime import AiRuntime
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.ingestion import EMBEDDING_MODEL, NormalizedDocument, build_document, embed_text, generate_proposals
from graphview_api.llm import build_llm_provider
from graphview_api.repository import GraphRepository
from graphview_api.schemas import ActionRunCreate, AgentRunCreate, GraphQueryCreate, GraphResearchCreate, IngestionCreate, PlanningMessageCreate, SignalCreate, SourceCreate
from graphview_api.settings import Settings
from graphview_api.upload_extraction import extract_uploaded_text, validate_uploaded_payload
from graphview_api.malware import scan_payload


class GraphJobExecutor:
    """Application service executed by Arq workers and legacy compatibility routes."""

    def __init__(
        self,
        repository: GraphRepository,
        settings: Settings,
        *,
        llm_provider_factory=build_llm_provider,
        object_store=None,
        action_executor: ActionExecutor | None = None,
    ):
        self.repository = repository
        self.settings = settings
        self.llm_provider_factory = llm_provider_factory
        self.object_store = object_store
        self.action_executor = action_executor

    async def execute(self, job: dict) -> dict:
        payload = job["payload"]
        actor_id = str(payload.get("actor_id") or "system-worker")
        if job["kind"] == "ingestion.run":
            return await self.ingestion(
                IngestionCreate.model_validate(payload["ingestion"]),
                actor_id=actor_id,
                graph_id=payload.get("graph_id"),
            )
        if job["kind"] == "upload.ingest":
            if self.object_store is None:
                raise RuntimeError("Object store is not configured")
            raw = self.object_store.get_bytes(str(payload["object_key"]))
            validate_uploaded_payload(str(payload["filename"]), str(payload["content_type"]), raw)
            await scan_payload(
                self.settings,
                filename=str(payload["filename"]),
                content_type=str(payload["content_type"]),
                payload=raw,
            )
            kind, content = extract_uploaded_text(str(payload["filename"]), str(payload["content_type"]), raw)
            return await self.ingestion(
                IngestionCreate(
                    kind=kind,
                    title=str(payload["title"]),
                    content=content,
                    uri=f"object://{payload['object_key']}",
                ),
                actor_id=actor_id,
                graph_id=payload.get("graph_id"),
            )
        if job["kind"] == "connector.sync":
            return await self.connector_sync(
                str(payload["target_id"]),
                actor_id=actor_id,
                worker_id=str(job.get("worker_id") or "graphview-worker"),
                retry_attempt=int(job.get("attempt") or 1),
                project_id=str(payload.get("project_id") or "project-default"),
            )
        if job["kind"] == "action.run":
            bundle = self.repository.action_proposal_execution_bundle(
                str(payload["action_proposal_id"]), project_id=str(payload.get("project_id") or "project-default")
            )
            if bundle is None:
                raise KeyError(str(payload["action_proposal_id"]))
            proposal, action_payload = bundle
            if proposal["action_type"] in {"create_external_ticket", "create_notification", "trigger_workflow"}:
                if self.action_executor is None:
                    raise RuntimeError("External action adapters are not configured")
                result = await self.action_executor.execute(proposal, action_payload)
                return self.repository.record_external_action_run(
                    proposal["id"],
                    actor_id=actor_id,
                    external_id=result.external_id,
                    adapter_metadata=result.metadata,
                )
            return self.repository.create_action_run(
                ActionRunCreate(action_proposal_id=str(payload["action_proposal_id"])), actor_id
            )
        ai = AiRuntime(self.repository, self.settings)
        if job["kind"] == "ai.planning":
            return await ai.planning_message(
                str(payload["session_id"]), PlanningMessageCreate.model_validate(payload["message"]), actor_id=actor_id
            )
        if job["kind"] == "ai.query":
            return await ai.graph_query(GraphQueryCreate.model_validate(payload["query"]), actor_id=actor_id)
        if job["kind"] == "ai.research":
            return await ai.research(GraphResearchCreate.model_validate(payload["research"]), actor_id=actor_id)
        if job["kind"] == "ai.agent":
            return await ai.agent_run(AgentRunCreate.model_validate(payload["agent_run"]), actor_id=actor_id)
        if job["kind"] == "agent_context.retention":
            return self.repository.run_agent_context_retention()
        raise ValueError(f"Unsupported durable job kind: {job['kind']}")

    async def ingestion(self, payload: IngestionCreate, *, actor_id: str, graph_id: str | None = None) -> dict:
        document = await build_document(
            kind=payload.kind,
            title=payload.title,
            content=payload.content,
            uri=payload.uri,
            content_base64=payload.content_base64,
            allowed_hosts={host.strip().lower() for host in self.settings.outbound_allowed_hosts.split(",") if host.strip()},
        )
        generated = [
            proposal.__dict__
            for proposal in generate_proposals(
                document,
                limit=payload.proposal_limit,
                extraction_lenses=payload.extraction_lenses,
                proposal_limit_per_lens=payload.proposal_limit_per_lens,
            )
        ]
        return self.repository.create_ingestion_result(
            source_payload=SourceCreate(kind=payload.kind, title=payload.title, uri=payload.uri, checksum=document.checksum),
            generated_proposals=generated,
            embedding_model=EMBEDDING_MODEL,
            embedding_vector=embed_text(document.text),
            actor_id=actor_id,
            source_text=document.text,
            graph_id=graph_id,
        )

    async def connector_sync(
        self,
        target_id: str,
        *,
        actor_id: str,
        worker_id: str,
        retry_attempt: int,
        project_id: str = "project-default",
    ) -> dict:
        bundle = self.repository.connector_target_bundle(target_id, project_id=project_id)
        if bundle is None:
            raise KeyError(target_id)
        state = ConnectorStateRepository(self.repository.engine)
        health = state.get(target_id)
        existing_remote_ids = state.remote_ids(target_id)
        state.claim(target_id, worker_id=worker_id)
        account, target, token_json = bundle
        original_token_json = copy.deepcopy(token_json)
        global_allowed_hosts = {host.strip().lower() for host in self.settings.outbound_allowed_hosts.split(",") if host.strip()}
        target_allowed_hosts = {str(host).strip().lower() for host in target.get("sync_settings", {}).get("allowed_hosts", []) if str(host).strip()}
        effective_allowed_hosts = global_allowed_hosts & target_allowed_hosts if global_allowed_hosts and target_allowed_hosts else (global_allowed_hosts or target_allowed_hosts)
        target = {
            **target,
            "sync_settings": {
                **target.get("sync_settings", {}),
                "allowed_hosts": sorted(effective_allowed_hosts),
                "require_allowed_hosts": self.settings.environment not in {"local", "test", "development"},
                "connector_cursor": health["cursor"]["cursor"] if health else None,
                "existing_remote_ids": sorted(existing_remote_ids),
            },
        }
        try:
            fetch_result = await fetch_connector_documents(account=account, target=target, token_json=token_json)
        except Exception as error:
            failed = state.fail(target_id, error, retry_attempt=retry_attempt)
            self.repository.create_signal(
                SignalCreate(
                    kind="connector_issue",
                    severity="high" if failed["status"] in {"auth_failed", "rate_limited"} else "medium",
                    source_kind="connector",
                    source_id=target_id,
                    title=f"{target['title']} connector sync failed",
                    summary=str(error)[:2000],
                    payload={"target_id": target_id, "status": failed["status"], "retry_attempt": retry_attempt},
                ),
                actor_id,
            )
            raise
        if token_json is not None and token_json != original_token_json:
            self.repository.update_connector_account_tokens(account["id"], token_json, project_id=target["project_id"])
        documents = fetch_result.documents
        graph_settings = self.repository.graph_settings_with_secrets()
        provider_api_keys = self.repository.ai_provider_api_keys()
        target_settings = target.get("sync_settings", {})
        llm_enabled = bool(target_settings.get("llm_enabled", graph_settings.get("llm_enabled", self.settings.llm_enabled)))
        llm_provider = str(target_settings.get("llm_provider") or graph_settings.get("llm_provider") or self.settings.llm_provider)
        llm_model = str(target_settings.get("llm_model") or graph_settings.get("llm_model") or self.settings.llm_model)
        llm_base_url = str(target_settings.get("llm_base_url") or graph_settings["settings"].get("llm_base_url") or self.settings.llm_base_url)
        llm_api_key = target_settings.get("llm_api_key") or graph_settings["settings"].get("llm_api_key") or self.settings.llm_api_key or provider_api_keys.get("openai")
        auto_commit_threshold = float(target_settings.get("auto_commit_threshold", graph_settings.get("auto_commit_threshold", self.settings.auto_commit_threshold)))
        llm = self.llm_provider_factory(
            enabled=llm_enabled,
            provider=llm_provider,
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model,
        )
        proposals_by_remote_id: dict[str, list[dict]] = {}
        vectors_by_remote_id: dict[str, list[float]] = {}
        for document in documents:
            proposals = [proposal.__dict__ for proposal in build_connector_proposals(document)]
            proposals.extend(
                proposal.__dict__
                for proposal in generate_proposals(
                    NormalizedDocument(
                        kind=document.source_kind,
                        title=document.title,
                        text=document.text,
                        uri=document.uri or document.remote_url,
                        checksum=document.checksum,
                        locator=document.uri or document.remote_url or document.remote_id,
                    )
                )
            )
            if llm_enabled:
                proposals.extend(
                    proposal.__dict__
                    for proposal in await llm.extract(
                        title=document.title,
                        text=document.text,
                        locator=document.uri or document.remote_url or document.remote_id,
                    )
                )
            proposals_by_remote_id[document.remote_id] = proposals
            vectors_by_remote_id[document.remote_id] = embed_text(document.text)
        try:
            result = self.repository.create_connector_sync_result(
                target_id=target_id,
                documents=documents,
                generated_proposals_by_remote_id=proposals_by_remote_id,
                embedding_model=EMBEDDING_MODEL,
                embedding_vectors_by_remote_id=vectors_by_remote_id,
                actor_id=actor_id,
                auto_commit_threshold=auto_commit_threshold,
                full_snapshot=fetch_result.full_snapshot,
                tombstone_remote_ids=set(fetch_result.tombstone_remote_ids),
            )
        except Exception as error:
            state.fail(target_id, error, retry_attempt=retry_attempt)
            raise
        state.succeed(
            target_id,
            imported_count=len(result["sources"]),
            deleted_count=result["deleted_count"],
            cursor=fetch_result.cursor,
            next_scheduled_at=(
                datetime.now(tz=UTC) + timedelta(minutes=int(target_settings.get("interval_minutes") or 0))
                if int(target_settings.get("interval_minutes") or 0) > 0 and target_settings.get("schedule_enabled", True) is not False
                else None
            ),
        )
        return result
