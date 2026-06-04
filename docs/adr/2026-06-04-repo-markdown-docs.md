# ADR: Repo Markdown Documentation

Date: 2026-06-04

## Status

Accepted for Phase 1 direction.

## Context

The project needs documentation immediately, but building and operating a docs site in Phase 1 would add unnecessary
surface area.

## Decision

Use repo markdown as the Phase 1 documentation source of truth. A later docs app may consume the same markdown.

## Consequences

- Docs must remain link-checkable and readable in GitHub.
- Generated docs artifacts should not be committed without review.
- The docs app must not fork content away from `docs/`.
