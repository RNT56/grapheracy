from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("GRAPHVIEW_DATABASE_URL", "sqlite://")

from graphview_api.main import create_app
from graphview_api.settings import Settings


root = Path(__file__).resolve().parents[1]
expected = json.dumps(create_app(Settings(database_url="sqlite://")).openapi(), indent=2) + "\n"
actual = (root / "services/api/openapi.yaml").read_text(encoding="utf-8")
if actual != expected:
    raise SystemExit("OpenAPI drift detected. Run pnpm api:generate.")
print("OpenAPI contract is current.")
