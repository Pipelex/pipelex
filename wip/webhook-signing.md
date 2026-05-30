# Webhook signing — security track

This plan covers webhook signing for the `pipelex → pipelex-api → external receiver` completion-callback flow. It is **independent of the error-handling refactor** ([`error-handling/`](error-handling/)) — the two were originally bundled in the same TODO list because the same cross-repo PR window was convenient, but they have no functional dependency on each other.

Splitting signing into its own track lets reviewers evaluate it on security merit (trust topology, threat model, tamper detection, rollout safety) rather than as a footnote to an error-handling PR.

---

## Background — what exists today

### Dispatcher-side signing in pipelex-api

`pipelex-api/api/routes/pipelex/pipeline.py:44-56` computes a signature **at dispatch time** when wiring up the webhook target. The signed bytes are **only the `pipeline_run_id`**, and the resulting hex is baked into the `WebhookTarget.headers` dict that rides through pipelex unchanged:

```python
def _completion_signature(pipeline_run_id: str) -> str:
    secret = get_required_env("COMPLETION_CALLBACK_SECRET")
    return hmac.new(secret.encode("utf-8"), pipeline_run_id.encode("utf-8"), hashlib.sha256).hexdigest()

# At dispatch:
WebhookTarget(
    url=url,
    headers={"X-Completion-Signature": _completion_signature(resolved_pipeline_run_id)},
)
```

### Pipelex itself

Pipelex has **zero signing code**. `pipelex/pipe_run/delivery_executor.py:_notify_webhook` POSTs the payload with whatever headers it was handed and never reads a secret. It is a generic forwarder.

### Threat model gap

A MitM who can rewrite the webhook body in transit can change `status="completed"` → `status="failed"`, mutate `result_url`, and — after the error-handling refactor's Item D-2 lands — rewrite the entire `error` classification payload (`error_type`, `retryable`, `provider`, `user_action`, etc.). The current header signature does nothing to detect this; the signed bytes are just `pipeline_run_id`, which is in the URL anyway.

---

## Trust topology — today vs. proposed

| | Today | Proposed |
|---|---|---|
| **Who signs** | pipelex-api dispatcher | pipelex worker |
| **What's signed** | `pipeline_run_id` only | Full serialized request body |
| **Where the secret lives** | One process (the dispatcher) | Every pipelex worker process |
| **Trust blast radius if compromised** | Dispatcher | Any worker |
| **Header format** | `X-Completion-Signature: <hex>` (bare hex) | `X-Completion-Signature: sha256=<hex>` (algorithm-prefixed) |

The proposed pattern matches Stripe / GitHub / standard webhook-signing best practice. The cost is broader secret distribution — every worker needs it. This is acceptable because workers already run in trusted infrastructure; their attack surface dominates the marginal risk of also holding this secret.

---

## Decisions locked in

- **Secret source: env var only, no config field.** The worker reads `PIPELEX_WEBHOOK_SIGNING_SECRET` from its environment. There is no `pipelex.toml` field for it. Rationale: pipelex's repo policy is "no secrets in any committed config file." Consistent with how provider API keys (`OPENAI_API_KEY`, etc.) are handled.
- **Same env-var name on both sides.** Worker and receiver both read `PIPELEX_WEBHOOK_SIGNING_SECRET`. The shared-secret nature is named explicitly. The old `COMPLETION_CALLBACK_SECRET` is renamed in pipelex-api's deployment manifests as part of the migration.
- **Algorithm: HMAC-SHA256.** Standard, fast, well-supported.
- **Header: `X-Completion-Signature: sha256=<hex>`.** Algorithm-prefixed format. The bare-hex format used today becomes incompatible — see rollout.
- **Verification: constant-time via `hmac.compare_digest`.** Prevents timing-side-channel leaks.
- **Failure mode: loud, not silent.** If a webhook is configured but the secret is missing, raise `PipelexConfigError` at delivery time. No unsigned send, ever.
- **Empty webhooks list does not require the secret.** Cost of running pipelex without webhooks should not increase.
- **Body bytes signed = body bytes sent.** Sign the exact `bytes` posted to httpx (`content=body_bytes`), not the dict (`json=payload`). `httpx`'s JSON serialization is otherwise free to add whitespace, breaking signature verification.

---

## Approach — 3-step rollout

The signature format changes from bare hex to `sha256=<hex>`, and from `pipeline_run_id`-signing to body-signing. A naive single-PR merge breaks any in-flight webhooks during the deploy window. The correct sequence is three deploys, each reversible on its own.

### Step 1 — Receiver supports both old and new formats

The pipelex-api receiver verifies webhooks **both ways**:

- If the `X-Completion-Signature` header starts with `sha256=`, take body bytes, recompute, compare.
- Otherwise (bare hex, no algorithm prefix), assume legacy format, recompute from `pipeline_run_id`, compare. Log a deprecation warning identifying the request.

Ship and deploy first. Existing pipelex workers (still signing the old way at dispatch time) keep working.

### Step 2 — Pipelex worker switches to body-signing

`pipelex/pipe_run/delivery_executor.py:_notify_webhook` computes HMAC-SHA256 over the request body bytes and sets `X-Completion-Signature: sha256=<hex>`. The dispatcher (`pipelex-api/api/routes/pipelex/pipeline.py`) **stops** populating the header at dispatch time — the worker is now the signer end-to-end.

Ship and deploy. Receivers verify via the new sha256-prefixed branch.

### Step 3 — Remove the legacy fallback

The pipelex-api receiver drops the bare-hex verification branch and the `_completion_signature` helper.

**Pre-condition:** Step 2 has been deployed across all pipelex workers, AND the deprecation log line from Step 1 has gone quiet for at least one full retention window (typically a week). The deprecation log is the safety net — if any legacy sender is still in production, the log surfaces it before the fallback is removed.

This rollout is the **single biggest difference** from the original Item F framing in the error-handling plan, which proposed lockstep merge of both repos. Lockstep merge breaks any in-flight webhook during the deploy window; the 3-step rollout does not.

---

## The work

### [ ] Item 1 — Receiver-side dual-format verification

- **Files:**
    - `pipelex-api/api/routes/pipelex/pipeline.py` — replace `_completion_signature(pipeline_run_id)` with `_verify_signature(header, body, pipeline_run_id) -> bool` that handles both formats.
    - Deployment manifests + `.env.example` — rename `COMPLETION_CALLBACK_SECRET` → `PIPELEX_WEBHOOK_SIGNING_SECRET`. Value unchanged; same shared secret.
- **Surface:**
    ```python
    def _verify_signature(header: str | None, body: bytes, pipeline_run_id: str) -> bool:
        if header is None:
            return False
        secret = get_required_env("PIPELEX_WEBHOOK_SIGNING_SECRET").encode("utf-8")
        if header.startswith("sha256="):
            expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(header.removeprefix("sha256="), expected)
        # Legacy: bare-hex over pipeline_run_id. Drops in Step 3.
        log.warning("Legacy webhook signature format received; sender should upgrade.")
        expected = hmac.new(secret, pipeline_run_id.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(header, expected)
    ```
- **Tests:**
    - sha256-prefixed format verifies a body-bytes signature correctly.
    - Bare-hex format still verifies a pipeline_run_id signature correctly.
    - Bare-hex format triggers the deprecation log.
    - Wrong signature in either format returns `False`.
    - Missing header returns `False`.
- **Acceptance:** receiver works with both old and new pipelex workers during the rollout window.

### [ ] Item 2 — Pipelex-side body-bytes signing

- **Files:**
    - `pipelex/pipe_run/delivery_executor.py:_notify_webhook` — compute HMAC-SHA256 over the request body bytes; set `X-Completion-Signature: sha256=<hex>` header before POST. Read `PIPELEX_WEBHOOK_SIGNING_SECRET` from `os.environ` at delivery time. Raise `PipelexConfigError` if the secret is missing **and** webhooks are configured.
    - `pipelex-api/api/routes/pipelex/pipeline.py` — **stop** populating `X-Completion-Signature` at dispatch time. The `WebhookTarget.headers` no longer carries it. Pipelex now owns signing end-to-end.
- **Surface (sketch):**
    ```python
    async def _notify_webhook(self, pipeline_run_id, status, result_url, webhook) -> None:
        payload: dict[str, Any] = dict(webhook.payload)
        payload["pipeline_run_id"] = pipeline_run_id
        payload["status"] = status
        if result_url is not None:
            payload["result_url"] = result_url

        # Sign the exact bytes we send. `content=body_bytes` below — not `json=payload` —
        # so httpx cannot reformat the JSON after signing.
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        secret = os.environ.get("PIPELEX_WEBHOOK_SIGNING_SECRET")
        if secret is None:
            msg = (
                "Webhook signing secret not configured. "
                "Set PIPELEX_WEBHOOK_SIGNING_SECRET in the worker environment."
            )
            raise PipelexConfigError(msg)
        signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        headers = {
            **webhook.headers,
            "X-Completion-Signature": f"sha256={signature}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(webhook.url, content=body_bytes, headers=headers, timeout=30.0)
            response.raise_for_status()
    ```
- **Tests** (`tests/unit/pipelex/pipe_run/test_delivery_executor.py`):
    - Signature is deterministic for fixed (secret, body) pairs.
    - Signature matches `hmac.new(secret, body, sha256).hexdigest()` (compare against the receiver-side computation in Item 1).
    - Flipping a single byte in the body produces a different signature.
    - Missing-secret-with-webhook-configured raises `PipelexConfigError` and the message names the env var.
    - Webhook with no recipients (empty `delivery_assignment.webhooks`) succeeds without requiring the secret.
    - The exact bytes posted to httpx match the exact bytes signed (no whitespace drift from JSON serialization).
- **Acceptance:** rewriting `status`, `result_url`, or `error` in transit causes signature verification to fail on the receiver.

### [ ] Item 3 — Drop legacy fallback in receiver

- **Files:**
    - `pipelex-api/api/routes/pipelex/pipeline.py` — remove the bare-hex branch and the legacy verification path; `_verify_signature` becomes the sha256-only path.
- **Pre-conditions:**
    - Item 2 deployed to all pipelex workers.
    - Deprecation log line from Item 1 has been quiet for one full retention window (typically a week).
- **Tests:** existing tests for sha256-prefixed verification continue to pass; bare-hex tests are deleted.
- **Acceptance:** code surface is now small. One signing pattern, one secret, one verification path.

---

## End-to-end acceptance test

Independent of per-item tests, this scenario pins the cross-repo contract once Items 1 and 2 are deployed:

1. Dispatch a real pipeline run that triggers a webhook.
2. Observe the webhook arrive at a test receiver wired to `_verify_signature` from Item 1.
3. Verify the receiver accepts the sha256-prefixed signature.
4. **Flip one byte in the body** between worker-side signing and receiver-side verification (e.g. via an httpx-MockTransport interceptor).
5. Verify the receiver rejects the tampered body.

---

## Deferred follow-ups (out of scope)

### Replay attack mitigation

The current design protects against tamper-in-transit but **not against replay** — an attacker who captures a valid signed webhook can resubmit it. Standard mitigations: include a timestamp in the signed payload, have the receiver enforce a freshness window (e.g. ±5 minutes), reject duplicates by `pipeline_run_id` if the receiver maintains a dedupe cache.

**Why deferred.** No current consumer has asked. The active threat model is "MitM rewrites body in transit," not "attacker captures and resubmits." Pick this up when a partner integration asks for it or when the threat model evolves.

### Secret rotation

Rotating `PIPELEX_WEBHOOK_SIGNING_SECRET` today requires coordinated env-var updates on worker and receiver, with a brief window where webhooks fail verification. Standard mitigation: support **two** secrets simultaneously (current + previous) — worker signs with the current, receiver tries both. Rotate by setting the previous secret, deploying, then dropping it in a follow-up deploy.

**Why deferred.** Secret rotation isn't operationally needed yet (no schedule, no compromise event). The dual-secret pattern is a small addition to the verifier when it's needed.

---

## Tracking

| ID | Item | Pre-condition | Status |
|---|---|---|---|
| 1 | Receiver-side dual-format verification | — | [ ] |
| 2 | Pipelex-side body-bytes signing | Item 1 deployed | [ ] |
| 3 | Drop legacy fallback in receiver | Item 2 deployed + deprecation log quiet | [ ] |

---

## Cross-repo coordination

This plan spans the pipelex and pipelex-api repos. The 3-step rollout is intentionally ordered across separate PRs in separate repos — no lockstep deploy.

The pipelex-api companion plan (when written) lives at `pipelex-api/wip/security/webhook-signing.md` and describes the receiver-side changes from its own perspective.

---

## How this relates to the error-handling refactor

The error-handling refactor at [`error-handling/`](error-handling/) (and its execution plan at [`../TODOS.md`](../TODOS.md)) lands Item D-2, which puts a structured `error` dict on the webhook body. That meaningfully expands the tamper surface — a MitM body rewrite previously could change `status` / `result_url`, now it can also rewrite the classification.

The error-handling refactor is **the motivating context** for accelerating this signing work, but the signing fix itself is correct independent of D-2. The two PR series can be merged on independent schedules; there is no functional dependency.
