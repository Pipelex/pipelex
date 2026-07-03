# BYOK — deferred review findings (design tradeoffs, not defects)

Captured from the Checkpoint 2 code review of `infra-python-tools@feature/inference-profiles` (see `TODOS.md`). These are deliberate deferrals — each needs a real decision, not a reflexive fix.

## 1. CMK replacement semantics after `KeyId` pinning

`KmsEnvelopeAdapter.decrypt_credentials` now pins `KeyId=self.kms_key_arn` (confused-deputy hardening, applied at Checkpoint 2). Consequence: envelope blobs written under a retired CMK stop decrypting after a key replacement. Before any CMK rotation/replacement runbook exists, pair the pin with a re-encrypt migration story (read with old ARN, re-encrypt under new, bump nothing — re-encryption is deliberately NOT a credentials_version bump / fingerprint change). Owner: Phase 2d infra work (CMK lifecycle policy).

## 2. Plaintext credentials echoed by pydantic validation errors

`InferenceProfileSaveBody.credentials` is a plain `dict[str, str]`; a mistyped value (e.g. a non-string) is echoed verbatim in the `ValidationError` `input_value`, which a FastAPI 422 body or request log would carry. Consistent with the repo's existing convention (`api_key.py` `plaintext_key` is equally bare), but the blast radius is a whole multi-provider key map. Options when the platform router lands (Phase 1c): `SecretStr` values (changes the encrypt call to `.get_secret_value()`), a custom validator that raises without echoing, or router-level 422 sanitization for this route. Decide at Phase 1c review; the log scrubber's whole-object `credentials` redaction (applied at Checkpoint 2) already covers the logging half.

## 3. Decimal round-trip normalization for the worker-boot materializer

DynamoDB rehydrates overlay numbers as `Decimal` (e.g. `{"timeout": 30}` → `Decimal('30')`, rendered `"30"` by `model_dump(mode="json")`). Fingerprints are already canonicalized against this; the Phase 2c worker-boot materializer must apply the same normalization when rendering the overlay dicts into TOML, or provider configs get string-typed numbers. One implementation should be shared (`_canonicalize_for_fingerprint` is the shape to lift if needed).

## 4. Overlay secret-shape guard is best-effort (Checkpoint 3, F3 residual)

`InferenceProfileSaveBody` now rejects prefix-shaped secret literals (`sk-…` etc.) in the plaintext overlay fields, but shapes with no recognizable prefix (bare hex Azure keys, GCP service-account JSON fields) still pass and would be member-readable via the member-open GET routes. Options if this needs closing: make profile reads admin-only (UX cost for the Phase 3 webapp), or a stronger allowlist ("credential-slot fields in `backends` MUST be `${VAR}` placeholders" — validate slot keys like `api_key` specifically). Decide with the Phase 3 product surface.

## 5. Disable-vs-bind race on the org default (Checkpoint 3, F1 note)

The default-binding invariant (always points at an enabled profile) is enforced on bind (409 disabled target), delete (atomic conditional clear), and update-disable (409 when currently bound). A concurrent disable+bind interleaving can still theoretically cross (no cross-item transaction); consequence is bounded — resolution fails closed, never falls back to server keys. Not worth a transaction until real traffic says otherwise.

## 6. `list_profiles` pagination

`list_profiles` is single-page (byte-identical to `list_methods`) — silently truncates past one 1MB query page. Not plausible at expected profile counts per org; revisit only if profiles grow large payloads (deck overlays with many custom model specs could).
