from fastapi.testclient import TestClient

from graphview_api.main import create_app


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "graphview-api"}


def test_version() -> None:
    client = TestClient(create_app())

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.2.0"


def test_local_auth_rejects_unknown_user() -> None:
    client = TestClient(create_app())

    response = client.get("/graph", headers={"X-Graphview-User": "unknown"})

    assert response.status_code == 401
