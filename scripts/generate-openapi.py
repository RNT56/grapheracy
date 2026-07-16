from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("GRAPHVIEW_DATABASE_URL", "sqlite://")

from graphview_api.main import create_app
from graphview_api.settings import Settings


root = Path(__file__).resolve().parents[1]
document = create_app(Settings(database_url="sqlite://")).openapi()
(root / "services/api/openapi.yaml").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
