---
type: security
owner: codex
---

# Complete Vault credential lifecycle

- Add validated stable-reference replacement and permanent deletion to Vault KV v2 and the development-only local
  AEAD store.
- Rotate connector and provider credentials in place, expose redacted connector credential rotation/removal routes,
  and purge external values when credentials are removed.
- Migrate legacy database AES-GCM and reversible credential envelopes into the configured external secret store during
  startup instead of retaining production credentials in database ciphertext.
- Move graph/provider secret settings into the bounded secret repository module and lower the enforced monolith
  ceiling.
- Add an exact-image OIDC/Vault gate for versioned rotation, redaction, legacy migration, database neutralization, and
  permanent metadata/version purge.
