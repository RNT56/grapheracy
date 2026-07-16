import asyncio

import pytest

from graphview_api.llm import build_provider_registry
from graphview_api.settings import Settings


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if "/responses" in url:
            return FakeResponse({"output_text": '{"answer":"openai ok","confidence":0.8}'})
        if "/v1/messages" in url:
            return FakeResponse({"content": [{"type": "text", "text": '{"answer":"anthropic ok","confidence":0.8}'}]})
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": '{"answer":"gemini ok","confidence":0.8}'}]}}]})


def test_provider_registry_reports_configured_status_without_keys() -> None:
    registry = build_provider_registry(Settings(database_url="sqlite://"))

    providers = registry.descriptors()

    assert next(provider for provider in providers if provider["id"] == "graphview-local")["enabled"] is True
    openai = next(provider for provider in providers if provider["id"] == "openai")
    anthropic = next(provider for provider in providers if provider["id"] == "anthropic")
    gemini = next(provider for provider in providers if provider["id"] == "gemini")
    assert openai["enabled"] is False
    assert anthropic["configured"] is False
    assert gemini["configured"] is False
    assert openai["default_model"] == "gpt-5.5"
    assert [model["id"] for model in openai["models"]] == ["gpt-5.5", "gpt-5.4-mini"]
    assert anthropic["default_model"] == "claude-opus-4.8"
    assert [model["id"] for model in anthropic["models"]] == ["claude-opus-4.8", "claude-sonnet-4.6"]
    assert gemini["default_model"] == "gemini-3.1-pro"
    assert [model["id"] for model in gemini["models"]] == ["gemini-3.1-pro", "gemini-3.5-flash"]


def test_provider_catalog_keeps_one_default_for_configured_alternate_model() -> None:
    registry = build_provider_registry(
        Settings(
            database_url="sqlite://",
            openai_model="gpt-5.4-mini",
            anthropic_model="claude-sonnet-4.6",
            gemini_model="gemini-3.5-flash",
        )
    )

    for provider_id in ["openai", "anthropic", "gemini"]:
        provider = next(item for item in registry.descriptors() if item["id"] == provider_id)
        model_ids = [model["id"] for model in provider["models"]]
        defaults = [model["id"] for model in provider["models"] if model["default"]]
        assert len(model_ids) == len(set(model_ids))
        assert defaults == [provider["default_model"]]


def test_unconfigured_external_provider_is_not_silently_replaced() -> None:
    registry = build_provider_registry(Settings(database_url="sqlite://"))

    with pytest.raises(ValueError):
        registry.resolve("openai")


def test_openai_anthropic_and_gemini_adapters_build_expected_requests(monkeypatch) -> None:
    from graphview_api import llm

    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)
    settings = Settings(
        database_url="sqlite://",
        openai_api_key="openai-key",
        anthropic_api_key="anthropic-key",
        gemini_api_key="gemini-key",
    )
    registry = build_provider_registry(settings)

    for provider_id in ["openai", "anthropic", "gemini"]:
        provider = registry.resolve(provider_id)
        response = asyncio.run(provider.complete(system="System", user='{"question":"Q"}', response_format="graph_query"))
        assert response.structured["answer"]

    urls = [call["url"] for call in FakeAsyncClient.calls]
    assert any(url.endswith("/responses") for url in urls)
    assert any(url.endswith("/v1/messages") for url in urls)
    assert any(":generateContent" in url for url in urls)
    assert FakeAsyncClient.calls[0]["json"]["model"] == settings.openai_model
    assert FakeAsyncClient.calls[1]["headers"]["x-api-key"] == "anthropic-key"
    assert FakeAsyncClient.calls[2]["params"]["key"] == "gemini-key"
