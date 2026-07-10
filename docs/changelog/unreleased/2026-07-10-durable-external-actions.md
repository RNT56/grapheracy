---
type: changed
owner: codex
---

# Crash-visible external actions

- Persist external action runs before side effects, reuse the same run across worker retries and expired leases, and
  record queued, resumed, succeeded, failed, or cancelled transitions with redacted audit events and external receipts.
- Mint GitHub App installation tokens for issue actions, scan paginated issues for stable idempotency markers, render
  inert SMTP templates with suppression and TLS, and keep workflow webhooks allowlisted and HMAC-signed.
- Redact sensitive provider errors before durable job, connector health, action-run, or OpenTelemetry storage.
- Add fresh, HMAC-verified workflow outcome callbacks that enqueue replay-safe durable outcome jobs, plus an atomic
  mode-0600 local AES-GCM secret-reference store so development exercises the same credential boundary as Vault.
- Wire safe actions, signed-webhook destinations, SMTP settings, and SMTP network-policy egress through the production
  Compose and Helm reference deployments.
