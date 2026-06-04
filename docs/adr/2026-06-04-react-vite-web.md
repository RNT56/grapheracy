# ADR: React And Vite Web App

Date: 2026-06-04

## Status

Accepted for Phase 1 direction.

## Context

The product needs an interactive graph UI with review workflows and a future docs app path.

## Decision

Use React 19.2, TypeScript, Vite 8, React Router, TanStack Query, Zustand, and CSS Modules unless design tokens justify
Tailwind later.

## Consequences

- Keep rendering logic behind a typed graph abstraction.
- Avoid committing to a heavy graph renderer before Phase 2 evaluation.
- Dependency additions must follow the security checklist.
