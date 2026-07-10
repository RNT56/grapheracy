---
type: security
owner: codex
---

# Signed release artifact chain

- Package the MCP gateway as a constrained TGZ and the editor adapter as an installable, deterministic VSIX without
  accepting the provenance downgrade blocked by the workspace trust policy.
- Emit and verify a client-artifact SPDX 2.3 SBOM, commit-bound manifest, exact sizes, and SHA-256 checksums in pull
  requests and the full release gate.
- Record all eight release image digests, retain BuildKit SBOM/provenance and Cosign image signatures, verify GitHub's
  annotated-tag signature result, attest client artifacts, and publish a keyless Sigstore bundle over the complete
  checksum manifest.
- Raise the locked Python security floors to `pydantic-settings` 2.14.2, `pypdf` 6.13.3 or newer, and Starlette 1.3.1
  after the release gate detected newly disclosed advisories in the previous lock set.
- Redact Gitleaks console findings and exclude only local encrypted `.gvenc` ciphertext from entropy-based scanning;
  source, metadata, manifests, and every other runtime file remain covered.
