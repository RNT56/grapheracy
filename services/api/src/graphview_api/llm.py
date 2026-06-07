from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from graphview_api.ingestion import GeneratedProposal
from graphview_api.schemas import CONTENT_NODE_KINDS, SEMANTIC_RELATIONS
from graphview_api.settings import Settings

ALLOWED_NODE_KINDS = ", ".join(CONTENT_NODE_KINDS)
ALLOWED_RELATIONS = ", ".join(SEMANTIC_RELATIONS)


class LlmExtractionProvider(Protocol):
    async def extract(self, *, title: str, text: str, locator: str) -> list[GeneratedProposal]:
        ...


@dataclass(frozen=True)
class ProviderModelDescriptor:
    id: str
    label: str
    default: bool
    capabilities: list[str]
    context_window: int | None = None


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    label: str
    enabled: bool
    configured: bool
    default_model: str
    capabilities: list[str]
    models: list[ProviderModelDescriptor]


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    structured: dict[str, Any]
    model: str
    provider: str
    confidence: float = 0.72


class AiProvider(Protocol):
    provider_id: str
    model: str

    async def complete(self, *, system: str, user: str, response_format: str = "text") -> ProviderResponse:
        ...


class GraphviewLocalProvider:
    provider_id = "graphview-local"

    def __init__(self, model: str = "graphview-local-deterministic-v1"):
        self.model = model

    async def complete(self, *, system: str, user: str, response_format: str = "text") -> ProviderResponse:
        parsed = _safe_json(user)
        question = str(parsed.get("question") or parsed.get("message") or parsed.get("query") or parsed.get("goal") or user)
        citations = parsed.get("citations") if isinstance(parsed.get("citations"), list) else []
        build_spec = _local_build_spec(parsed, question)
        if response_format == "graph_build_spec":
            return ProviderResponse(
                text=f"Drafted a graph build plan for {build_spec['title']}.",
                structured=build_spec,
                model=self.model,
                provider=self.provider_id,
                confidence=0.76,
            )
        if response_format == "graph_query":
            answer = _local_graph_answer(question, citations)
            return ProviderResponse(
                text=answer["answer"],
                structured=answer,
                model=self.model,
                provider=self.provider_id,
                confidence=answer["confidence"],
            )
        if response_format == "research":
            title = f"AI research note: {question[:96]}"
            return ProviderResponse(
                text=f"Created a scoped research note for: {question}",
                structured={
                    "title": title,
                    "content": (
                        f"# {title}\n\n"
                        f"Research question: {question}\n\n"
                        "This deterministic local pass records the question, links it to the active graph context, "
                        "and creates reviewable proposals without committing graph nodes directly."
                    ),
                    "confidence": 0.68,
                },
                model=self.model,
                provider=self.provider_id,
                confidence=0.68,
            )
        return ProviderResponse(
            text=(
                "I mapped the request into Graphview's reviewed graph workflow. "
                "Next, approve the build spec or launch scoped research to create sources and proposals."
            ),
            structured={"message": question, "next_actions": ["approve_build_spec", "launch_research", "ask_graph"]},
            model=self.model,
            provider=self.provider_id,
            confidence=0.7,
        )


class OpenAIResponsesProvider:
    provider_id = "openai"

    def __init__(self, *, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def complete(self, *, system: str, user: str, response_format: str = "text") -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "reasoning": {"effort": "medium"},
            "text": {"verbosity": "low"},
        }
        if response_format != "text":
            payload["text"]["format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        text = _openai_response_text(body)
        return ProviderResponse(
            text=text,
            structured=_safe_json(text),
            model=self.model,
            provider=self.provider_id,
            confidence=0.78,
        )


class AnthropicMessagesProvider:
    provider_id = "anthropic"

    def __init__(self, *, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def complete(self, *, system: str, user: str, response_format: str = "text") -> ProviderResponse:
        prompt = user
        if response_format != "text":
            prompt = f"{user}\n\nReturn JSON only."
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "name": "graphview_context",
                    "description": "Read-only Graphview retrieval context already supplied by the API.",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        }
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        text = "".join(item.get("text", "") for item in body.get("content", []) if item.get("type") == "text")
        return ProviderResponse(
            text=text,
            structured=_safe_json(text),
            model=self.model,
            provider=self.provider_id,
            confidence=0.78,
        )


class GeminiGenerateProvider:
    provider_id = "gemini"

    def __init__(self, *, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def complete(self, *, system: str, user: str, response_format: str = "text") -> ProviderResponse:
        json_instruction = "\n\nReturn JSON only." if response_format != "text" else ""
        contents = [
            {
                "role": "user",
                "parts": [{"text": f"{system}\n\n{user}{json_instruction}"}],
            }
        ]
        payload: dict[str, Any] = {
            "contents": contents,
            "tools": [{"googleSearch": {}}, {"urlContext": {}}],
            "generationConfig": {"temperature": 0.1},
        }
        if response_format != "text":
            payload["generationConfig"]["responseMimeType"] = "application/json"
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/v1alpha/models/{self.model}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        text = _gemini_response_text(body)
        return ProviderResponse(
            text=text,
            structured=_safe_json(text),
            model=self.model,
            provider=self.provider_id,
            confidence=0.78,
        )


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings

    def descriptors(self) -> list[dict[str, Any]]:
        descriptors = [
            ProviderDescriptor(
                id="graphview-local",
                label="Graphview Local",
                enabled=True,
                configured=True,
                default_model="graphview-local-deterministic-v1",
                capabilities=["planning", "graph_query", "research", "structured_output"],
                models=[
                    ProviderModelDescriptor(
                        id="graphview-local-deterministic-v1",
                        label="Local deterministic",
                        default=True,
                        capabilities=["planning", "graph_query", "research", "structured_output"],
                    )
                ],
            ),
            ProviderDescriptor(
                id="openai",
                label="OpenAI",
                enabled=bool(self.settings.openai_api_key),
                configured=bool(self.settings.openai_api_key),
                default_model=self.settings.openai_model,
                capabilities=["planning", "graph_query", "research", "structured_output", "tool_calling"],
                models=_provider_models(
                    self.settings.openai_model,
                    [
                        ("gpt-5.5", "gpt-5.5", ["reasoning", "tool_calling", "structured_output"]),
                        ("gpt-5.4-mini", "gpt-5.4-mini", ["fast_reasoning", "tool_calling", "structured_output"]),
                    ],
                ),
            ),
            ProviderDescriptor(
                id="anthropic",
                label="Anthropic",
                enabled=bool(self.settings.anthropic_api_key),
                configured=bool(self.settings.anthropic_api_key),
                default_model=self.settings.anthropic_model,
                capabilities=["planning", "graph_query", "research", "tool_calling"],
                models=_provider_models(
                    self.settings.anthropic_model,
                    [
                        ("claude-opus-4.8", "claude-opus-4.8", ["reasoning", "tool_calling", "long_context"]),
                        ("claude-sonnet-4.6", "claude-sonnet-4.6", ["fast_reasoning", "tool_calling", "long_context"]),
                    ],
                ),
            ),
            ProviderDescriptor(
                id="gemini",
                label="Gemini",
                enabled=bool(self.settings.gemini_api_key),
                configured=bool(self.settings.gemini_api_key),
                default_model=self.settings.gemini_model,
                capabilities=["planning", "graph_query", "research", "structured_output", "search_grounding", "url_context"],
                models=_provider_models(
                    self.settings.gemini_model,
                    [
                        ("gemini-3.1-pro", "gemini-3.1-pro", ["reasoning", "function_calling", "search_grounding", "url_context"]),
                        ("gemini-3.5-flash", "gemini-3.5-flash", ["fast_reasoning", "function_calling", "search_grounding", "url_context"]),
                    ],
                ),
            ),
        ]
        return [_descriptor_to_dict(descriptor) for descriptor in descriptors]

    def resolve(self, provider: str | None = None, model: str | None = None) -> AiProvider:
        provider_id = provider or self.settings.ai_default_provider
        if provider_id == "graphview-local":
            return GraphviewLocalProvider(model or "graphview-local-deterministic-v1")
        if provider_id == "openai" and self.settings.openai_api_key:
            return OpenAIResponsesProvider(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=model or self.settings.openai_model,
            )
        if provider_id == "anthropic" and self.settings.anthropic_api_key:
            return AnthropicMessagesProvider(
                api_key=self.settings.anthropic_api_key,
                base_url=self.settings.anthropic_base_url,
                model=model or self.settings.anthropic_model,
            )
        if provider_id == "gemini" and self.settings.gemini_api_key:
            return GeminiGenerateProvider(
                api_key=self.settings.gemini_api_key,
                base_url=self.settings.gemini_base_url,
                model=model or self.settings.gemini_model,
            )
        raise ValueError(f"Provider {provider_id} is not configured")


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(settings)


@dataclass(frozen=True)
class OpenAICompatibleExtractionProvider:
    base_url: str
    api_key: str
    model: str

    async def extract(self, *, title: str, text: str, locator: str) -> list[GeneratedProposal]:
        prompt = (
            "Extract a small reviewed-knowledge-graph proposal list from the source. "
            "Return strict JSON with a top-level proposals array. Each item must have "
            "kind content_node or semantic_edge, confidence 0..1, locator, and proposed_value. "
            f"Allowed node kinds: {ALLOWED_NODE_KINDS}. "
            f"Allowed relations: {ALLOWED_RELATIONS}."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps({"title": title, "locator": locator, "text": text[:12000]}),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        proposals: list[GeneratedProposal] = []
        for item in parsed.get("proposals", []):
            if item.get("kind") not in {"content_node", "semantic_edge"}:
                continue
            value = item.get("proposed_value")
            if not isinstance(value, dict):
                continue
            proposals.append(
                GeneratedProposal(
                    kind=item["kind"],
                    proposed_value={**value, "metadata": {**value.get("metadata", {}), "extractedByModel": self.model}},
                    confidence=float(item.get("confidence", 0.5)),
                    locator=str(item.get("locator") or locator),
                )
            )
        return proposals


class DisabledLlmExtractionProvider:
    async def extract(self, *, title: str, text: str, locator: str) -> list[GeneratedProposal]:
        return []


def build_llm_provider(
    *,
    enabled: bool,
    provider: str | None,
    base_url: str,
    api_key: str | None,
    model: str | None,
) -> LlmExtractionProvider:
    if not enabled or not api_key:
        return DisabledLlmExtractionProvider()
    if provider not in {None, "openai-compatible", "openai"}:
        return DisabledLlmExtractionProvider()
    return OpenAICompatibleExtractionProvider(base_url=base_url, api_key=api_key, model=model or "gpt-4.1-mini")


def _descriptor_to_dict(descriptor: ProviderDescriptor) -> dict[str, Any]:
    return {
        "id": descriptor.id,
        "label": descriptor.label,
        "enabled": descriptor.enabled,
        "configured": descriptor.configured,
        "default_model": descriptor.default_model,
        "capabilities": descriptor.capabilities,
        "models": [
            {
                "id": model.id,
                "label": model.label,
                "default": model.default,
                "capabilities": model.capabilities,
                "context_window": model.context_window,
            }
            for model in descriptor.models
        ],
    }


def _provider_models(default_model: str, catalog: list[tuple[str, str, list[str]]]) -> list[ProviderModelDescriptor]:
    model_ids = [default_model, *[model_id for model_id, _, _ in catalog if model_id != default_model]]
    descriptors = []
    for model_id in model_ids:
        catalog_item = next((item for item in catalog if item[0] == model_id), None)
        label = catalog_item[1] if catalog_item else model_id
        capabilities = catalog_item[2] if catalog_item else ["reasoning"]
        descriptors.append(
            ProviderModelDescriptor(
                id=model_id,
                label=label,
                default=model_id == default_model,
                capabilities=capabilities,
            )
        )
    return descriptors


def _safe_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _local_build_spec(parsed: dict[str, Any], question: str) -> dict[str, Any]:
    goal = str(parsed.get("goal") or question or "New research graph").strip()
    title = str(parsed.get("title") or goal[:80] or "AI planning session")
    seed = goal.rstrip(".")
    return {
        "title": title,
        "objective": goal,
        "topics": [
            {"name": seed, "priority": "primary"},
            {"name": "Open questions", "priority": "review"},
            {"name": "Evidence and sources", "priority": "review"},
        ],
        "seed_sources": [],
        "open_questions": [
            f"What source material best grounds {seed}?",
            "Which claims need direct provenance before graph acceptance?",
        ],
        "research_tasks": [
            {"query": seed, "source_policy": "mixed", "priority": "high"},
        ],
        "node_kinds": ["concept", "document", "source", "decision", "risk"],
        "edge_relations": ["supports", "contradicts", "depends_on", "references", "relates_to"],
        "review_policy": "review-first",
    }


def _local_graph_answer(question: str, citations: list[Any]) -> dict[str, Any]:
    source_count = len(citations)
    if source_count:
        labels = [
            str(item.get("label") or item.get("source_title") or item.get("node_id") or "source")
            for item in citations
            if isinstance(item, dict)
        ][:3]
        answer = (
            f"Based on {source_count} graph citations, the strongest available context for '{question}' is "
            f"{', '.join(labels)}. Review the cited sources before committing follow-up graph changes."
        )
    else:
        answer = (
            f"I could not find strong stored graph evidence for '{question}'. "
            "Launch scoped research to add sources and reviewable proposals."
        )
    return {"answer": answer, "confidence": 0.72 if source_count else 0.38}


def _openai_response_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _gemini_response_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in body.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)
