from graphview_api.repository import load_json
from graphview_api.repository_secrets import _load_json as load_secret_json
from graphview_api.repository_serialization import _load_json as load_projection_json


def test_json_loaders_accept_postgresql_jsonb_values_and_legacy_text() -> None:
    for loader in (load_json, load_secret_json, load_projection_json):
        parsed = {"items": ["one", "two"]}
        assert loader(parsed, {}) is parsed
        assert loader('{"items":["one","two"]}', {}) == parsed
        assert loader(None, {"fallback": True}) == {"fallback": True}
