import json

import httpx
import pytest
from pydantic import ValidationError

from graphview_api.identity import IdentityService
from graphview_api.identity.service import OIDCVerifier
from graphview_api.secret_store import VaultSecretStore
from graphview_api.settings import Settings


def test_production_settings_fail_closed_without_oidc_postgres_and_strong_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_oidc_groups_map_to_least_privileged_graphview_roles() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://graphview:test@postgres/graphview",
        secret_key="a-strong-production-secret-that-is-long-enough",
        oidc_issuer_url="https://identity.example.test/realms/graphview",
        oidc_client_id="graphview",
        secret_provider="vault",
        vault_address="https://vault.example.test",
        vault_token="test-token",
        object_store_provider="s3",
        s3_endpoint_url="https://objects.example.test",
        s3_access_key_id="test-access-key",
        s3_secret_access_key="test-secret-key",
        malware_scan_url="https://scanner.example.test/scan",
        outbound_allowed_hosts="api.example.test",
    )
    identity = IdentityService(settings)

    reader = identity.user_from_claims(
        {"sub": "reader-1", "email": "reader@example.test", "groups": ["graphview-readers"]}
    )
    reviewer = identity.user_from_claims(
        {"sub": "reviewer-1", "groups": ["graphview-reviewers"]}
    )
    admin = identity.user_from_claims(
        {"sub": "admin-1", "groups": ["graphview-admins", "graphview-readers"]}
    )
    service = identity.user_from_claims({"sub": "service-1", "groups": ["graphview-services"]})

    assert reader.role == "reader"
    assert reader.project_ids == ("project-default",)
    assert reviewer.role == "reviewer"
    assert admin.role == "admin"
    assert service.role == "service"
    assert service.project_ids == ("*",)
    scoped_reader = identity.user_from_claims(
        {"sub": "scoped", "groups": ["graphview-readers", "graphview-project:project-research"]}
    )
    assert scoped_reader.project_ids == ("project-research",)
    with pytest.raises(PermissionError):
        identity.user_from_claims({"sub": "unmapped", "groups": ["another-group"]})


def test_oidc_backchannel_rewrites_only_the_configured_public_issuer() -> None:
    settings = Settings(
        oidc_issuer_url="https://graphview.example/identity/realms/graphview",
        oidc_backchannel_url="http://keycloak:8080/identity/realms/graphview",
    )
    verifier = OIDCVerifier(settings)

    assert verifier.backchannel(
        "https://graphview.example/identity/realms/graphview/protocol/openid-connect/token"
    ) == "http://keycloak:8080/identity/realms/graphview/protocol/openid-connect/token"
    assert verifier.backchannel("https://unrelated.example/jwks") == "https://unrelated.example/jwks"


def test_vault_store_returns_opaque_reference_and_reads_kv_v2_value() -> None:
    written: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            written.update(json.loads(request.content)["data"])
            return httpx.Response(200, json={"data": {}})
        return httpx.Response(200, json={"data": {"data": written}})

    settings = Settings(vault_address="https://vault.example.test", vault_token="test-token")
    client = httpx.Client(base_url=settings.vault_address, transport=httpx.MockTransport(handler))
    store = VaultSecretStore(settings, client=client)

    reference = store.put({"access_token": "access-token-value"})

    assert reference.startswith("gvsecret:vault:v1:")
    assert "access-token-value" not in reference
    assert store.get(reference) == {"access_token": "access-token-value"}
