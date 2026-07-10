import importlib.util
import asyncio
import hashlib
import hmac
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from graphview_api import db
from graphview_api.auth import CurrentUser, get_current_user
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.main import create_app
from graphview_api.schemas import IngestionCreate
from graphview_api.settings import Settings


def make_client(settings: Settings | None = None) -> TestClient:
    resolved = settings or Settings(database_url="sqlite://")
    if resolved.object_store_provider == "local" and resolved.object_store_path == "./.graphview/objects":
        resolved = resolved.model_copy(update={"object_store_path": tempfile.mkdtemp(prefix="graphview-test-objects-")})
    return TestClient(create_app(resolved))


ADMIN_HEADERS = {"X-Graphview-User": "maintainer"}
READER_HEADERS = {"X-Graphview-User": "reader"}


def create_agent_context_capture_session(
    client: TestClient,
    *,
    title: str = "Codex context run",
    workspace_root: str | None = "/Users/mt/Programming/Schtack/graphview",
) -> tuple[dict[str, str], dict]:
    created_client = client.post(
        "/agent-context/clients",
        headers=ADMIN_HEADERS,
        json={
            "display_name": "Codex local gateway",
            "runtime_kind": "codex",
            "scopes": ["context:capture"],
        },
    )
    assert created_client.status_code == 201
    token = created_client.json()["token"]
    capture_headers = {"Authorization": f"Bearer {token}"}
    created_session = client.post(
        "/agent-context/sessions",
        headers=capture_headers,
        json={
            "title": title,
            "runtime_kind": "codex",
            "authority": "gateway",
            "workspace_root": workspace_root,
            "repository_uri": "git@example.invalid:graphview.git",
            "branch": "codex/phase27",
            "commit_sha": "abc123",
        },
    )
    assert created_session.status_code == 201
    return capture_headers, created_session.json()


def test_health() -> None:
    client = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "graphview-api"}


def test_rate_limiter_returns_problem_details_and_retry_after() -> None:
    client = make_client(Settings(database_url="sqlite://", rate_limit_requests=2))

    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    limited = client.get("/health")

    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert limited.headers["content-type"].startswith("application/problem+json")


def test_version() -> None:
    client = make_client()

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.24.0"


def test_v1_compatibility_routes_match_legacy_and_deprecate_only_legacy() -> None:
    client = make_client()

    legacy = client.get("/graph", headers=READER_HEADERS)
    versioned = client.get("/api/v1/graph", headers=READER_HEADERS)

    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert versioned.json() == legacy.json()
    assert legacy.headers["Deprecation"] == "true"
    assert legacy.headers["Link"].startswith("</api/v1/graph>")
    assert "Deprecation" not in versioned.headers


def test_v1_graph_viewport_layout_search_and_etag() -> None:
    client = make_client()
    graph_id = "project-ios26-swift-demo"

    clustered = client.get(
        f"/api/v1/graphs/{graph_id}/viewport",
        params={"zoom": 0.25, "max_nodes": 20, "max_edges": 100},
        headers=READER_HEADERS,
    )
    assert clustered.status_code == 200
    viewport = clustered.json()
    assert viewport["graph_id"] == graph_id
    assert viewport["graph_version"] >= 1
    assert viewport["level"] in {"clusters", "mixed"}
    assert viewport["clusters"]
    assert clustered.headers["etag"] == viewport["etag"]

    not_modified = client.get(
        f"/api/v1/graphs/{graph_id}/viewport",
        params={"zoom": 0.25, "max_nodes": 20, "max_edges": 100},
        headers={**READER_HEADERS, "If-None-Match": viewport["etag"]},
    )
    assert not_modified.status_code == 304

    graph = client.get("/graph", params={"graph_id": graph_id}, headers=READER_HEADERS).json()
    positions = [
        {"node_id": node["id"], "x": index / 10, "y": -(index / 10), "z": index / 100}
        for index, node in enumerate(graph["nodes"][:4])
    ]
    saved = client.put(
        f"/api/v1/graphs/{graph_id}/layouts/review",
        headers=ADMIN_HEADERS,
        json={"name": "review", "algorithm": "manual", "positions": positions},
    )
    assert saved.status_code == 200
    assert saved.json()["position_count"] == len(positions)
    layouts = client.get(
        f"/api/v1/graphs/{graph_id}/layouts",
        params={"include_positions": True},
        headers=READER_HEADERS,
    )
    assert layouts.status_code == 200
    returned_positions = sorted(layouts.json()[0]["positions"], key=lambda position: position["node_id"])
    expected_positions = sorted(positions, key=lambda position: position["node_id"])
    assert [position["node_id"] for position in returned_positions] == [position["node_id"] for position in expected_positions]
    assert [(position["x"], position["y"], position["z"]) for position in returned_positions] == [
        (position["x"], position["y"], position["z"]) for position in expected_positions
    ]

    searched = client.get(
        f"/api/v1/graphs/{graph_id}/search",
        params={"q": "Liquid Glass"},
        headers=READER_HEADERS,
    )
    assert searched.status_code == 200
    assert any(anchor["label"] == "Liquid Glass" for anchor in searched.json()["anchors"])


def test_v1_project_scope_blocks_bola_for_graphs_jobs_and_job_lists() -> None:
    settings = Settings(database_url="sqlite://", object_store_path=tempfile.mkdtemp(prefix="graphview-bola-objects-"))
    app = create_app(settings)

    async def scoped_admin() -> CurrentUser:
        return CurrentUser(
            id="scoped-admin",
            email="scoped@example.test",
            role="admin",
            project_ids=("project-default",),
        )

    app.dependency_overrides[get_current_user] = scoped_admin
    with TestClient(app) as client:
        hidden_job = JobRepository(app.state.repository.engine).enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key="bola-hidden-job",
                payload={"project_id": "project-ios26-swift-demo", "ingestion": {"kind": "text", "title": "Hidden", "content": "Hidden"}},
            ),
            project_id="project-ios26-swift-demo",
        )

        assert client.get("/api/v1/graphs/project-ios26-swift-demo/viewport").status_code == 404
        assert client.get("/api/v1/jobs", params={"project_id": "project-ios26-swift-demo"}).status_code == 404
        assert client.get(f"/api/v1/jobs/{hidden_job['id']}").status_code == 404
        assert client.post(f"/api/v1/jobs/{hidden_job['id']}/cancel").status_code == 404


def test_v1_ingestion_jobs_are_durable_and_idempotent() -> None:
    client = make_client()
    payload = {
        "kind": "text",
        "title": "Durable ingestion",
        "content": "# Durable ingestion\nGraphview queues this work transactionally.",
    }

    first = client.post("/api/v1/ingestions", headers=ADMIN_HEADERS, json=payload)
    second = client.post("/api/v1/ingestions", headers=ADMIN_HEADERS, json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["kind"] == "ingestion.run"
    assert first.json()["status"] == "queued"

    jobs = JobRepository(client.app.state.repository.engine)
    outbox = jobs.pending_outbox()
    assert len(outbox) == 1
    assert outbox[0]["aggregate_id"] == first.json()["id"]

    claimed = jobs.claim(first.json()["id"], worker_id="test-worker")
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempt"] == 1

    completed = jobs.complete(first.json()["id"], {"source_id": "source-test"})
    assert completed["status"] == "succeeded"
    assert completed["result"] == {"source_id": "source-test"}


def test_v1_ai_query_and_research_are_durable_cited_worker_jobs() -> None:
    client = make_client()
    repository = client.app.state.repository
    settings = Settings(database_url="sqlite://", object_store_path=tempfile.mkdtemp(prefix="graphview-ai-objects-"))
    executor = GraphJobExecutor(repository, settings, object_store=client.app.state.object_store)
    ingestion = asyncio.run(
        executor.ingestion(
            IngestionCreate(
                kind="markdown",
                title="Liquid Glass evidence",
                content="# Liquid Glass\nLiquid Glass enables adaptive, depth-aware interface materials.",
            ),
            actor_id="evidence-seed",
            graph_id="project-ios26-swift-demo",
        )
    )
    source_id = ingestion["source"]["id"]
    source_chunk_id = repository.list_source_chunks(source_id=source_id, graph_id="project-ios26-swift-demo")[0]["id"]

    query_job = client.post(
        "/api/v1/ai/query",
        headers=READER_HEADERS,
        json={
            "question": "What enables adaptive depth-aware interface materials?",
            "graph_id": "project-ios26-swift-demo",
            "source_id": source_id,
            "source_chunk_id": source_chunk_id,
        },
    )
    assert query_job.status_code == 202
    jobs = JobRepository(repository.engine)
    claimed_query = jobs.claim(query_job.json()["id"], worker_id="ai-test")
    query_result = asyncio.run(executor.execute(claimed_query))
    assert query_result["citations"]
    assert query_result["citations"][0]["source_id"] == source_id
    assert query_result["citations"][0]["source_chunk_id"] == source_chunk_id
    assert query_result["agent_run"]["status"] == "completed"
    with repository.engine.begin() as conn:
        retrieval_audits = conn.execute(
            select(db.audit_events).where(db.audit_events.c.action == "ai.retrieval")
        ).mappings().all()
    assert retrieval_audits

    research_job = client.post(
        "/api/v1/ai/research",
        headers=ADMIN_HEADERS,
        json={
            "query": "What enables adaptive depth-aware interface materials?",
            "graph_id": "project-ios26-swift-demo",
            "lens": "research",
            "source_id": source_id,
            "source_chunk_id": source_chunk_id,
        },
    )
    assert research_job.status_code == 202
    claimed_research = jobs.claim(research_job.json()["id"], worker_id="ai-test")
    research_result = asyncio.run(executor.execute(claimed_research))
    assert research_result["proposals"]
    assert research_result["agent_run"]["output"]["citations"]
    assert research_result["agent_run"]["status"] == "waiting_for_review"


def test_v1_failed_job_is_a_visible_dead_letter_and_can_be_requeued() -> None:
    client = make_client()
    created = client.post(
        "/api/v1/jobs",
        headers=ADMIN_HEADERS,
        json={
            "kind": "agent_context.retention",
            "queue": "maintenance",
            "idempotency_key": "maintenance-test-1",
            "payload": {"project_id": "project-default"},
            "max_attempts": 1,
        },
    ).json()
    jobs = JobRepository(client.app.state.repository.engine)
    assert jobs.claim(created["id"], worker_id="failing-worker") is not None
    failed = jobs.fail(created["id"], error_code="InjectedFailure", error="failure injection")
    assert failed["status"] == "failed"

    retried = client.post(f"/api/v1/jobs/{created['id']}/retry", headers=ADMIN_HEADERS)

    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempt"] == 0
    assert len(jobs.pending_outbox()) == 2


def test_v1_approved_action_can_be_enqueued_once() -> None:
    client = make_client()
    proposal = client.post(
        "/action-proposals",
        headers=ADMIN_HEADERS,
        json={
            "action_type": "webhook",
            "title": "Notify workflow",
            "summary": "Send an approved workflow notification.",
            "payload": {"destination": "https://example.invalid/hook"},
        },
    ).json()
    approved = client.post(
        f"/action-proposals/{proposal['id']}/approve",
        headers=ADMIN_HEADERS,
        json={"rationale": "Approved by test"},
    )
    assert approved.status_code == 200

    first = client.post(f"/api/v1/action-proposals/{proposal['id']}/run", headers=ADMIN_HEADERS)
    second = client.post(f"/api/v1/action-proposals/{proposal['id']}/run", headers=ADMIN_HEADERS)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["kind"] == "action.run"


def test_v1_upload_streams_to_object_storage_and_worker_ingests(tmp_path: Path) -> None:
    settings = Settings(database_url="sqlite://", object_store_path=str(tmp_path / "objects"))
    client = make_client(settings)

    accepted = client.post(
        "/api/v1/uploads",
        headers=ADMIN_HEADERS,
        data={"title": "Uploaded evidence"},
        files={"file": ("../evidence.md", b"# Evidence\nA durable uploaded source.", "text/markdown")},
    )

    assert accepted.status_code == 202
    body = accepted.json()
    assert body["filename"] == "evidence.md"
    object_path = tmp_path / "objects" / body["object_key"]
    assert object_path.read_bytes().startswith(b"# Evidence")

    jobs = JobRepository(client.app.state.repository.engine)
    claimed = jobs.claim(body["job_id"], worker_id="upload-test")
    assert claimed is not None
    result = asyncio.run(
        GraphJobExecutor(
            client.app.state.repository,
            settings,
            object_store=client.app.state.object_store,
        ).execute(claimed)
    )
    completed = jobs.complete(body["job_id"], result)
    assert completed["status"] == "succeeded"
    assert result["source"]["title"] == "Uploaded evidence"
    assert result["proposals"]


def test_v1_resumable_upload_persists_offset_and_enqueues_completion(tmp_path: Path) -> None:
    settings = Settings(database_url="sqlite://", object_store_path=str(tmp_path / "objects"))
    client = make_client(settings)
    content = b"# Resumable evidence\nGraphview preserves upload ordering."
    created = client.post(
        "/api/v1/uploads/resumable",
        headers=ADMIN_HEADERS,
        json={
            "filename": "evidence.md",
            "content_type": "text/markdown",
            "expected_bytes": len(content),
            "title": "Resumable evidence",
        },
    )
    assert created.status_code == 201
    upload_id = created.json()["id"]
    assert created.headers["upload-offset"] == "0"
    assert client.head(f"/api/v1/uploads/resumable/{upload_id}", headers=READER_HEADERS).headers["upload-offset"] == "0"

    mismatch = client.patch(
        f"/api/v1/uploads/resumable/{upload_id}",
        headers={**ADMIN_HEADERS, "Upload-Offset": "1", "Content-Type": "application/offset+octet-stream"},
        content=content,
    )
    assert mismatch.status_code == 409
    completed = client.patch(
        f"/api/v1/uploads/resumable/{upload_id}",
        headers={**ADMIN_HEADERS, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream"},
        content=content,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["job_id"].startswith("job_")
    assert (tmp_path / "objects" / completed.json()["object_key"]).read_bytes() == content
    assert JobRepository(client.app.state.repository.engine).get(completed.json()["job_id"])["status"] == "queued"


def test_github_connector_webhook_verifies_signature_and_deduplicates_delivery() -> None:
    client = make_client()
    account = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={
            "kind": "repository",
            "display_name": "GitHub App",
            "token_json": {"webhook_secret": "webhook-test-secret", "access_token": "installation-token"},
        },
    ).json()
    target = client.post(
        "/connector-targets",
        headers=ADMIN_HEADERS,
        json={
            "account_id": account["id"],
            "target_type": "repository",
            "remote_id": "owner/repository",
            "title": "Repository",
            "sync_settings": {"provider": "github"},
        },
    ).json()
    payload = b'{"ref":"refs/heads/main"}'
    signature = "sha256=" + hmac.new(b"webhook-test-secret", payload, hashlib.sha256).hexdigest()
    headers = {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Delivery": "delivery-1",
        "X-GitHub-Event": "push",
        "Content-Type": "application/json",
    }

    first = client.post(f"/api/v1/connectors/github/{target['id']}/webhook", headers=headers, content=payload)
    second = client.post(f"/api/v1/connectors/github/{target['id']}/webhook", headers=headers, content=payload)
    invalid = client.post(
        f"/api/v1/connectors/github/{target['id']}/webhook",
        headers={**headers, "X-Hub-Signature-256": "sha256=invalid", "X-GitHub-Delivery": "delivery-2"},
        content=payload,
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert invalid.status_code == 401


def test_v1_connector_health_tracks_queue_lease_and_actionable_failure() -> None:
    client = make_client()
    account = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={"kind": "upload", "display_name": "Health uploads"},
    ).json()
    target = client.post(
        "/connector-targets",
        headers=ADMIN_HEADERS,
        json={
            "account_id": account["id"],
            "target_type": "upload",
            "remote_id": "health-target",
            "title": "Health target",
            "sync_settings": {"content": "# Health"},
        },
    ).json()

    initial = client.get(f"/api/v1/connectors/{target['id']}/health", headers=READER_HEADERS)
    assert initial.status_code == 200
    assert initial.json()["status"] == "healthy"
    queued = client.post(f"/api/v1/connectors/{target['id']}/sync", headers=ADMIN_HEADERS)
    assert queued.status_code == 202
    assert client.get(f"/api/v1/connectors/{target['id']}/health", headers=READER_HEADERS).json()["status"] == "syncing"

    from graphview_api.connector_state import ConnectorStateRepository

    state = ConnectorStateRepository(client.app.state.repository.engine)
    state.claim(target["id"], worker_id="worker-health")
    state.fail(target["id"], RuntimeError("429 provider rate limit"), retry_attempt=2)
    failed = client.get(f"/api/v1/connectors/{target['id']}/health", headers=READER_HEADERS).json()
    assert failed["status"] == "rate_limited"
    assert failed["retry_attempt"] == 2
    assert "429" in failed["actionable_failure"]


def test_v1_subgraph_is_bounded_and_project_scoped() -> None:
    client = make_client()
    graph_id = "project-ios26-swift-demo"
    graph = client.get("/graph", params={"graph_id": graph_id}, headers=READER_HEADERS).json()
    focus_id = graph["nodes"][0]["id"]

    response = client.get(
        f"/api/v1/graphs/{graph_id}/subgraph",
        params={"focus_node_id": focus_id, "depth": 1, "max_nodes": 12},
        headers=READER_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["focus_node_id"] == focus_id
    assert len(body["nodes"]) <= 12
    assert all(node["project_id"] == graph_id for node in body["nodes"])


def test_local_auth_rejects_unknown_user() -> None:
    client = make_client()

    response = client.get("/graph", headers={"X-Graphview-User": "unknown"})

    assert response.status_code == 401


def test_cookie_authenticated_mutations_require_csrf() -> None:
    client = make_client()
    asyncio.run(
        client.app.state.identity.store.put(
            "session:test-session",
            {
                "user": {"id": "oidc-admin", "email": "admin@example.test", "role": "admin"},
                "csrf_token": "csrf-test-token",
            },
            300,
        )
    )
    client.cookies.set("graphview_session", "test-session")

    denied = client.post("/sources", json={"kind": "text", "title": "Denied without CSRF"})
    accepted = client.post(
        "/sources",
        headers={"X-CSRF-Token": "csrf-test-token"},
        json={"kind": "text", "title": "Accepted with CSRF"},
    )

    assert denied.status_code == 403
    assert denied.headers["content-type"].startswith("application/problem+json")
    assert accepted.status_code == 201


def test_reader_can_read_but_cannot_write() -> None:
    client = make_client()

    graph = client.get("/graph", headers=READER_HEADERS)
    assert graph.status_code == 200

    created = client.post("/sources", headers=READER_HEADERS, json={"kind": "text", "title": "Reader note"})
    assert created.status_code == 403


def test_connector_and_provider_secrets_use_authenticated_envelopes() -> None:
    client = make_client()
    account = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={
            "kind": "repository",
            "display_name": "GitHub App",
            "token_json": {"access_token": "top-secret-token"},
        },
    )
    assert account.status_code == 201
    provider = client.patch(
        "/providers/openai/credentials",
        headers=ADMIN_HEADERS,
        json={"api_key": "top-secret-provider-key", "make_default": True},
    )
    assert provider.status_code == 200

    with client.app.state.repository.engine.begin() as connection:
        token_envelope = connection.execute(
            select(db.connector_accounts.c.encrypted_token_json).where(
                db.connector_accounts.c.id == account.json()["id"]
            )
        ).scalar_one()
        settings_json = connection.execute(
            select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == "project-default")
        ).scalar_one()

    assert token_envelope.startswith("gvenc:aesgcm:v2:")
    assert "top-secret-token" not in token_envelope
    assert "top-secret-provider-key" not in settings_json
    assert "gvenc:aesgcm:v2:" in settings_json


def test_lenses_expose_extraction_and_graph_descriptors() -> None:
    client = make_client()

    old_response = client.get("/modes", headers=READER_HEADERS)
    extraction_response = client.get("/extraction-lenses", headers=READER_HEADERS)
    graph_response = client.get("/graph-lenses", headers=READER_HEADERS)

    assert old_response.status_code == 404
    assert extraction_response.status_code == 200
    assert graph_response.status_code == 200
    lenses = extraction_response.json()["extraction_lenses"]
    assert {lens["id"] for lens in lenses} >= {"research", "engineering", "ops"}
    engineering = next(lens for lens in lenses if lens["id"] == "engineering")
    assert "repository" in engineering["source_kinds"]
    assert {"repository", "file", "symbol", "package"} <= set(engineering["primary_node_kinds"])
    graph_lenses = graph_response.json()["graph_lenses"]
    assert {lens["id"] for lens in graph_lenses} >= {"all", "research", "engineering", "ops"}


def test_live_demo_graph_is_seeded_and_selectable() -> None:
    client = make_client()

    graphs = client.get("/graphs", headers=READER_HEADERS)

    assert graphs.status_code == 200
    graph_views = graphs.json()
    demo = next(view for view in graph_views if view["id"] == "project-ios26-swift-demo")
    assert demo["kind"] == "project"
    assert demo["node_count"] >= 32
    assert demo["edge_count"] >= 50
    assert demo["source_count"] >= 6

    scoped = next(view for view in graph_views if view["id"] == "project-ios26-swift-demo:planning")
    assert scoped["kind"] == "scope"
    assert scoped["node_count"] < demo["node_count"]

    graph = client.get("/graph", params={"graph_id": demo["id"]}, headers=READER_HEADERS)
    assert graph.status_code == 200
    labels = {node["label"] for node in graph.json()["nodes"]}
    assert "Native iOS 26 Swift App" in labels
    assert "Liquid Glass" in labels
    assert len(graph.json()["edges"]) >= 50

    chunks = client.get(
        "/source-chunks",
        params={"graph_id": demo["id"], "source_id": "src-team-blueprint"},
        headers=READER_HEADERS,
    )
    assert chunks.status_code == 200
    source_chunks = chunks.json()["source_chunks"]
    assert len(source_chunks) >= 4
    assert any("SwiftUI-first architecture" in chunk["text"] for chunk in source_chunks)


def test_source_crud_and_search() -> None:
    client = make_client()

    created = client.post(
        "/sources",
        json={"kind": "markdown", "title": "Research notes", "uri": "file://notes.md"},
    )

    assert created.status_code == 201
    source = created.json()
    assert source["title"] == "Research notes"

    listed = client.get("/sources", params={"q": "Research"})
    assert listed.status_code == 200
    assert listed.json()["sources"][0]["id"] == source["id"]

    updated = client.patch(f"/sources/{source['id']}", json={"title": "Reviewed research notes"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Reviewed research notes"

    searched = client.get("/search", params={"q": "Reviewed"})
    assert searched.status_code == 200
    assert searched.json()["sources"][0]["id"] == source["id"]

    deleted = client.delete(f"/sources/{source['id']}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 204
    assert client.get("/sources").json()["sources"] == []


def test_proposal_review_commits_node_with_provenance() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Interview transcript"}).json()
    proposal = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "confidence": 0.86,
            "locator": "line 12",
            "proposed_value": {
                "label": "Tacit knowledge",
                "kind": "concept",
                "summary": "Knowledge that is hard to formalize.",
            },
        },
    )

    assert proposal.status_code == 201
    proposal_body = proposal.json()
    assert proposal_body["status"] == "pending_review"
    assert proposal_body["provenance"][0]["sourceId"] == source["id"]

    decision = client.post(
        "/review-decisions",
        json={"proposal_id": proposal_body["id"], "decision": "accept", "rationale": "Relevant concept"},
    )

    assert decision.status_code == 201
    assert decision.json()["decision"] == "accept"

    graph = client.get("/graph").json()
    assert graph["nodes"][0]["label"] == "Tacit knowledge"
    assert graph["nodes"][0]["provenance"][0]["locator"] == "line 12"

    proposals = client.get("/proposals").json()["proposals"]
    assert proposals[0]["status"] == "accepted"


def test_proposal_create_validates_node_and_edge_values() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Schema source"}).json()

    invalid_node = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"label": "Invalid kind", "kind": "not-a-node-kind"},
        },
    )
    assert invalid_node.status_code == 422

    missing_endpoint = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {"targetNodeId": "node-b", "relation": "supports"},
        },
    )
    assert missing_endpoint.status_code == 422

    invalid_relation = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {
                "sourceNodeId": "node-a",
                "targetNodeId": "node-b",
                "relation": "invalid_relation",
            },
        },
    )
    assert invalid_relation.status_code == 422


def test_export_and_import_sources() -> None:
    client = make_client()

    imported = client.post(
        "/import",
        headers=ADMIN_HEADERS,
        json={"sources": [{"kind": "url", "title": "Graph paper", "uri": "https://example.invalid/paper"}]},
    )

    assert imported.status_code == 200
    bundle = client.get("/export", headers=ADMIN_HEADERS)
    assert bundle.status_code == 200
    assert bundle.json()["sources"][0]["title"] == "Graph paper"


def test_connector_account_target_crud_redacts_tokens_and_enforces_roles() -> None:
    client = make_client()

    reader_denied = client.post(
        "/connector-accounts",
        headers=READER_HEADERS,
        json={"kind": "notion", "display_name": "Reader Notion", "token_json": {"access_token": "secret"}},
    )
    assert reader_denied.status_code == 403

    account_response = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={
            "kind": "notion",
            "display_name": "Workspace Notion",
            "token_json": {"access_token": "secret-token"},
            "scopes": ["read_content"],
        },
    )
    assert account_response.status_code == 201
    account = account_response.json()
    assert account["kind"] == "notion"
    assert "token_json" not in account
    assert "encrypted_token_json" not in account

    listed = client.get("/connector-accounts", headers=READER_HEADERS).json()["connector_accounts"]
    assert listed[0]["id"] == account["id"]
    assert "secret-token" not in str(listed)

    target = client.post(
        "/connector-targets",
        headers=ADMIN_HEADERS,
        json={
            "account_id": account["id"],
            "target_type": "page",
            "remote_id": "notion-page-1",
            "title": "Notion Product Plan",
            "sync_settings": {"pages": [{"id": "notion-page-1", "title": "Plan", "content": "# Strategy\n[[SwiftUI]]"}]},
        },
    )
    assert target.status_code == 201
    assert target.json()["connector_kind"] == "notion"


def test_manual_connector_sync_creates_chunks_proposals_and_auto_commits() -> None:
    client = make_client()
    account = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={"kind": "upload", "display_name": "Uploads"},
    ).json()
    target = client.post(
        "/connector-targets",
        headers=ADMIN_HEADERS,
        json={
            "account_id": account["id"],
            "target_type": "upload",
            "remote_id": "upload-target",
            "title": "iOS Uploads",
            "sync_settings": {
                "files": [
                    {
                        "id": "file-a",
                        "title": "SwiftUI Plan",
                        "content": "# Architecture\nSwiftUI references https://developer.apple.com/documentation/swiftui\n@Navigation",
                    },
                    {
                        "id": "file-b",
                        "title": "Release Plan",
                        "content": "# Release\nApp Store Connect checklist",
                    },
                ],
            },
        },
    ).json()

    synced = client.post("/connector-sync-runs", headers=ADMIN_HEADERS, json={"target_id": target["id"]})
    assert synced.status_code == 201
    sync_body = synced.json()
    assert sync_body["sync_run"]["status"] == "completed"
    assert sync_body["sync_run"]["source_count"] == 2
    assert sync_body["sync_run"]["chunk_count"] >= 4
    assert sync_body["sync_run"]["proposal_count"] >= 6
    assert sync_body["sync_run"]["auto_committed_count"] >= 4

    sources = client.get("/sources", headers=READER_HEADERS).json()["sources"]
    uploaded = [source for source in sources if source["connector_kind"] == "upload"]
    assert {source["remote_id"] for source in uploaded} == {"file-a", "file-b"}
    assert uploaded[0]["metadata"]["targetId"] == target["id"]

    chunks = client.get("/source-chunks", params={"source_id": uploaded[0]["id"]}, headers=READER_HEADERS).json()
    assert chunks["source_chunks"]
    assert any(chunk["heading_path"] for chunk in chunks["source_chunks"])

    graph = client.get("/graph", headers=READER_HEADERS).json()
    labels = {node["label"] for node in graph["nodes"]}
    assert "SwiftUI Plan" in labels
    assert "Architecture" in labels
    assert any(edge["relation"] in {"contains", "references"} for edge in graph["edges"])

    decisions = client.get("/review-decisions", headers=READER_HEADERS).json()["review_decisions"]
    assert any(decision["reviewer_id"] == "system-autocommit" for decision in decisions)


def test_connector_resync_is_idempotent_and_marks_missing_remote_sources_stale() -> None:
    client = make_client()
    account = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={"kind": "upload", "display_name": "Uploads"},
    ).json()
    target = client.post(
        "/connector-targets",
        headers=ADMIN_HEADERS,
        json={
            "account_id": account["id"],
            "target_type": "upload",
            "remote_id": "sync-target",
            "title": "Sync Target",
            "sync_settings": {
                "files": [
                    {"id": "kept", "title": "Kept", "content": "# Kept\nhttps://example.invalid/a"},
                    {"id": "removed", "title": "Removed", "content": "# Removed"},
                ],
            },
        },
    ).json()

    first = client.post("/connector-sync-runs", headers=ADMIN_HEADERS, json={"target_id": target["id"]}).json()
    assert first["sync_run"]["proposal_count"] > 0
    second = client.post("/connector-sync-runs", headers=ADMIN_HEADERS, json={"target_id": target["id"]}).json()
    assert second["sync_run"]["proposal_count"] == 0

    updated = client.patch(
        f"/connector-targets/{target['id']}",
        headers=ADMIN_HEADERS,
        json={"sync_settings": {"files": [{"id": "kept", "title": "Kept Updated", "content": "# Kept\nUpdated"}]}},
    )
    assert updated.status_code == 200
    third = client.post("/connector-sync-runs", headers=ADMIN_HEADERS, json={"target_id": target["id"]}).json()
    assert third["sync_run"]["source_count"] == 1

    sources = client.get("/sources", headers=READER_HEADERS).json()["sources"]
    removed = next(source for source in sources if source["remote_id"] == "removed")
    kept = next(source for source in sources if source["remote_id"] == "kept")
    assert removed["stale_at"]
    assert kept["stale_at"] is None
    assert kept["title"] == "Kept Updated"


def test_llm_extraction_is_disabled_by_default_and_runs_through_provider_when_enabled(monkeypatch) -> None:
    from graphview_api import main as api_main
    from graphview_api.ingestion import GeneratedProposal

    calls = {"count": 0}

    class FakeLlmProvider:
        async def extract(self, *, title: str, text: str, locator: str):
            calls["count"] += 1
            return [
                GeneratedProposal(
                    kind="content_node",
                    proposed_value={
                        "id": "node-llm-concept",
                        "label": "LLM Concept",
                        "kind": "concept",
                        "summary": "Created by fake LLM provider.",
                    },
                    confidence=0.93,
                    locator=locator,
                )
            ]

    def fake_provider(**kwargs):
        return FakeLlmProvider()

    monkeypatch.setattr(api_main, "build_llm_provider", fake_provider)
    client = make_client()
    account = client.post(
        "/connector-accounts",
        headers=ADMIN_HEADERS,
        json={"kind": "upload", "display_name": "Uploads"},
    ).json()
    target = client.post(
        "/connector-targets",
        headers=ADMIN_HEADERS,
        json={
            "account_id": account["id"],
            "target_type": "upload",
            "remote_id": "llm-target",
            "title": "LLM Target",
            "sync_settings": {"content": "# Notes\nSome content."},
        },
    ).json()

    disabled = client.post("/connector-sync-runs", headers=ADMIN_HEADERS, json={"target_id": target["id"]})
    assert disabled.status_code == 201
    assert calls["count"] == 0

    settings = client.patch(
        "/graph/settings",
        headers=ADMIN_HEADERS,
        json={"llm_enabled": True, "settings": {"llm_api_key": "test-key"}},
    )
    assert settings.status_code == 200
    assert "test-key" not in str(settings.json())
    assert "llm_api_key" not in settings.json()["settings"]
    enabled = client.post("/connector-sync-runs", headers=ADMIN_HEADERS, json={"target_id": target["id"]})
    assert enabled.status_code == 201
    assert calls["count"] == 1
    graph = client.get("/graph", headers=READER_HEADERS).json()
    assert any(node["label"] == "LLM Concept" for node in graph["nodes"])


def test_provider_catalog_redacts_configuration_and_lists_ai_providers() -> None:
    client = make_client()

    response = client.get("/providers", headers=READER_HEADERS)

    assert response.status_code == 200
    providers = response.json()["providers"]
    provider_ids = {provider["id"] for provider in providers}
    assert {"graphview-local", "openai", "anthropic", "gemini"} <= provider_ids
    assert next(provider for provider in providers if provider["id"] == "graphview-local")["enabled"] is True
    assert "api_key" not in str(response.json()).lower()


def test_ai_provider_credentials_are_saved_redacted_and_used(monkeypatch) -> None:
    from graphview_api import llm

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self.body

    class FakeAsyncClient:
        calls = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return FakeResponse({"output_text": '{"answer":"saved provider ok","confidence":0.8}'})

    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)
    client = make_client()

    denied = client.patch(
        "/providers/openai/credentials",
        headers=READER_HEADERS,
        json={"api_key": "fake-openai-key"},
    )
    assert denied.status_code == 403

    saved = client.patch(
        "/providers/openai/credentials",
        headers=ADMIN_HEADERS,
        json={"api_key": "fake-openai-key", "make_default": True},
    )
    assert saved.status_code == 200
    saved_body = saved.json()
    assert next(provider for provider in saved_body["providers"] if provider["id"] == "openai")["enabled"] is True
    assert "fake-openai-key" not in str(saved_body)

    settings = client.get("/graph/settings", headers=READER_HEADERS).json()
    assert settings["settings"]["ai_default_provider"] == "openai"
    assert settings["settings"]["ai_provider_credentials"]["openai"]["configured"] is True
    assert "fake-openai-key" not in str(settings)
    assert "encrypted_api_key" not in str(settings)

    answer = client.post("/graph/query", headers=READER_HEADERS, json={"question": "What does the graph know?"})
    assert answer.status_code == 200
    assert answer.json()["agent_run"]["provider"] == "openai"
    assert FakeAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer fake-openai-key"

    cleared = client.delete("/providers/openai/credentials", headers=ADMIN_HEADERS)
    assert cleared.status_code == 200
    assert next(provider for provider in cleared.json()["providers"] if provider["id"] == "openai")["enabled"] is False
    settings_after_clear = client.get("/graph/settings", headers=READER_HEADERS).json()
    assert settings_after_clear["settings"]["ai_default_provider"] == "graphview-local"


def test_planning_session_message_creates_build_spec_and_agent_run() -> None:
    client = make_client()

    created = client.post(
        "/planning-sessions",
        headers=ADMIN_HEADERS,
        json={
            "title": "AI graph planning",
            "goal": "Map Graphview AI planning mode and embedded graph research.",
            "lens": "research",
        },
    )
    assert created.status_code == 201
    session = created.json()
    assert session["status"] == "active"
    assert session["messages"] == []

    messaged = client.post(
        f"/planning-sessions/{session['id']}/messages",
        headers=ADMIN_HEADERS,
        json={"content": "Clarify open questions and draft a build plan."},
    )
    assert messaged.status_code == 200
    body = messaged.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"
    assert body["build_spec"]["status"] == "draft"
    assert "open_questions" in body["build_spec"]["spec"]

    listed = client.get("/planning-sessions", headers=READER_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["planning_sessions"][0]["id"] == session["id"]


def test_graph_query_is_read_only_and_returns_citations() -> None:
    client = make_client()
    source = client.post(
        "/ingestion-runs",
        headers=ADMIN_HEADERS,
        json={
            "kind": "markdown",
            "title": "AI Query Source",
            "content": "# Evidence\nGraphview preserves citations for AI graph query answers.",
            "proposal_limit": 2,
        },
    ).json()
    before = client.get("/proposals", headers=READER_HEADERS).json()["proposals"]

    response = client.post(
        "/graph/query?graph_id=project-default&lens=research",
        headers=READER_HEADERS,
        json={"question": "How does Graphview preserve citations?", "source_id": source["source"]["id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["citations"]
    assert body["agent_run"]["kind"] == "graph_query"
    assert body["agent_run"]["project_id"] == "project-default"
    assert body["agent_run"]["input"]["graph_id"] == "project-default"
    assert body["agent_run"]["input"]["lens"] == "research"
    after = client.get("/proposals", headers=READER_HEADERS).json()["proposals"]
    assert len(after) == len(before)


def test_agent_tools_execute_read_tools_and_gate_mutations() -> None:
    client = make_client()
    source = client.post(
        "/sources",
        headers=ADMIN_HEADERS,
        json={"kind": "markdown", "title": "Agent tool source", "uri": "file://agent-tool.md"},
    ).json()

    catalog = client.get("/agent-tools", headers=READER_HEADERS)
    assert catalog.status_code == 200
    tool_kinds = {tool["kind"] for tool in catalog.json()["tools"]}
    assert {"graph_query", "source_search", "source_open", "proposal_create", "connector_sync"} <= tool_kinds

    searched = client.post(
        "/agent-tool-calls",
        headers=ADMIN_HEADERS,
        json={"kind": "source_search", "input": {"query": "Agent tool"}},
    )
    assert searched.status_code == 201
    assert searched.json()["status"] == "succeeded"
    assert searched.json()["citations"][0]["source_id"] == source["id"]

    opened = client.post(
        "/agent-tool-calls",
        headers=ADMIN_HEADERS,
        json={"kind": "source_open", "input": {"source_id": source["id"]}},
    )
    assert opened.status_code == 201
    assert opened.json()["affected_graph_ids"] == [source["id"]]

    proposed = client.post(
        "/agent-tool-calls",
        headers=ADMIN_HEADERS,
        json={
            "kind": "proposal_create",
            "input": {
                "source_id": source["id"],
                "kind": "content_node",
                "proposed_value": {
                    "label": "Agent tool proposal",
                    "kind": "concept",
                    "summary": "Created as a review-gated agent tool call.",
                },
            },
        },
    )
    assert proposed.status_code == 201
    body = proposed.json()
    assert body["status"] == "pending_review"
    assert body["resulting_proposal_id"]
    proposals = client.get("/proposals", headers=READER_HEADERS).json()["proposals"]
    assert proposals[0]["id"] == body["resulting_proposal_id"]
    assert proposals[0]["status"] == "pending_review"


def test_agent_context_capture_lifecycle_encryption_graph_stream_retention_and_backup() -> None:
    client = make_client(Settings(database_url="sqlite://", agent_context_max_blob_bytes=20_000, agent_context_retention_days=1))

    denied_client = client.post(
        "/agent-context/clients",
        headers=READER_HEADERS,
        json={"display_name": "Reader adapter", "runtime_kind": "codex"},
    )
    assert denied_client.status_code == 403

    created_client = client.post(
        "/agent-context/clients",
        headers=ADMIN_HEADERS,
        json={
            "display_name": "Codex local gateway",
            "runtime_kind": "codex",
            "scopes": ["context:read", "context:capture"],
        },
    )
    assert created_client.status_code == 201
    client_body = created_client.json()
    token = client_body["token"]
    assert token.startswith("gvctx_")
    assert "token_hash" not in str(client_body)
    assert client_body["client"]["scopes"] == ["context:capture"]
    capture_headers = {"Authorization": f"Bearer {token}"}

    no_token = client.post(
        "/agent-context/sessions",
        json={"title": "Missing token", "runtime_kind": "codex"},
    )
    assert no_token.status_code == 401

    created_session = client.post(
        "/agent-context/sessions",
        headers=capture_headers,
        json={
            "title": "Codex context run",
            "runtime_kind": "codex",
            "authority": "gateway",
            "workspace_root": "/Users/mt/Programming/Schtack/graphview",
            "repository_uri": "git@example.invalid:graphview.git",
            "branch": "codex/phase27",
            "commit_sha": "abc123",
        },
    )
    assert created_session.status_code == 201
    session = created_session.json()
    assert session["status"] == "running"
    assert session["authority"] == "gateway"

    batch = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-1",
                    "sequence": 1,
                    "event_kind": "file_read",
                    "summary": "Read API settings file.",
                    "payload": {"path": "services/api/src/graphview_api/settings.py", "api_key": "sk-secret"},
                    "artifact": {
                        "kind": "file",
                        "path": "services/api/src/graphview_api/settings.py",
                        "title": "settings.py",
                        "content_type": "text/x-python",
                    },
                    "content": {
                        "content_kind": "text",
                        "media_type": "text/x-python",
                        "text": "OPENAI_API_KEY=sk-secret\nclass Settings: pass\n",
                        "token_count": 8,
                    },
                },
                {
                    "client_event_id": "evt-2",
                    "sequence": 2,
                    "event_kind": "prompt_built",
                    "authority": "adapter_reported",
                    "summary": "Built prompt with selected context.",
                    "artifact": {"kind": "prompt", "title": "Prompt context", "content_type": "text/plain"},
                    "content": {
                        "content_kind": "text",
                        "media_type": "text/plain",
                        "text": "Use settings.py but do not reveal token=secret-value",
                    },
                },
            ],
        },
    )
    assert batch.status_code == 201
    batch_body = batch.json()
    assert batch_body["accepted_count"] == 2
    assert batch_body["duplicate_count"] == 0
    assert "sk-secret" not in str(batch_body)
    assert all(len(event["checksum"]) == 64 for event in batch_body["events"])

    duplicate = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={"session_id": session["id"], "events": [{"client_event_id": "evt-1", "sequence": 1, "event_kind": "file_read"}]},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["accepted_count"] == 0
    assert duplicate.json()["duplicate_count"] == 1

    denied_path = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-denied-path",
                    "sequence": 3,
                    "event_kind": "file_read",
                    "artifact": {"kind": "file", "path": ".env", "title": ".env"},
                }
            ],
        },
    )
    assert denied_path.status_code == 403
    assert "denied" in denied_path.json()["detail"]

    outside_workspace = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-outside-workspace",
                    "sequence": 4,
                    "event_kind": "file_read",
                    "artifact": {"kind": "file", "path": "/tmp/outside.py", "title": "outside.py"},
                }
            ],
        },
    )
    assert outside_workspace.status_code == 403
    assert "outside configured workspace" in outside_workspace.json()["detail"]

    events = client.get(f"/agent-context/sessions/{session['id']}/events", headers=READER_HEADERS)
    assert events.status_code == 200
    assert [event["sequence"] for event in events.json()["events"]] == [1, 2]
    assert all(len(event["checksum"]) == 64 for event in events.json()["events"])
    assert "sk-secret" not in str(events.json())

    graph = client.get(f"/agent-context/sessions/{session['id']}/graph", headers=READER_HEADERS)
    assert graph.status_code == 200
    graph_body = graph.json()
    assert graph_body["session"]["id"] == session["id"]
    assert any(node["kind"] == "file" and node["label"] == "settings.py" for node in graph_body["nodes"])
    assert any(edge["relation"] == "read" for edge in graph_body["edges"])

    artifact_id = next(artifact["id"] for artifact in graph_body["artifacts"] if artifact["kind"] == "file")
    reader_content = client.get(f"/agent-context/artifacts/{artifact_id}/content", headers=READER_HEADERS)
    assert reader_content.status_code == 403
    admin_content = client.get(f"/agent-context/artifacts/{artifact_id}/content", headers=ADMIN_HEADERS)
    assert admin_content.status_code == 200
    assert "class Settings" in admin_content.json()["text"]
    assert "sk-secret" not in admin_content.json()["text"]

    default_backup = client.get("/backup", headers=ADMIN_HEADERS)
    assert default_backup.status_code == 200
    assert default_backup.json()["metadata"]["agent_context_content_blob_count"] == 0
    assert default_backup.json()["bundle"]["agent_context_blob_contents"] == []

    content_backup = client.get(
        "/backup",
        params={"include_agent_context_content": True},
        headers=ADMIN_HEADERS,
    )
    assert content_backup.status_code == 200
    content_backup_body = content_backup.json()
    assert content_backup_body["metadata"]["agent_context_content_blob_count"] >= 1
    encrypted_backup_content = content_backup_body["bundle"]["agent_context_blob_contents"][0]["encrypted_content"]
    assert encrypted_backup_content.startswith("gvenc:fernet:v1:")
    assert "class Settings" not in str(content_backup_body["bundle"]["agent_context_blob_contents"])

    restored_client = make_client(Settings(database_url="sqlite://", agent_context_max_blob_bytes=20_000, agent_context_retention_days=1))
    restored = restored_client.post("/restore", headers=ADMIN_HEADERS, json=content_backup_body)
    assert restored.status_code == 200
    restored_content = restored_client.get(f"/agent-context/artifacts/{artifact_id}/content", headers=ADMIN_HEADERS)
    assert restored_content.status_code == 200
    assert "class Settings" in restored_content.json()["text"]
    assert "sk-secret" not in restored_content.json()["text"]

    with client.app.state.repository.engine.begin() as conn:
        stored_blob = conn.execute(db.agent_context_blobs.select()).mappings().first()
        assert stored_blob is not None
        assert stored_blob["encrypted_content"] is None
        assert stored_blob["object_key"]
        stored_object_path = client.app.state.object_store.root / stored_blob["object_key"]
        assert stored_object_path.read_text().startswith("gvenc:fernet:v1:")
        assert "class Settings" not in stored_object_path.read_text()
        conn.execute(
            update(db.agent_context_blobs)
            .where(db.agent_context_blobs.c.id == stored_blob["id"])
            .values(expires_at=datetime.now(tz=UTC) - timedelta(seconds=1))
        )

    stream_payload = ""
    with client.stream("GET", f"/agent-context/sessions/{session['id']}/stream", headers=READER_HEADERS) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        stream_payload = "".join(response.iter_text())
    assert stream_payload.startswith(": heartbeat\n\n")
    assert "event: agent-context.event\n" in stream_payload

    retention = client.post("/agent-context/retention/run", headers=ADMIN_HEADERS)
    assert retention.status_code == 200
    assert retention.json()["purged_blob_count"] == 1
    assert retention.json()["retained_blob_count"] >= 1

    retained_content = client.get(f"/agent-context/artifacts/{artifact_id}/content", headers=ADMIN_HEADERS)
    assert retained_content.status_code == 200
    assert retained_content.json()["text"] is None
    assert retained_content.json()["blob"]["encryption_status"] == "metadata_only"
    assert retained_content.json()["blob"]["redaction_status"] == "metadata_only"

    with client.app.state.repository.engine.begin() as conn:
        retained_blob = conn.execute(
            db.agent_context_blobs.select().where(db.agent_context_blobs.c.id == stored_blob["id"])
        ).mappings().first()
        retained_event = conn.execute(
            db.agent_context_events.select().where(db.agent_context_events.c.blob_id == stored_blob["id"])
        ).mappings().first()
        assert retained_blob is not None
        assert retained_blob["encrypted_content"] is None
        assert retained_blob["object_key"] is None
        assert not stored_object_path.exists()
        assert "retention_purged_at" in retained_blob["metadata_json"]
        assert retained_event is not None

    backup = client.get("/backup", headers=ADMIN_HEADERS)
    assert backup.status_code == 200
    backup_body = backup.json()
    assert backup_body["metadata"]["agent_context_session_count"] == 1
    assert backup_body["bundle"]["agent_context_sessions"][0]["id"] == session["id"]
    assert len(backup_body["bundle"]["agent_context_events"][0]["checksum"]) == 64
    assert "encrypted_content" not in str(backup_body["bundle"]["agent_context_blobs"])

    completed = client.patch(
        f"/agent-context/sessions/{session['id']}",
        headers=capture_headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_agent_context_out_of_order_events_are_listed_and_replayed_idempotently() -> None:
    client = make_client()
    capture_headers, session = create_agent_context_capture_session(
        client,
        title="Out of order context run",
    )

    out_of_order = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-seq-3",
                    "sequence": 3,
                    "event_kind": "model_response",
                    "summary": "Model returned after a pending tool call.",
                },
                {
                    "client_event_id": "evt-seq-1",
                    "sequence": 1,
                    "event_kind": "session_started",
                    "summary": "Capture session started.",
                },
            ],
        },
    )
    assert out_of_order.status_code == 201
    assert out_of_order.json()["accepted_count"] == 2
    assert out_of_order.json()["duplicate_count"] == 0

    late_middle = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-seq-2",
                    "sequence": 2,
                    "event_kind": "file_read",
                    "summary": "Late file read arrived after sequence 3.",
                }
            ],
        },
    )
    assert late_middle.status_code == 201
    assert late_middle.json()["accepted_count"] == 1
    assert late_middle.json()["duplicate_count"] == 0
    assert [event["sequence"] for event in late_middle.json()["events"]] == [2]

    replayed = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-seq-2",
                    "sequence": 20,
                    "event_kind": "file_read",
                    "summary": "Same client event should not be reaccepted at a new sequence.",
                },
                {
                    "client_event_id": "evt-seq-3-replay",
                    "sequence": 3,
                    "event_kind": "model_response",
                    "summary": "Same sequence should not be reaccepted with a new client event id.",
                },
            ],
        },
    )
    assert replayed.status_code == 201
    assert replayed.json()["accepted_count"] == 0
    assert replayed.json()["duplicate_count"] == 2
    assert replayed.json()["events"] == []

    events = client.get(f"/agent-context/sessions/{session['id']}/events", headers=READER_HEADERS)
    assert events.status_code == 200
    event_body = events.json()["events"]
    assert [event["sequence"] for event in event_body] == [1, 2, 3]
    assert [event["client_event_id"] for event in event_body] == ["evt-seq-1", "evt-seq-2", "evt-seq-3"]

    since_first = client.get(
        f"/agent-context/sessions/{session['id']}/events",
        params={"since_sequence": 1},
        headers=READER_HEADERS,
    )
    assert since_first.status_code == 200
    assert [event["sequence"] for event in since_first.json()["events"]] == [2, 3]

    graph = client.get(f"/agent-context/sessions/{session['id']}/graph", headers=READER_HEADERS)
    assert graph.status_code == 200
    assert [event["sequence"] for event in graph.json()["events"]] == [1, 2, 3]


def test_agent_context_oversized_and_metadata_blobs_are_metadata_only() -> None:
    client = make_client(
        Settings(database_url="sqlite://", agent_context_max_blob_bytes=12, agent_context_retention_days=1)
    )
    capture_headers, session = create_agent_context_capture_session(client, title="Metadata-only context run")
    oversized_text = "This context text is too large to retain."
    command_metadata = {"command": "pytest services/api/tests/test_api.py", "status": "passed"}

    batch = client.post(
        "/agent-context/events/batch",
        headers=capture_headers,
        json={
            "session_id": session["id"],
            "events": [
                {
                    "client_event_id": "evt-oversized",
                    "sequence": 1,
                    "event_kind": "file_read",
                    "summary": "Read a file whose captured content exceeds the blob limit.",
                    "artifact": {
                        "kind": "file",
                        "path": "services/api/tests/test_api.py",
                        "title": "test_api.py",
                        "content_type": "text/x-python",
                    },
                    "content": {
                        "content_kind": "text",
                        "media_type": "text/plain",
                        "text": oversized_text,
                        "token_count": 9,
                        "metadata": {"capture_mode": "oversized"},
                    },
                },
                {
                    "client_event_id": "evt-metadata",
                    "sequence": 2,
                    "event_kind": "shell_command",
                    "summary": "Recorded command metadata without retaining output bytes.",
                    "artifact": {"kind": "shell", "title": "pytest"},
                    "content": {
                        "content_kind": "metadata",
                        "media_type": "application/json",
                        "byte_count": 128,
                        "metadata": command_metadata,
                    },
                },
            ],
        },
    )
    assert batch.status_code == 201
    batch_body = batch.json()
    assert batch_body["accepted_count"] == 2
    assert batch_body["duplicate_count"] == 0
    oversized_event = next(
        event for event in batch_body["events"] if event["client_event_id"] == "evt-oversized"
    )
    metadata_event = next(
        event for event in batch_body["events"] if event["client_event_id"] == "evt-metadata"
    )
    assert oversized_event["blob_id"]
    assert metadata_event["blob_id"]

    oversized_content = client.get(
        f"/agent-context/artifacts/{oversized_event['artifact_id']}/content",
        headers=ADMIN_HEADERS,
    )
    assert oversized_content.status_code == 200
    oversized_body = oversized_content.json()
    assert oversized_body["text"] is None
    assert oversized_body["blob"]["content_kind"] == "text"
    assert oversized_body["blob"]["encryption_status"] == "metadata_only"
    assert oversized_body["blob"]["redaction_status"] == "metadata_only"
    assert oversized_body["blob"]["byte_count"] == len(oversized_text.encode("utf-8"))
    assert oversized_body["blob"]["token_count"] == 9
    assert oversized_body["blob"]["metadata"] == {"capture_mode": "oversized"}

    metadata_content = client.get(
        f"/agent-context/artifacts/{metadata_event['artifact_id']}/content",
        headers=ADMIN_HEADERS,
    )
    assert metadata_content.status_code == 200
    metadata_body = metadata_content.json()
    assert metadata_body["text"] is None
    assert metadata_body["blob"]["content_kind"] == "metadata"
    assert metadata_body["blob"]["encryption_status"] == "metadata_only"
    assert metadata_body["blob"]["redaction_status"] == "metadata_only"
    assert metadata_body["blob"]["byte_count"] == 128
    assert metadata_body["blob"]["metadata"] == command_metadata
    assert len(metadata_body["blob"]["checksum"]) == 64

    content_backup = client.get(
        "/backup",
        params={"include_agent_context_content": True},
        headers=ADMIN_HEADERS,
    )
    assert content_backup.status_code == 200
    assert content_backup.json()["metadata"]["agent_context_content_blob_count"] == 0
    assert content_backup.json()["bundle"]["agent_context_blob_contents"] == []
    assert oversized_text not in str(content_backup.json())

    with client.app.state.repository.engine.begin() as conn:
        stored_blobs = conn.execute(db.agent_context_blobs.select()).mappings().all()
        assert {blob["id"] for blob in stored_blobs} == {
            oversized_event["blob_id"],
            metadata_event["blob_id"],
        }
        assert all(blob["encrypted_content"] is None for blob in stored_blobs)


def test_graph_research_creates_reviewable_proposals_and_action_gate() -> None:
    client = make_client()

    response = client.post(
        "/graph/research?graph_id=project-default",
        headers=ADMIN_HEADERS,
        json={"query": "Research AI planning mode source provenance", "lens": "research", "source_policy": "mixed"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["research_task"]["status"] == "proposal_ready"
    assert body["research_task"]["project_id"] == "project-default"
    assert body["agent_run"]["project_id"] == "project-default"
    assert body["source"]["kind"] == "markdown"
    assert body["proposals"]
    assert all(proposal["status"] == "pending_review" for proposal in body["proposals"])
    assert body["agent_run"]["status"] == "waiting_for_review"
    action = body["agent_run"]["action_proposals"][0]
    assert action["status"] == "pending_review"

    other_run = client.post(
        "/agent-runs",
        headers=ADMIN_HEADERS,
        json={"kind": "research", "input": {"query": "Different run"}},
    )
    assert other_run.status_code == 201
    wrong_run = client.post(
        f"/agent-runs/{other_run.json()['id']}/approve-action",
        headers=ADMIN_HEADERS,
        json={"action_proposal_id": action["id"], "decision": "approve", "rationale": "Wrong run."},
    )
    assert wrong_run.status_code == 404

    approved = client.post(
        f"/agent-runs/{body['agent_run']['id']}/approve-action",
        headers=ADMIN_HEADERS,
        json={"action_proposal_id": action["id"], "decision": "approve", "rationale": "Reviewed proposal gate."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "applied"


def test_graph_activity_orders_filters_by_lens_and_since() -> None:
    client = make_client()
    source = client.post(
        "/sources",
        headers=ADMIN_HEADERS,
        json={"kind": "markdown", "title": "Activity lens source", "uri": "file://activity.md"},
    ).json()
    research_proposal = client.post(
        "/proposals",
        headers=ADMIN_HEADERS,
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {
                "label": "Research Activity Concept",
                "kind": "concept",
                "metadata": {"extractionLenses": ["research"]},
            },
        },
    ).json()
    engineering_proposal = client.post(
        "/proposals",
        headers=ADMIN_HEADERS,
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {
                "label": "Engineering Activity Component",
                "kind": "component",
                "metadata": {"extractionLenses": ["engineering"]},
            },
        },
    ).json()

    response = client.get("/graph/activity", params={"limit": 20}, headers=READER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["returned_count"] == len(body["events"])
    assert [event["created_at"] for event in body["events"]] == sorted(
        [event["created_at"] for event in body["events"]],
        reverse=True,
    )

    engineering = client.get("/graph/activity", params={"lens": "engineering", "limit": 20}, headers=READER_HEADERS)
    assert engineering.status_code == 200
    engineering_proposal_ids = {
        ref["id"]
        for event in engineering.json()["events"]
        if event["event_type"] == "proposal.created"
        for ref in event["object_refs"]
        if ref["kind"] == "proposal"
    }
    assert engineering_proposal["id"] in engineering_proposal_ids
    assert research_proposal["id"] not in engineering_proposal_ids

    oldest_timestamp = body["events"][-1]["created_at"]
    since = client.get("/graph/activity", params={"since": oldest_timestamp, "limit": 20}, headers=READER_HEADERS)
    assert since.status_code == 200
    assert all(event["created_at"] > oldest_timestamp for event in since.json()["events"])


def test_graph_activity_requires_reader_permission() -> None:
    client = make_client()

    allowed = client.get("/graph/activity", headers=READER_HEADERS)
    denied = client.get("/graph/activity", headers={"X-Graphview-User": "unknown"})

    assert allowed.status_code == 200
    assert denied.status_code == 401


def test_graph_activity_records_proposal_review_and_research_events() -> None:
    client = make_client()
    source = client.post(
        "/sources",
        headers=ADMIN_HEADERS,
        json={"kind": "text", "title": "Activity review source"},
    ).json()
    proposal = client.post(
        "/proposals",
        headers=ADMIN_HEADERS,
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"label": "Activity Reviewed Node", "kind": "concept"},
        },
    ).json()
    reviewed = client.post(
        "/review-decisions",
        headers=ADMIN_HEADERS,
        json={"proposal_id": proposal["id"], "decision": "accept", "rationale": "Activity test."},
    )
    assert reviewed.status_code == 201

    activity = client.get("/graph/activity", params={"limit": 50}, headers=READER_HEADERS).json()["events"]
    event_types = {event["event_type"] for event in activity}
    assert {"proposal.created", "proposal.reviewed", "graph.node_committed"} <= event_types
    reviewed_event = next(event for event in activity if event["event_type"] == "proposal.reviewed")
    assert any(ref["kind"] == "proposal" and ref["id"] == proposal["id"] for ref in reviewed_event["object_refs"])

    researched = client.post(
        "/graph/research?graph_id=project-default",
        headers=ADMIN_HEADERS,
        json={"query": "Activity event research", "lens": "research", "source_policy": "mixed"},
    )
    assert researched.status_code == 201
    research_body = researched.json()
    research_events = client.get("/graph/activity", params={"limit": 100}, headers=READER_HEADERS).json()["events"]
    research_event_types = {event["event_type"] for event in research_events}
    assert {"agent.run.waiting_for_review", "research.proposal_ready", "agent.action_proposed"} <= research_event_types

    agent_activity = client.get(
        f"/agent-runs/{research_body['agent_run']['id']}/activity",
        params={"limit": 10},
        headers=READER_HEADERS,
    )
    assert agent_activity.status_code == 200
    agent_events = agent_activity.json()["events"]
    assert agent_events
    assert all(
        event["payload"].get("agent_run_id") == research_body["agent_run"]["id"]
        or any(ref["kind"] == "agent_run" and ref["id"] == research_body["agent_run"]["id"] for ref in event["object_refs"])
        for event in agent_events
    )


def test_graph_activity_stream_frames_heartbeat_and_bounded_events() -> None:
    client = make_client()
    created = client.post(
        "/ingestion-runs",
        headers=ADMIN_HEADERS,
        json={
            "kind": "text",
            "title": "Activity stream source",
            "content": "Activity stream events need bounded server-sent event framing.",
            "proposal_limit": 2,
        },
    )
    assert created.status_code == 201

    with client.stream("GET", "/graph/activity/stream", params={"limit": 2}, headers=READER_HEADERS) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        payload = "".join(response.iter_text())

    assert payload.startswith(": heartbeat\n\n")
    assert "event: graph.activity\n" in payload
    assert "data: " in payload
    assert payload.count("event: graph.activity") <= 2


def test_phase26_action_policy_is_configurable_and_source_actions_are_scoped() -> None:
    settings = Settings(database_url="sqlite://", safe_action_types="create_notification")
    client = make_client(settings)
    source = client.post(
        "/sources",
        headers=ADMIN_HEADERS,
        json={"kind": "url", "title": "Scoped source", "uri": "https://example.invalid/scoped"},
    ).json()
    stale_proposal = client.post(
        "/action-proposals",
        headers=ADMIN_HEADERS,
        json={
            "action_type": "mark_source_stale",
            "title": "Mark scoped source stale",
            "summary": "Should be denied by the configured allowlist.",
            "payload": {"source_id": source["id"]},
        },
    ).json()
    approved = client.post(
        f"/action-proposals/{stale_proposal['id']}/approve",
        headers=ADMIN_HEADERS,
        json={"rationale": "Approved but not allowlisted for execution."},
    )
    assert approved.status_code == 200

    denied_run = client.post(
        "/action-runs",
        headers=ADMIN_HEADERS,
        json={"action_proposal_id": stale_proposal["id"]},
    )
    assert denied_run.status_code == 409
    assert "allowlist" in denied_run.json()["detail"]

    default_client = make_client()
    missing_source_proposal = default_client.post(
        "/action-proposals",
        headers=ADMIN_HEADERS,
        json={
            "action_type": "mark_source_stale",
            "title": "Mark missing source stale",
            "summary": "Should fail without mutating any source.",
            "payload": {"source_id": "source-missing-phase26"},
        },
    ).json()
    assert default_client.post(
        f"/action-proposals/{missing_source_proposal['id']}/approve",
        headers=ADMIN_HEADERS,
        json={"rationale": "Approved missing source execution test."},
    ).status_code == 200

    failed_run = default_client.post(
        "/action-runs",
        headers=ADMIN_HEADERS,
        json={"action_proposal_id": missing_source_proposal["id"]},
    )
    assert failed_run.status_code == 201
    assert failed_run.json()["status"] == "failed"
    assert failed_run.json()["error_code"] == "source_not_found"


def test_migrations_are_linear_through_graphview_v1_foundation() -> None:
    migration_dir = Path(__file__).parents[1] / "migrations" / "versions"
    revisions: dict[str, str | None] = {}

    for path in sorted(migration_dir.glob("*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        revisions[module.revision] = module.down_revision

    assert len(revisions) == len(list(migration_dir.glob("*.py")))
    assert list(revisions.values()).count(None) == 1
    assert revisions["20260605_0008"] == "20260605_0007"
    assert revisions["20260606_0009"] == "20260605_0008"
    assert revisions["20260614_0010"] == "20260606_0009"
    assert revisions["20260710_0011"] == "20260614_0010"
    assert revisions["20260710_0012"] == "20260710_0011"
    assert revisions["20260710_0013"] == "20260710_0012"
    assert revisions["20260710_0014"] == "20260710_0013"
    assert revisions["20260710_0015"] == "20260710_0014"
    assert revisions["20260710_0016"] == "20260710_0015"
    assert revisions["20260710_0017"] == "20260710_0016"

    seen: set[str] = set()
    current = "20260710_0017"
    while current is not None:
        assert current not in seen
        seen.add(current)
        current = revisions[current]

    assert seen == set(revisions)


def test_phase25_digital_nervous_system_routes_executes_observes_and_learns() -> None:
    client = make_client()
    source = client.post(
        "/sources",
        headers=ADMIN_HEADERS,
        json={"kind": "url", "title": "Runbook", "uri": "https://example.invalid/runbook"},
    ).json()
    owner = client.post(
        "/owners",
        headers=ADMIN_HEADERS,
        json={"owner_type": "team", "display_name": "Knowledge Ops", "scope_kind": "project"},
    )
    assert owner.status_code == 201
    policy = client.post(
        "/routing-policies",
        headers=ADMIN_HEADERS,
        json={
            "name": "Source freshness routing",
            "match": {"signal_kinds": ["source_changed"], "source_kinds": ["manual"]},
            "severity": "high",
            "owner_id": owner.json()["id"],
            "sla_seconds": 3600,
            "suggested_actions": ["mark_source_stale"],
        },
    )
    assert policy.status_code == 201

    signal = client.post(
        "/signals",
        headers=ADMIN_HEADERS,
        json={
            "kind": "source_changed",
            "severity": "medium",
            "source_kind": "manual",
            "source_id": source["id"],
            "title": "Runbook changed upstream",
            "summary": "The source URI changed and needs graph review.",
            "payload": {"api_key": "secret-token", "nested": {"password": "hidden"}},
        },
    )
    assert signal.status_code == 201
    signal_body = signal.json()
    assert signal_body["status"] == "routed"
    assert signal_body["payload"]["api_key"] == "[redacted]"
    assert signal_body["payload"]["nested"]["password"] == "[redacted]"

    observations = client.get("/observations", params={"signal_id": signal_body["id"]}, headers=READER_HEADERS)
    assert observations.status_code == 200
    assert observations.json()["observations"][0]["signal_id"] == signal_body["id"]
    alerts = client.get("/alerts", headers=READER_HEADERS).json()["alerts"]
    assert alerts[0]["owner_id"] == owner.json()["id"]
    assert alerts[0]["policy_id"] == policy.json()["id"]
    assert alerts[0]["severity"] == "high"
    attention = client.get("/attention", headers=READER_HEADERS).json()["items"]
    assert attention[0]["status"] == "assigned"
    assert attention[0]["sla_status"] == "at_risk"
    assert attention[0]["suggested_actions"] == ["mark_source_stale"]

    moved = client.post(
        f"/attention/{attention[0]['id']}/transition",
        headers=ADMIN_HEADERS,
        json={"status": "waiting_for_review", "rationale": "Needs a reviewer decision."},
    )
    assert moved.status_code == 200
    decision = client.post(
        "/decision-records",
        headers=ADMIN_HEADERS,
        json={
            "attention_item_id": attention[0]["id"],
            "decision": "approve",
            "rationale": "Mark stale so the graph can surface refresh work.",
        },
    )
    assert decision.status_code == 201

    proposal = client.post(
        "/action-proposals",
        headers=ADMIN_HEADERS,
        json={
            "decision_record_id": decision.json()["id"],
            "attention_item_id": attention[0]["id"],
            "action_type": "mark_source_stale",
            "title": "Mark runbook stale",
            "summary": "Flag the source as stale until the upstream page is re-ingested.",
            "payload": {"source_id": source["id"], "secret": "source-secret"},
        },
    )
    assert proposal.status_code == 201
    proposal_body = proposal.json()
    assert proposal_body["status"] == "pending_review"
    assert proposal_body["redacted_payload"]["secret"] == "[redacted]"
    assert "source-secret" not in str(proposal_body)

    approved = client.post(
        f"/action-proposals/{proposal_body['id']}/approve",
        headers=ADMIN_HEADERS,
        json={"rationale": "Reviewed and safe graph mutation."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    action_run = client.post(
        "/action-runs",
        headers=ADMIN_HEADERS,
        json={"action_proposal_id": proposal_body["id"]},
    )
    assert action_run.status_code == 201
    run_body = action_run.json()
    assert run_body["status"] == "succeeded"
    assert run_body["redacted_payload"]["secret"] == "[redacted]"
    stale_source = next(
        item for item in client.get("/sources", headers=READER_HEADERS).json()["sources"] if item["id"] == source["id"]
    )
    assert stale_source["stale_at"]

    outcome = client.post(
        f"/action-runs/{run_body['id']}/outcome",
        headers=ADMIN_HEADERS,
        json={
            "attention_item_id": attention[0]["id"],
            "status": "resolved",
            "title": "Refresh task queued",
            "summary": "The stale source is visible to graph reviewers.",
            "result": {"stale_source_id": source["id"]},
        },
    )
    assert outcome.status_code == 201
    feedback = client.post(
        "/feedback-events",
        headers=ADMIN_HEADERS,
        json={
            "outcome_id": outcome.json()["id"],
            "action_run_id": run_body["id"],
            "attention_item_id": attention[0]["id"],
            "kind": "source_freshness",
            "summary": "Routing policy correctly captured the stale source.",
            "effect": {"confidence_delta": 0.05},
        },
    )
    assert feedback.status_code == 201

    activity = client.get("/graph/activity", params={"limit": 50}, headers=READER_HEADERS).json()["events"]
    event_types = {event["event_type"] for event in activity}
    assert {
        "signal.created",
        "observation.created",
        "alert.routed",
        "attention.assigned",
        "decision.recorded",
        "action.proposed",
        "action.approved",
        "action.run.succeeded",
        "outcome.resolved",
        "feedback.recorded",
    } <= event_types
    assert any(ref["kind"] == "attention" and ref["id"] == attention[0]["id"] for event in activity for ref in event["object_refs"])

    backup = client.get("/backup", headers=ADMIN_HEADERS)
    assert backup.status_code == 200
    bundle = backup.json()["bundle"]
    assert bundle["signals"][0]["id"] == signal_body["id"]
    assert bundle["attention_items"][0]["id"] == attention[0]["id"]
    assert bundle["action_proposals"][0]["redacted_payload"]["secret"] == "[redacted]"
    assert "source-secret" not in str(bundle)


def test_phase25_action_runs_require_approval_and_operate_permission() -> None:
    client = make_client()
    denied = client.post(
        "/owners",
        headers=READER_HEADERS,
        json={"owner_type": "team", "display_name": "Reader owned", "scope_kind": "project"},
    )
    assert denied.status_code == 403

    proposal = client.post(
        "/action-proposals",
        headers=ADMIN_HEADERS,
        json={
            "action_type": "create_notification",
            "title": "Notify source owner",
            "summary": "Create a safe notification after review.",
            "payload": {"target": "owner-team", "message": "Please refresh the source."},
        },
    )
    assert proposal.status_code == 201
    assert proposal.json()["status"] == "pending_review"

    reader_run = client.post(
        "/action-runs",
        headers=READER_HEADERS,
        json={"action_proposal_id": proposal.json()["id"]},
    )
    assert reader_run.status_code == 403

    unapproved_run = client.post(
        "/action-runs",
        headers=ADMIN_HEADERS,
        json={"action_proposal_id": proposal.json()["id"]},
    )
    assert unapproved_run.status_code == 409
    assert "approved" in unapproved_run.json()["detail"]


def test_text_ingestion_creates_source_run_proposal_and_embedding() -> None:
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "text",
            "title": "Knowledge Architecture",
            "content": "Knowledge Architecture connects sources, provenance, and review decisions.",
            "proposal_limit": 2,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"]["checksum"]
    assert body["ingestion_run"]["status"] == "proposal_ready"
    assert body["proposals"][0]["provenance"][0]["extractedBy"] == "worker"
    assert body["embeddings"][0]["embedding_model"] == "graphview-local-hash-v1"
    assert len(body["embeddings"][0]["vector"]) == 16

    chunks = client.get("/source-chunks", params={"source_id": body["source"]["id"]}, headers=READER_HEADERS)
    assert chunks.status_code == 200
    assert any("Knowledge Architecture connects sources" in chunk["text"] for chunk in chunks.json()["source_chunks"])

    proposal_id = body["proposals"][0]["id"]
    decision = client.post("/review-decisions", json={"proposal_id": proposal_id, "decision": "accept"})
    assert decision.status_code == 201
    exported = client.get("/export", headers=ADMIN_HEADERS).json()
    embedding = next(item for item in exported["embeddings"] if item["proposal_id"] == proposal_id)
    assert embedding["content_node_id"] == exported["nodes"][0]["id"]


def test_url_ingestion_fetches_from_backend(monkeypatch) -> None:
    from graphview_api import ingestion

    async def fake_fetch_url_text(uri: str) -> str:
        assert uri == "https://example.invalid/research"
        return "Fetched Research Note describes Graphview ingestion."

    monkeypatch.setattr(ingestion, "fetch_url_text", fake_fetch_url_text)
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "url",
            "title": "Fetched note",
            "uri": "https://example.invalid/research",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"]["uri"] == "https://example.invalid/research"
    assert body["proposals"][0]["proposed_value"]["label"] in {
        "Fetched Research Note",
        "Graphview",
        "Fetched note",
    }


def test_repository_ingestion_extracts_symbols_and_dependencies() -> None:
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "repository",
            "title": "Graphview web repository",
            "content": 'apps/web/src/App.tsx\nfunction GraphCanvas() {}\nimport "react";\nIssue #42 documents provenance.',
            "proposal_limit": 6,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"]["kind"] == "repository"
    labels = {
        proposal["proposed_value"]["label"]
        for proposal in body["proposals"]
        if proposal["kind"] == "content_node"
    }
    assert "Path apps/web/src/App.tsx" in labels
    assert "Symbol GraphCanvas" in labels
    assert "Dependency react" in labels
    symbol = next(proposal for proposal in body["proposals"] if proposal["proposed_value"]["label"] == "Symbol GraphCanvas")
    assert symbol["proposed_value"]["kind"] == "symbol"
    assert symbol["proposed_value"]["metadata"]["extractionLenses"] == ["engineering"]
    dependency = next(proposal for proposal in body["proposals"] if proposal["proposed_value"]["label"] == "Dependency react")
    assert dependency["proposed_value"]["kind"] == "package"
    edge = next(proposal for proposal in body["proposals"] if proposal["kind"] == "semantic_edge")
    assert edge["proposed_value"]["relation"] in {"contains", "defines", "imports", "references", "mentions"}
    assert edge["proposed_value"]["sourceNodeId"]
    assert edge["proposed_value"]["targetNodeId"]


def test_repository_edge_proposal_commits_after_endpoint_nodes_are_accepted() -> None:
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "repository",
            "title": "Relationship repository",
            "content": 'function GraphCanvas() {}\nimport "react";',
            "proposal_limit": 10,
        },
    )

    assert response.status_code == 201
    proposals = response.json()["proposals"]
    edge = next(proposal for proposal in proposals if proposal["kind"] == "semantic_edge")

    early_edge = client.post("/review-decisions", json={"proposal_id": edge["id"], "decision": "accept"})
    assert early_edge.status_code == 409

    edge_node_ids = {edge["proposed_value"]["sourceNodeId"], edge["proposed_value"]["targetNodeId"]}
    for proposal in proposals:
        if proposal["kind"] == "content_node" and proposal["proposed_value"]["id"] in edge_node_ids:
            accepted = client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"})
            assert accepted.status_code == 201

    accepted_edge = client.post("/review-decisions", json={"proposal_id": edge["id"], "decision": "accept"})
    assert accepted_edge.status_code == 201
    graph = client.get("/graph").json()
    assert graph["edges"][0]["source_node_id"] == edge["proposed_value"]["sourceNodeId"]
    assert graph["edges"][0]["target_node_id"] == edge["proposed_value"]["targetNodeId"]

    edge_lineage = client.get(f"/lineage/edge/{graph['edges'][0]['id']}", headers=READER_HEADERS)
    assert edge_lineage.status_code == 200
    edge_trace = edge_lineage.json()
    assert edge_trace["source"]["kind"] == "repository"
    assert edge_trace["proposals"][0]["kind"] == "semantic_edge"
    assert edge_trace["review_decisions"][0]["decision"] == "accept"
    assert {node["id"] for node in edge_trace["nodes"]} == edge_node_ids

    node_lineage = client.get(f"/lineage/node/{edge['proposed_value']['sourceNodeId']}", headers=READER_HEADERS)
    assert node_lineage.status_code == 200
    assert node_lineage.json()["proposals"][0]["kind"] == "content_node"

    source_id = response.json()["source"]["id"]
    source_lineage = client.get(f"/lineage/source/{source_id}", headers=READER_HEADERS)
    assert source_lineage.status_code == 200
    assert len(source_lineage.json()["proposals"]) >= 3


def test_lineage_rejects_unknown_entity() -> None:
    client = make_client()

    response = client.get("/lineage/node/missing", headers=READER_HEADERS)

    assert response.status_code == 404


def test_graph_insights_summarize_review_progress_and_quality() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Insight source"}).json()
    first = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-insight-a", "label": "Insight A", "kind": "concept"},
        },
    ).json()
    second = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-insight-b", "label": "Insight B", "kind": "decision"},
        },
    ).json()

    assert client.post("/review-decisions", json={"proposal_id": first["id"], "decision": "accept"}).status_code == 201
    assert client.post("/review-decisions", json={"proposal_id": second["id"], "decision": "accept"}).status_code == 201

    edge = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {
                "id": "edge-insight-a-b",
                "sourceNodeId": "node-insight-a",
                "targetNodeId": "node-insight-b",
                "relation": "supports",
            },
        },
    ).json()
    assert client.post("/review-decisions", json={"proposal_id": edge["id"], "decision": "accept"}).status_code == 201

    response = client.get("/insights", headers=READER_HEADERS)

    assert response.status_code == 200
    insights = response.json()
    assert insights["node_count"] == 2
    assert insights["edge_count"] == 1
    assert insights["source_count"] == 1
    assert insights["proposal_count"] == 3
    assert insights["pending_proposal_count"] == 0
    assert insights["review_decision_count"] == 3
    assert insights["connected_edge_count"] == 1
    assert insights["orphan_edge_count"] == 0
    assert insights["provenance_coverage"]["coverage_percent"] == 100.0
    assert {"name": "supports", "count": 1} in insights["relation_counts"]
    assert insights["top_nodes"][0]["degree"] == 1


def test_graph_neighborhood_returns_bounded_focus_graph() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Neighborhood source"}).json()
    node_payloads = [
        {"id": "node-neighborhood-a", "label": "Neighborhood A", "kind": "concept"},
        {"id": "node-neighborhood-b", "label": "Neighborhood B", "kind": "concept"},
        {"id": "node-neighborhood-c", "label": "Neighborhood C", "kind": "concept"},
    ]
    for payload in node_payloads:
        proposal = client.post(
            "/proposals",
            json={"source_id": source["id"], "kind": "content_node", "proposed_value": payload},
        ).json()
        assert client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"}).status_code == 201

    for edge_payload in [
        {
            "id": "edge-neighborhood-a-b",
            "sourceNodeId": "node-neighborhood-a",
            "targetNodeId": "node-neighborhood-b",
            "relation": "supports",
        },
        {
            "id": "edge-neighborhood-b-c",
            "sourceNodeId": "node-neighborhood-b",
            "targetNodeId": "node-neighborhood-c",
            "relation": "depends_on",
        },
    ]:
        proposal = client.post(
            "/proposals",
            json={"source_id": source["id"], "kind": "semantic_edge", "proposed_value": edge_payload},
        ).json()
        assert client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"}).status_code == 201

    response = client.get("/graph/neighborhood/node-neighborhood-a", headers=READER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["center_node"]["id"] == "node-neighborhood-a"
    assert body["depth"] == 1
    assert {node["id"] for node in body["nodes"]} == {"node-neighborhood-a", "node-neighborhood-b"}
    assert {edge["id"] for edge in body["edges"]} == {"edge-neighborhood-a-b"}

    depth_two = client.get("/graph/neighborhood/node-neighborhood-a", params={"depth": 2}, headers=READER_HEADERS)
    assert {node["id"] for node in depth_two.json()["nodes"]} == {
        "node-neighborhood-a",
        "node-neighborhood-b",
        "node-neighborhood-c",
    }

    missing = client.get("/graph/neighborhood/missing-node", headers=READER_HEADERS)
    assert missing.status_code == 404


def test_graph_path_returns_bounded_shortest_connection() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Path source"}).json()
    for payload in [
        {"id": "node-path-a", "label": "Path A", "kind": "concept"},
        {"id": "node-path-b", "label": "Path B", "kind": "concept"},
        {"id": "node-path-c", "label": "Path C", "kind": "concept"},
        {"id": "node-path-d", "label": "Path D", "kind": "concept"},
    ]:
        proposal = client.post(
            "/proposals",
            json={"source_id": source["id"], "kind": "content_node", "proposed_value": payload},
        ).json()
        assert client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"}).status_code == 201

    for edge_payload in [
        {
            "id": "edge-path-a-b",
            "sourceNodeId": "node-path-a",
            "targetNodeId": "node-path-b",
            "relation": "supports",
        },
        {
            "id": "edge-path-b-c",
            "sourceNodeId": "node-path-b",
            "targetNodeId": "node-path-c",
            "relation": "depends_on",
        },
    ]:
        proposal = client.post(
            "/proposals",
            json={"source_id": source["id"], "kind": "semantic_edge", "proposed_value": edge_payload},
        ).json()
        assert client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"}).status_code == 201

    response = client.get(
        "/graph/path",
        params={"source_node_id": "node-path-a", "target_node_id": "node-path-c", "max_depth": 2},
        headers=READER_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["path_found"] is True
    assert body["distance"] == 2
    assert [node["id"] for node in body["nodes"]] == ["node-path-a", "node-path-b", "node-path-c"]
    assert [edge["id"] for edge in body["edges"]] == ["edge-path-a-b", "edge-path-b-c"]

    too_shallow = client.get(
        "/graph/path",
        params={"source_node_id": "node-path-a", "target_node_id": "node-path-c", "max_depth": 1},
        headers=READER_HEADERS,
    )
    assert too_shallow.status_code == 200
    assert too_shallow.json()["path_found"] is False

    disconnected = client.get(
        "/graph/path",
        params={"source_node_id": "node-path-a", "target_node_id": "node-path-d", "max_depth": 4},
        headers=READER_HEADERS,
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["path_found"] is False

    missing = client.get(
        "/graph/path",
        params={"source_node_id": "node-path-a", "target_node_id": "missing-node"},
        headers=READER_HEADERS,
    )
    assert missing.status_code == 404


def test_review_queue_prioritizes_ready_and_blocked_proposals() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Queue source"}).json()
    for payload in [
        {"id": "node-queue-a", "label": "Queue A", "kind": "concept"},
        {"id": "node-queue-b", "label": "Queue B", "kind": "concept"},
    ]:
        proposal = client.post(
            "/proposals",
            json={"source_id": source["id"], "kind": "content_node", "proposed_value": payload},
        ).json()
        assert client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"}).status_code == 201

    ready_edge = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {
                "id": "edge-queue-a-b",
                "sourceNodeId": "node-queue-a",
                "targetNodeId": "node-queue-b",
                "relation": "supports",
            },
        },
    ).json()
    blocked_edge = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {
                "id": "edge-queue-a-missing",
                "sourceNodeId": "node-queue-a",
                "targetNodeId": "node-queue-missing",
                "relation": "mentions",
            },
        },
    ).json()
    node = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "confidence": 0.91,
            "proposed_value": {"id": "node-queue-c", "label": "Queue C", "kind": "concept"},
        },
    ).json()

    response = client.get("/review-queue", headers=READER_HEADERS)

    assert response.status_code == 200
    queue = response.json()
    assert queue["pending_count"] == 3
    assert queue["ready_count"] == 2
    assert queue["blocked_count"] == 1
    assert queue["items"][0]["proposal"]["id"] == ready_edge["id"]
    assert queue["items"][0]["action"] == "review_relationship"
    assert queue["items"][0]["ready_to_commit"] is True
    assert queue["items"][1]["proposal"]["id"] == node["id"]
    blocked = next(item for item in queue["items"] if item["proposal"]["id"] == blocked_edge["id"])
    assert blocked["action"] == "accept_endpoints"
    assert blocked["blocked"] is True
    assert blocked["missing_endpoint_node_ids"] == ["node-queue-missing"]
    assert blocked["source"]["id"] == source["id"]


def test_review_dashboard_summarizes_review_operations() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Dashboard source"}).json()
    accepted_payloads = [
        {"id": "node-dashboard-a", "label": "Dashboard A", "kind": "concept"},
        {"id": "node-dashboard-b", "label": "Dashboard B", "kind": "concept"},
    ]
    for payload in accepted_payloads:
        proposal = client.post(
            "/proposals",
            json={"source_id": source["id"], "kind": "content_node", "proposed_value": payload},
        ).json()
        assert client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"}).status_code == 201

    rejected = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-dashboard-rejected", "label": "Rejected", "kind": "concept"},
        },
    ).json()
    assert client.post("/review-decisions", json={"proposal_id": rejected["id"], "decision": "reject"}).status_code == 201

    deferred = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-dashboard-deferred", "label": "Deferred", "kind": "decision"},
        },
    ).json()
    assert (
        client.post(
            "/review-decisions",
            headers=ADMIN_HEADERS,
            json={"proposal_id": deferred["id"], "decision": "defer"},
        ).status_code
        == 201
    )

    ready_edge = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {
                "id": "edge-dashboard-ready",
                "sourceNodeId": "node-dashboard-a",
                "targetNodeId": "node-dashboard-b",
                "relation": "supports",
            },
        },
    ).json()
    blocked_edge = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "semantic_edge",
            "proposed_value": {
                "id": "edge-dashboard-blocked",
                "sourceNodeId": "node-dashboard-a",
                "targetNodeId": "node-dashboard-missing",
                "relation": "mentions",
            },
        },
    ).json()

    response = client.get("/review-dashboard", headers=READER_HEADERS)

    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["proposal_count"] == 6
    assert dashboard["pending_count"] == 2
    assert dashboard["ready_count"] == 1
    assert dashboard["blocked_count"] == 1
    assert dashboard["review_decision_count"] == 4
    assert dashboard["accepted_count"] == 2
    assert dashboard["rejected_count"] == 1
    assert dashboard["edited_count"] == 0
    assert dashboard["deferred_count"] == 1
    assert dashboard["acceptance_rate"] == 50.0
    assert dashboard["commit_rate"] == 50.0
    assert {"name": "content_node", "count": 4} in dashboard["proposal_kind_counts"]
    assert {"name": "semantic_edge", "count": 2} in dashboard["pending_kind_counts"]
    assert {"name": "accept", "count": 2} in dashboard["decision_counts"]
    assert {"name": "user-researcher", "count": 3} in dashboard["reviewer_counts"]
    assert {"name": "user-maintainer", "count": 1} in dashboard["reviewer_counts"]
    assert dashboard["oldest_pending_proposal_id"] in {ready_edge["id"], blocked_edge["id"]}
    assert dashboard["oldest_pending_created_at"]


def test_review_activity_lists_recent_decisions_with_sources() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Activity source"}).json()
    accepted = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-activity-accepted", "label": "Activity Accepted", "kind": "concept"},
        },
    ).json()
    rejected = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-activity-rejected", "label": "Activity Rejected", "kind": "concept"},
        },
    ).json()
    deferred = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-activity-deferred", "label": "Activity Deferred", "kind": "decision"},
        },
    ).json()

    assert client.post("/review-decisions", json={"proposal_id": accepted["id"], "decision": "accept"}).status_code == 201
    assert client.post("/review-decisions", json={"proposal_id": rejected["id"], "decision": "reject"}).status_code == 201
    assert client.post("/review-decisions", json={"proposal_id": deferred["id"], "decision": "defer"}).status_code == 201

    response = client.get("/review-activity", params={"limit": 2}, headers=READER_HEADERS)

    assert response.status_code == 200
    activity = response.json()
    assert activity["review_decision_count"] == 3
    assert activity["returned_count"] == 2
    assert len(activity["items"]) == 2
    assert activity["items"][0]["decision"]["decision"] == "defer"
    assert activity["items"][0]["proposal"]["id"] == deferred["id"]
    assert activity["items"][0]["source"]["id"] == source["id"]
    assert activity["items"][0]["summary"] == "Deferred node proposal Activity Deferred."
    assert activity["items"][1]["proposal"]["id"] == rejected["id"]


def test_source_review_coverage_summarizes_sources_by_review_state() -> None:
    client = make_client()
    mixed_source = client.post("/sources", json={"kind": "text", "title": "Mixed source"}).json()
    reviewed_source = client.post("/sources", json={"kind": "markdown", "title": "Reviewed source"}).json()
    empty_source = client.post("/sources", json={"kind": "text", "title": "Empty source"}).json()

    accepted = client.post(
        "/proposals",
        json={
            "source_id": mixed_source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-source-mixed-a", "label": "Mixed A", "kind": "concept"},
        },
    ).json()
    pending = client.post(
        "/proposals",
        json={
            "source_id": mixed_source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-source-mixed-b", "label": "Mixed B", "kind": "concept"},
        },
    ).json()
    rejected = client.post(
        "/proposals",
        json={
            "source_id": reviewed_source["id"],
            "kind": "content_node",
            "proposed_value": {"id": "node-source-reviewed", "label": "Reviewed", "kind": "decision"},
        },
    ).json()

    assert client.post("/review-decisions", json={"proposal_id": accepted["id"], "decision": "accept"}).status_code == 201
    assert client.post("/review-decisions", json={"proposal_id": rejected["id"], "decision": "reject"}).status_code == 201

    response = client.get("/review-sources", params={"limit": 2}, headers=READER_HEADERS)

    assert response.status_code == 200
    coverage = response.json()
    assert coverage["source_count"] == 3
    assert coverage["proposal_count"] == 3
    assert coverage["pending_count"] == 1
    assert coverage["reviewed_count"] == 2
    assert coverage["returned_count"] == 2
    assert coverage["sources"][0]["source"]["id"] == mixed_source["id"]
    assert coverage["sources"][0]["status"] == "mixed"
    assert coverage["sources"][0]["proposal_count"] == 2
    assert coverage["sources"][0]["pending_count"] == 1
    assert coverage["sources"][0]["reviewed_count"] == 1
    assert coverage["sources"][0]["accepted_count"] == 1
    assert coverage["sources"][0]["last_reviewed_at"]
    assert coverage["sources"][1]["source"]["id"] == reviewed_source["id"]
    assert coverage["sources"][1]["status"] == "reviewed"
    assert coverage["sources"][1]["rejected_count"] == 1
    assert pending["status"] == "pending_review"
    assert empty_source["id"] not in {item["source"]["id"] for item in coverage["sources"]}


def test_ops_document_ingestion_extracts_owner_review_metadata() -> None:
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "ops-document",
            "title": "Incident Response Policy",
            "content": "# Incident Response Policy\nOwner: Platform Ops\nReview: quarterly\nVendor Escalation Process",
            "proposal_limit": 5,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"]["kind"] == "ops-document"
    policy = next(
        proposal["proposed_value"]
        for proposal in body["proposals"]
        if "ops" in proposal["proposed_value"].get("metadata", {}).get("extractionLenses", [])
    )
    assert policy["metadata"]["extractionLenses"] == ["ops"]
    assert policy["metadata"]["owner"] == "Platform Ops"
    assert policy["metadata"]["reviewCycle"] == "quarterly"
    labels = {
        proposal["proposed_value"]["label"]
        for proposal in body["proposals"]
        if proposal["kind"] == "content_node"
    }
    assert "Vendor Escalation Process" in labels


def test_research_ingestion_does_not_force_other_lenses() -> None:
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "markdown",
            "title": "Research Memo",
            "content": "# Research Memo\nConceptual notes about Graphview provenance and review quality.",
            "proposal_limit_per_lens": 4,
        },
    )

    assert response.status_code == 201
    proposals = response.json()["proposals"]
    lenses = {
        lens
        for proposal in proposals
        for lens in proposal["proposed_value"].get("metadata", {}).get("extractionLenses", [])
    }
    assert lenses == {"research"}


def test_reviewed_metadata_and_graph_lens_filtering() -> None:
    client = make_client()

    response = client.post(
        "/ingestion-runs",
        json={
            "kind": "repository",
            "title": "Lens repository",
            "content": 'src/main.ts\nfunction LensGraph() {}\nimport "react";',
            "proposal_limit_per_lens": 6,
        },
    )
    assert response.status_code == 201
    proposals = response.json()["proposals"]
    symbol = next(proposal for proposal in proposals if proposal["proposed_value"].get("label") == "Symbol LensGraph")

    accepted = client.post("/review-decisions", json={"proposal_id": symbol["id"], "decision": "accept"})
    assert accepted.status_code == 201

    engineering_graph = client.get("/graph", params={"lens": "engineering"})
    ops_graph = client.get("/graph", params={"lens": "ops"})

    assert engineering_graph.status_code == 200
    symbol_node = next(node for node in engineering_graph.json()["nodes"] if node["label"] == "Symbol LensGraph")
    assert symbol_node["metadata"]["extractionLenses"] == ["engineering"]
    assert ops_graph.status_code == 200
    assert all(node["label"] != "Symbol LensGraph" for node in ops_graph.json()["nodes"])


def test_observability_ready_and_metrics_require_expected_roles() -> None:
    client = make_client()

    ready = client.get("/observability/ready", headers=READER_HEADERS)
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"

    denied = client.get("/observability/metrics", headers=READER_HEADERS)
    assert denied.status_code == 403

    metrics = client.get("/observability/metrics", headers=ADMIN_HEADERS)
    assert metrics.status_code == 200
    assert metrics.json()["total_requests"] >= 2
    assert "path_counts" in metrics.json()


def test_backup_and_restore_preserve_reviewed_graph_state() -> None:
    client = make_client()
    source = client.post("/sources", json={"kind": "text", "title": "Backup candidate"}).json()
    proposal = client.post(
        "/proposals",
        json={
            "source_id": source["id"],
            "kind": "content_node",
            "proposed_value": {"label": "Recoverable concept", "kind": "concept"},
        },
    ).json()
    client.post("/review-decisions", json={"proposal_id": proposal["id"], "decision": "accept"})

    backup = client.get("/backup", headers=ADMIN_HEADERS)
    assert backup.status_code == 200
    assert backup.json()["metadata"]["node_count"] == 1

    client.post("/sources", json={"kind": "text", "title": "Transient source"})
    assert len(client.get("/sources").json()["sources"]) == 2

    restored = client.post("/restore", headers=ADMIN_HEADERS, json=backup.json())
    assert restored.status_code == 200
    assert restored.json()["nodes"][0]["label"] == "Recoverable concept"
    assert [source["title"] for source in restored.json()["sources"]] == ["Backup candidate"]
    activity = client.get("/graph/activity", headers=READER_HEADERS).json()["events"]
    assert any(event["event_type"] == "proposal.created" for event in activity)
    assert "Transient source" not in str(activity)
