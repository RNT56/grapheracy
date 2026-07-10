import asyncio
import socket

import pytest

from graphview_api.ingestion import validate_outbound_url


def test_url_validation_blocks_private_networks_credentials_and_disallowed_hosts(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(ValueError, match="prohibited"):
        asyncio.run(validate_outbound_url("http://internal.example.test/admin"))
    with pytest.raises(ValueError, match="embedded credentials"):
        asyncio.run(validate_outbound_url("https://user:password@example.test/data"))
    with pytest.raises(ValueError, match="allowlist"):
        asyncio.run(validate_outbound_url("https://untrusted.example.test", {"trusted.example.test"}))


def test_url_validation_accepts_allowlisted_public_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    uri = "https://docs.example.test/guide"
    assert asyncio.run(validate_outbound_url(uri, {"example.test"})) == uri
