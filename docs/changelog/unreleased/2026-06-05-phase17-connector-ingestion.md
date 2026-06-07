---
type: added
owner: codex
---

Implemented connector-backed graph building with durable connector accounts, targets, sync runs, source chunks, topic
hierarchy, source origin metadata, graph settings, and expanded semantic relation values. Manual sync and resync now
normalize upload, URL, repository, Google Workspace, and Notion content into source documents and chunks; deterministic
extraction proposes hierarchy and source-aware relations, optional provider-boundary LLM extraction writes the same
proposal shape, and confidence-threshold auto-commit records `system-autocommit` review decisions when proposals are
ready and non-conflicting.

The web workspace now includes connector setup, target sync controls, inherited LLM and auto-commit settings, sync
status, and source hierarchy context while preserving the existing review worklist for pending or blocked proposals.
