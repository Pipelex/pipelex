---
description: "The webhooks a Pipelex API server sends when a run ends: the signed run.finished event each of a request's callback_urls receives, and the completion notice a deployment's own completion target receives."
---

# Webhooks

When a run ends, the API server can tell two different receivers about it, and the two never mix:

- **The caller's webhooks**: the `callback_urls` a request to `POST /v1/execute` or `POST /v1/start` registers. Each receives the signed `run.finished` event described below, under a secret the server's operator configures.
- **The deployment's completion target**: one URL the operator configures with `COMPLETION_CALLBACK_URL`, which a `/start` run notifies with a completion notice carrying its own signature. It is how a deployment that hosts the server learns a run ended, and it never receives a caller's event.

`callback_urls` is a **pipelex-api extension**, not part of the MTHDS Protocol, which defines no completion channel. SDK clients pass it through the generic `extra` mapping, e.g. `client.start(..., extra={"callback_urls": [...]})`.

## Registering callback URLs

```json
{
  "pipe_code": "your_pipeline_code",
  "inputs": { "input_name": "..." },
  "pipeline_run_id": "order-4242-run-1",
  "callback_urls": ["https://my-app.example.com/pipelex-finished"]
}
```

Both run routes take the field. A blocking `/execute` sends its events before it answers, since its caller may have lost the connection by then, so a receiver that never answers delays the response by about 51 seconds at most, three attempts of 15 seconds and the waits of 1 and 5 seconds between them, and a `/start` run sends them when the run ends. On `/execute` as on `/start`, a request may choose the run's `pipeline_run_id`, which the events then carry: a run still in flight under the same id refuses the request with a `409` `pipelex.run.already_exists`. A URL listed twice is delivered once.

A callback URL is refused before anything runs with a **422** `security.input_url_refused` when its scheme is not `http` or `https`, or when its host is one the runtime's SSRF rule refuses: `localhost`, a cloud metadata name such as `metadata.google.internal` in any case and with or without a trailing dot, or a literal address that is not publicly routable, a loopback, private, link-local, carrier-grade NAT or cloud metadata address among them. A scheme-relative URL, such as `//169.254.169.254/latest/meta-data`, is refused the same way when its host is one the rule refuses. It is the rule the delivery applies again when the webhook fires, resolving the name, and such a refusal also writes a [security event](logging.md#security-events). A callback URL that is not a URL at all, empty, longer than the limit, with no scheme, naming no host, or opening no authority with `//`, such as `example.com:8080/hook` or `localhost:3000/cb`, is a **422** `request.invalid` naming the field `callback_urls` and writes none.

**A signing secret is required.** The server signs every call it makes to a caller's webhook, so a server whose operator set no `CALLER_WEBHOOK_SECRET` refuses a request carrying `callback_urls` with a **422** [`pipelex.webhook.secret_not_configured`](../errors/pipelex/webhook/secret_not_configured.md), whose `params.setting` names the variable, before the method is fetched, written or run. A request without `callback_urls` never needs the secret. A value that is not a `whsec_` secret is the server's misconfiguration, a **500** `runtime.misconfigured` whose `component`, the variable's name, only an operator reads.

## The run.finished event

Each URL receives one POST per attempt, whose body is the `run.finished` event, compact JSON in UTF-8:

```json
{"type":"run.finished","timestamp":"2026-10-22T11:59:58.250Z","attempt":1,"data":{"pipeline_run_id":"order-4242-run-1","status":"failed","error":{"type":"https://mthds.ai/errors/run.timed_out","title":"The run passed its time limit","detail":"…","code":"run.timed_out","domain":"method","retry":"no","next_step":{"kind":"change_method","detail":"…"},"params":{"timeout":3600},"pipeline_run_id":"order-4242-run-1"}}}
```

| Member | Value |
|---|---|
| `type` | `run.finished`, for every ending: the outcome is `data.status`. |
| `timestamp` | When the run ended, an RFC 3339 date-time in UTC written with `Z`. |
| `attempt` | Which attempt of the delivery this call is, counted from 1. |
| `data` | The run as the MTHDS protocol's status read serves it: its `pipeline_run_id`, its `status`, `completed` or `failed`, and a failed run's problem as `error`. |

A run that was cancelled before it ended, such as when its server stopped mid-run, ended failed: its event reads `failed`, with the problem `run.cancelled`, and so does the completion notice of the deployment's completion target. A failed run's `error` is its problem document in the **caller's view**, whoever started the run: it carries the `code`, `detail`, `retry` and `next_step` the caller reads, and never `diagnostics`. It carries no `status` member, which is the HTTP envelope's. A member with no value is left out rather than written as `null`. The event never carries the run's results: the caller reads a `/execute` run's output from the response, and a `/start` run's results from storage.

A receiver ignores a member it does not know, and acknowledges an event whose `type` it does not know with a `2xx`.

## Verifying the signature

Every call carries the three [Standard Webhooks](https://www.standardwebhooks.com/) headers, so any Standard Webhooks library verifies it:

| Header | Value |
|---|---|
| `webhook-id` | The delivery's id, `whd_` followed by letters, digits and underscores: the same on every attempt of the delivery, and different for every other delivery. |
| `webhook-timestamp` | The attempt's send time, in whole Unix seconds. |
| `webhook-signature` | One `v1,` signature per secret the server holds, separated by single spaces. |

Each signature is the standard base64 of the HMAC-SHA256 of `{webhook-id}.{webhook-timestamp}.{body}`, the two header values exactly as sent and the body's bytes exactly as sent, under the key the secret carries: the standard base64 after its `whsec_` prefix, decoded. A receiver holding the secret recomputes it over the raw body, before parsing it:

```python
import base64, hashlib, hmac, time


def verify(*, secret: str, headers: dict[str, str], body: bytes) -> bool:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    if abs(time.time() - int(headers["webhook-timestamp"])) > 300:
        return False
    signed_content = f"{headers['webhook-id']}.{headers['webhook-timestamp']}.".encode() + body
    expected = "v1," + base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, signature) for signature in headers["webhook-signature"].split(" "))
```

The receiver rejects a call whose timestamp is more than five minutes from its own clock, and deduplicates on `webhook-id`, never on the body: the body changes with each attempt, since `attempt` is part of it.

**Rotating the secret.** `CALLER_WEBHOOK_SECRET` holds one secret, or several separated by spaces, the current one first. Every call is signed under each of them, so to rotate, set the new secret first and the old one after it, move the receivers to the new secret, then drop the old one.

**Trust model.** One secret, the operator's, signs every caller webhook the server sends, so any receiver that holds it can sign an event for any run, whoever started it. That suits a server with a single tenant, or with receivers that trust each other. A host that serves several tenants does not hand the secret to them: it receives the events itself and relays them to its tenants under credentials of its own.

## Delivery

Each URL is delivered on its own and at the same time as the others: one receiver's slowness or failure never delays or fails another's delivery.

- **When it is sent**: last, once the run's results are stored and the deployment's completion target notified, and once per URL. A run that completed but whose results cannot be stored, or whose completion target cannot be notified, ends failed, and its event says so, `failed` with that failure's problem, never `completed`.
- **What counts as delivered**: a `2xx` answered within 15 seconds of the call being sent. Anything else fails the attempt: another status, a redirect, which the server never follows, a time-out, a connection or TLS failure, and a host whose name resolves to a private, loopback, link-local or metadata address, which the server refuses to connect to and logs as a [security event](logging.md#security-events).
- **Retries**: a delivery makes three attempts, the second one second after the first failed and the third five seconds after the second, each keeping the delivery's `webhook-id`. A refused address is not tried again. The three attempts are those of one delivery step: when the step itself runs again, as a durable orchestrator may run a step that did not finish, the event is sent again under the same `webhook-id`, with its `attempt` counted from 1 again, so a receiver may see the same delivery more than once, more than three times in all, and deduplicates on `webhook-id`.
- **A delivery failure stays a delivery failure.** It is logged, as a warning naming the receiver's host, the attempts and the reason, and it never fails a run that succeeded nor replaces a run's own failure: the `/execute` response and the run's status are the run's.
- **No log, no replay.** The server keeps no delivery log and offers no way to send a delivery again. The receiver acknowledges at once and does its work afterwards, rather than spend its 15 seconds processing the run.

The server signs its calls with the secret of the process that runs the delivery. With an orchestrator that runs a `/start` run in another process, such as a Temporal worker, that process needs `CALLER_WEBHOOK_SECRET` too.

## The deployment's completion target

`COMPLETION_CALLBACK_URL` names the operator's own receiver, an absolute `http` or `https` URL which may name the run's id with one `{pipeline_run_id}` placeholder, such as `https://ops.example.com/runs/complete/{pipeline_run_id}`. A malformed value stops the server at boot, and leaving it unset gives the deployment no completion target. When set, every `/start` run notifies it, once, when the run ends; an `/execute` run, which answers with its result, does not.

The target receives a completion notice, not the caller's event:

- A JSON body with the run's `pipeline_run_id`, the delivery `state` (`"COMPLETED"` or `"FAILED"`, also sent under the legacy `status` key), `result_url` (when results were stored: the storage key prefix under which the result files sit, not a fetchable URL) and, for a failed run, `error`, its problem document in the **operator's view**, `diagnostics` included (see [Error Responses](error-responses.md#async-callbacks-webhook-payload)).
- An **`X-Completion-Signature`** header, `HMAC-SHA256(COMPLETION_CALLBACK_SECRET, pipeline_run_id)` rendered as a hex digest, which the receiver recomputes with its own copy of the secret:

```python
import hmac, hashlib

expected = hmac.new(SHARED_SECRET.encode("utf-8"), pipeline_run_id.encode("utf-8"), hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, request.headers["X-Completion-Signature"]):
    return Response(status=401)
```

`COMPLETION_CALLBACK_SECRET` is required once a completion target is set: the server refuses to boot with a target and without the secret, and a `/start` that meets that configuration anyway is refused with a `500` `runtime.misconfigured` before its method is fetched or its run set up. Unlike the caller's event, a failure to notify the completion target fails the delivery step, which a durable orchestrator repeats.

A host that forwards its completion URL among a request's `callback_urls`, as it did before the completion target had a setting of its own, is understood: a `callback_urls` entry equal to the run's completion URL is the deployment's hop, notified once with its completion notice, and never treated as a caller's webhook nor signed as one.
