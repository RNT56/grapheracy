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
    assert response.json()["version"] == "0.3.0"


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
