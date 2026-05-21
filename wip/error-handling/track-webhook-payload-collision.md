# Webhook payload reserved-key collision

Follow-up surfaced during the Stage 3 (Item D-2) /review pass. Not a blocker for the error-handling refactor — the behavior is consistent with how the webhook payload already handled `pipeline_run_id` / `status` / `result_url` — but the surface should be tightened before more callers depend on the schema.

## What

`pipelex/pipe_run/delivery_executor.py:240-260` (`DeliveryExecutor._notify_webhook`) copies `WebhookTarget.payload` (arbitrary caller dict) and then unconditionally assigns four Pipelex-owned keys on top:

```python
payload: dict[str, Any] = dict(webhook.payload)
payload["pipeline_run_id"] = pipeline_run_id
payload["status"] = status
if result_url is not None:
    payload["result_url"] = result_url
if error_report is not None:
    payload["error"] = error_report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)
```

`WebhookTarget` (at `pipelex/pipe_run/delivery_assignment.py`) declares `payload: dict[str, Any] = Field(default_factory=dict)` — no schema, no key validation. A caller is free to put `{"error": "static fallback"}` in their static payload; on success that key passes through unchanged, on failure it gets silently replaced by the `ErrorReport` dict. The webhook schema therefore varies with delivery status in a way the caller did not opt into.

The same is true for `result_url` (replaced on success only) and for `pipeline_run_id` / `status` (always replaced). `error` is just the most recent addition to the reserved set.

## Why this is a follow-up, not a Stage 3 fix

- Item D-2 plan explicitly specified `payload["error"] = error_report.to_dict(VERBOSE)` and the test pins it (`tests/unit/pipelex/pipe_run/test_delivery_executor.py::test_webhook_includes_error_report_on_failed_status`).
- The asymmetry is consistent with `result_url`'s pre-existing behavior, so this is not a regression introduced by the error-handling refactor — it just makes the four-key reserved set more visible.
- Fixing it in the same PR risks scope creep into webhook validation, which deserves its own review (see "Cross-track interactions" below).

## Options

### Option 1 — Pydantic validator on `WebhookTarget.payload` (preferred)

Add a `field_validator` to `WebhookTarget.payload` that rejects the reserved set at construction time:

```python
# pipelex/pipe_run/delivery_assignment.py
_RESERVED_WEBHOOK_PAYLOAD_KEYS: frozenset[str] = frozenset({
    "pipeline_run_id", "status", "result_url", "error",
})

class WebhookTarget(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload", mode="after")
    @classmethod
    def _reject_reserved_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        collisions = set(value) & _RESERVED_WEBHOOK_PAYLOAD_KEYS
        if collisions:
            msg = (
                f"WebhookTarget.payload contains reserved keys: {sorted(collisions)}. "
                "Pipelex owns these keys (assigned per delivery); choose different names."
            )
            raise ValueError(msg)
        return value
```

**Pros**

- Fails at construction (`DeliveryAssignment` validation) rather than silently at delivery time.
- Discovered the moment the caller writes the misconfiguration, not the first time a delivery happens to fail.
- Zero schema change for well-behaved callers.

**Cons**

- Breaking change for any caller currently relying on a reserved key surviving — needs a CHANGELOG note.

### Option 2 — Namespace Pipelex-owned fields

Move the four reserved keys under a `pipelex` sub-dict:

```python
payload: dict[str, Any] = dict(webhook.payload)
pipelex_meta: dict[str, Any] = {
    "pipeline_run_id": pipeline_run_id,
    "status": status,
}
if result_url is not None:
    pipelex_meta["result_url"] = result_url
if error_report is not None:
    pipelex_meta["error"] = error_report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)
payload["pipelex"] = pipelex_meta
```

**Pros**

- Cleanest separation between caller schema and Pipelex schema.
- Only one reserved top-level key (`pipelex`), easy for the validator (Option 1) to enforce.

**Cons**

- Breaks every existing webhook receiver. Every consumer of `body["status"]` becomes `body["pipelex"]["status"]`. Coordinated change across pipelex-api, the webapp, n8n node, customer integrations.
- Loses RFC 7807 affinity — when `error` is present, today it can be a near-drop-in for `application/problem+json` content with the right `Content-Type`. Burying it under `pipelex.error` makes that retargeting noisier.

## Recommendation

Land Option 1 in its own PR after this error-handling refactor merges. Skip Option 2 — the namespace shift cost is high and the RFC 7807 affinity is worth preserving.

Sequencing:

1. This PR (`feature/API-readiness`) merges with current behavior.
2. New PR adds the `WebhookTarget.payload` validator + reserved-key constant + CHANGELOG entry. Same PR updates `pipelex-api`'s docs to call out the reserved set (the API repo is the primary consumer of this surface).
3. Update `wip/error-handling/api-companion-revisions.md` D-2 section to point at this doc.

## Cross-track interactions

- **Webhook signing** (`wip/security/webhook-signing.md`) modifies the same `_notify_webhook` body. If signing lands first, the validator PR should rebase onto it. If validator lands first, the signing track inherits a well-defined payload shape — strictly easier to sign over.
- **Deferred `causes` cause-chain serialization** (TODOS.md "Deferred follow-ups") adds richness to `error_report.to_dict(VERBOSE)` but doesn't touch the reserved-key set. Independent.

## Trigger to pick this up

Any of:

- A new caller reports surprise that their static `error` key vanished on failed runs.
- pipelex-api or the webapp wants to add a new payload field and needs a clear contract for what's already reserved.
- The webhook-signing track lands and we want a clean payload shape under the signature.
