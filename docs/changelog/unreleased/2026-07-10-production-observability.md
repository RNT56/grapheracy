---
type: changed
owner: codex
---

# Production OpenTelemetry proof

- Export route-bounded API request metrics, SSE lifecycle metrics, worker queue/job/outbox metrics, SQL spans, sanitized
  outbound HTTP spans, and durable job spans through the vendor-neutral OTLP boundary.
- Persist W3C trace context with durable jobs and transactional outbox events so API uploads and worker execution retain
  one distributed trace, and return that trace ID to clients.
- Redact server queries, outbound URL queries/fragments, sensitive headers, and provider exceptions before telemetry;
  keep project/job identifiers out of metric dimensions.
- Include the non-root Collector image in SBOM, vulnerability, provenance, and signing workflows; add bounded file
  evidence, Prometheus export, Compose/Helm health probes, and a live-stack gate that parses trace continuity, required
  metrics, URL hygiene, and injected-secret absence.
