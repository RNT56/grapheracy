from fastapi.testclient import TestClient

from graphview_api.main import create_app
from graphview_api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(database_url="sqlite://")))


def test_health() -> None:
    client = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "graphview-api"}


def test_version() -> None:
    client = make_client()

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.4.0"


def test_local_auth_rejects_unknown_user() -> None:
    client = make_client()

    response = client.get("/graph", headers={"X-Graphview-User": "unknown"})

    assert response.status_code == 401


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

    deleted = client.delete(f"/sources/{source['id']}")
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


def test_export_and_import_sources() -> None:
    client = make_client()

    imported = client.post(
        "/import",
        json={"sources": [{"kind": "url", "title": "Graph paper", "uri": "https://example.invalid/paper"}]},
    )

    assert imported.status_code == 200
    bundle = client.get("/export")
    assert bundle.status_code == 200
    assert bundle.json()["sources"][0]["title"] == "Graph paper"


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

    proposal_id = body["proposals"][0]["id"]
    decision = client.post("/review-decisions", json={"proposal_id": proposal_id, "decision": "accept"})
    assert decision.status_code == 201
    exported = client.get("/export").json()
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
