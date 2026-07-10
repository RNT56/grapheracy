---
type: changed
owner: codex
---

# Current Notion continuous sync

- Move the default Notion connector contract to API version `2026-03-11`, discover database data sources, page current
  query endpoints, persist last-edited cursors, import incremental edits, and tombstone trashed pages.
- Rotate OAuth access and refresh tokens through the external connector secret reference.
- Add explicitly armed webhook verification, raw-body HMAC validation, workspace/integration checks, redacted durable
  event payloads, and event-ID replay protection.
- Lock a Python 3.14-compatible Ruff and include Python linting in the stable repository quality gate.
