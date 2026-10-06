# Error Responses

Every error returned by the API uses the RFC 7807 `application/problem+json` envelope. The same shape applies across pipelex domain errors, validation errors, auth failures, payload-size limits, and the catch-all 500.

## Envelope

A failure response looks like this:

```json
{
  "type": "https://docs.pipelex.com/latest/errors/validate-bundle-error/",
  "title": "Validate bundle",
  "status": 422,
  "detail": "TOML syntax error at line 1, column 6: Expected '=' after a key in a key/value pair",
  "instance": "/v1/validate",
  "error_type": "ValidateBundleError",
  "error_domain": "input",
  "retryable": false,
  "request_id": "9f2c1ab3-…"
}
```

`Content-Type` is `application/problem+json` and `X-Request-ID` is always echoed in the response headers.

## Fields

**Standard RFC 7807 members** — `type`, `title`, `status`, `detail`, `instance`.

**Extension members** — only `error_type` is always present; the others appear when the originating error populates them:

- `error_type` — stable class name of the originating error (`ValidateBundleError`, `EnvVarNotFoundError`, `WorkflowExecutionError`, …). The same identifier the `type` URI is derived from.
- `error_domain` — one of `input`, `config`, `runtime`. See [Status codes](#status-codes). Absent for domain-less pipelex errors (some pipelex tool errors, e.g. `EnvVarNotFoundError`, do not classify a domain — the HTTP status still defaults to **500**).
- `retryable` — whether retrying the same request can plausibly succeed. Always emitted for API-authored 4xx/5xx (always `false`). For pipelex-originated errors, present only when the source error populates it — `true` only when the originating error explicitly classifies itself as transient (e.g. inference provider rate limits); absent on pipelex errors that don't set it (e.g. `EnvVarNotFoundError`, `PipelexConfigError`).
- `request_id` — server-correlated identifier for the request. Echoed from inbound `X-Request-ID` if provided, otherwise generated. Use this when reporting issues.
- `error_category` — finer classification when the originating error provides one (currently used by inference errors — see [`InferenceErrorCategory`](https://docs.pipelex.com/latest/errors/) upstream).
- `user_action` — structured suggestion of what the caller should do next, when the error can author one.
- `model`, `provider`, `provider_metadata` — populated when the failure originated in an upstream inference call. **Stripped under STRICT disclosure** (see [Disclosure modes](#disclosure-modes)).
- `validation_errors` — structured per-error list carried by a `ValidateBundleError`. On the run routes (`/execute`, `/start`) it rides this 422 problem document; on the diagnostic routes (`/validate`, `/resolve`, `/codegen`, `/pipe-io`) it rides the **200 `is_valid: false`** body instead (see [Pipe Validate](pipe-validate.md)). See [Structured validation errors](#structured-validation-errors).

## Structured validation errors

When a bundle fails validation, the `ValidateBundleError` carries a `validation_errors` array — the per-error diagnostics an editor maps to per-line problems. Where it surfaces depends on the endpoint: on the diagnostic routes (`/validate`, `/resolve`, `/codegen`, `/pipe-io`) it rides the **200 `is_valid: false`** body (the diagnostic-endpoint contract — see [Pipe Validate](pipe-validate.md)); on the run routes (`/execute`, `/start`) — where an invalid bundle means the run cannot proceed — it rides the **422** problem document alongside the single human-readable `detail`. Built by pipelex's one shared builder, the items are identical wherever they appear (and to the agent CLI's). Each item is one categorized validation failure:

| Field | Meaning |
|---|---|
| `category` | The failure family — one of `blueprint_validation`, `pipe_factory`, `pipe_validation`, `dry_run`. |
| `message` | Human-readable description of this specific error. |
| `error_type` | Finer error subtype within the category, when the source error provides one. |
| `source` | The owning file of the error, when the runtime could attribute it to one: on `blueprint_validation` and `pipe_validation` items, and on a `dry_run` item, where it is the file of the pipe whose dry run failed. On the in-memory submit path it is the matching `mthds_sources[i]` (see [Sourcing submitted files](pipe-validate.md)), so it is absent when the caller sent no sources. Absent on `pipe_factory` items and on the parse-level residual described below. Beside a server's own library directories, an item never names one of their files. |
| `pipe_code`, `concept_code`, `domain_code` | The pipe / concept / domain the error is about, when applicable. On a `dry_run` item they name the innermost pipe that failed, not the controller the failure passed through. |
| `field_path`, `field_name` | The offending field within the bundle, when the error localizes to one. |
| `variable_names`, `missing_concept_code`, `missing_pipe_code`, `declared_concepts` | Extra context for specific failure shapes (undefined variables, an unresolved concept or pipe reference, the set of concepts that were declared). |
| `line`, `column` | The 1-based position where the TOML parser stopped, on a TOML syntax error. |
| `model_reference`, `model_type`, `suggestions` | On an `unknown_model` item — a pipe naming a model the deployment's model deck does not define — the reference as the bundle wrote it, the kind of model the pipe needs (`llm`, `extract`, …), and the deck's close matches of that kind. With exactly one suggestion the item also carries an `unsafe` `suggested_fix` renaming the model. |
| `suggested_fix` | A structured, deterministic fix for this error — present only when the fix planner derived one. See [Suggested fixes](#suggested-fixes). |

Items carry only the fields that apply to their category — absent fields are omitted, not null. `validation_errors` is **retained under STRICT disclosure** (it describes the caller's own submitted bundle, not server internals). It is present only on `ValidateBundleError`; other error types omit it.

Every invalid verdict carries a **non-empty** `validation_errors` array — the structured-info invariant is total. A parse-level failure the runtime cannot attribute to a known pipe/concept/field — an empty blueprint, an elaborator failure — still becomes one `blueprint_validation` residual item carrying the failure message (no `source`, no `error_type` at this layer), so the array is never empty on an invalid verdict. A TOML syntax error is an item of the same category without an `error_type`, which carries the `line` and `column` the parser stopped at and the `source` when the caller sent one. A failing dry run is one `dry_run` item per failing pipe, located at the innermost pipe that failed. The richer, locator-bearing items appear only when the runtime could attribute the failure; the human-readable summary (the `detail` on a run-route 422, the `message` on a diagnostic-route 200 invalid verdict) stays available alongside, but a consumer can always read at least one structured item.

On the run routes, **every refusal of the bundle while it loads is this verdict**, and the load happens before any pipe runs: a misspelled concept, a wiring mismatch, an unknown model, a TOML fault or a refusal raised while a pipe is built all answer the same **422** carrying the same items validating the bundle gives. None of them reaches a run as a `500`. An entry pipe the bundle does not declare keeps its own `EntryPipeNotFoundError`, and a bare code matching pipes in several domains its own `EntryPipeAmbiguousError`.

## Suggested fixes

A validation error item may carry a `suggested_fix`: a deterministic repair the runtime's fix planner derived from the *typed* error data — never by parsing a message string. It is optional and additive. An item the planner has no rule for simply omits the field, and a client that ignores `suggested_fix` entirely behaves exactly as before.

```json
{
  "category": "pipe_validation",
  "message": "Pipe 'summarize_and_translate' declares output 'Text' but its last step produces 'Translation'",
  "error_type": "inadequate_output_concept",
  "pipe_code": "summarize_and_translate",
  "source": "translate.mthds",
  "suggested_fix": {
    "fix_code": "match-sequence-output",
    "description": "Set output of pipe 'summarize_and_translate' to 'Translation' to match its last step",
    "safety": "safe",
    "source": "translate.mthds",
    "ops": [
      {
        "kind": "set_key",
        "table_path": ["pipe", "summarize_and_translate"],
        "key": "output",
        "value": "Translation"
      }
    ]
  }
}
```

**Fields:**

- `fix_code` — the kebab-case rule id that produced the fix (`match-sequence-output`, `sync-controller-inputs`, `strip-native-concept-redecl`, `strip-namespace`, `delete-redundant-dotted-input`, …). Stable; use it to allow-list or suppress rules.
- `description` — human-readable summary of what the fix does.
- `safety` — `safe` or `unsafe`. Only apply an `unsafe` fix behind an explicit opt-in: it is a likely correction, such as the one close match for an unknown model, that a person or an agent must confirm, and `pipelex fix bundle` never applies one on its own.
- `source` — the file the ops target, when known. **An applier must only apply ops to the file they target** — in a multi-file library the ops are meaningless against any other file.
- `ops` — the semantic TOML patch operations, in order.

**Ops** are addressed by `table_path` (the containing table, e.g. `["pipe", "my_seq"]` — the same addressing convention as the items' `field_path`). An op is a **union discriminated on `kind`**: read `kind` off the wire and you know exactly which other fields the op carries, because each kind is its own shape in the OpenAPI artifact rather than one open shape with everything optional.

| `kind` | Effect | Carries besides `table_path` |
|---|---|---|
| `set_key` | Set (or add) a key in the table | `key`, `value` |
| `ensure_table` | Create the table when it is absent | — |
| `delete_key` | Remove a key from the table | `key` |
| `delete_table` | Remove the table | — |
| `rename_table_key` | Rename a key in place, keeping its position | `key`, `new_key` |
| `move_key` | Relocate a key to another table, creating missing destination parents | `key`, `new_table_path`, `new_key` |
| `remap_value` | Rewrite a key's string value through an explicit old-to-new `mapping`, doing nothing when the current value is not a mapped one | `key`, `mapping` |

For `ensure_table` and `delete_table`, `table_path` addresses the table itself rather than its parent, so it is never empty — the document root always exists and is never a target. `move_key` is addressed at both ends and the two ends follow different rules: `table_path` is the table the key currently sits in, per the general convention above, while `new_table_path` addresses the destination table itself. Neither is constrained to be non-empty: an empty `table_path` reads a key off the document root, and an empty `new_table_path` moves it there. `move_key` moves a table-valued key with its whole subtree.

`value` is a TOML scalar (string, integer, float, boolean) or a flat scalar mapping, which a fix that must create a whole table at once — a missing `inputs` mapping, say — writes as an inline table.

**The ops are the machine contract; any rendered diff is presentation.** Apply them with a style-preserving TOML editor rather than reconstructing the file from a diff: that is what keeps the caller's formatting, comments, and key order intact.

## Run failures: the root fault, located at the failing pipe

When a run fails, the problem document describes the **root fault**, the innermost Pipelex error on the cause chain, never the run-level wrapper around it: `error_type`, `title` and `type` are the root fault's, and so are `error_domain`, the HTTP status and whether STRICT disclosure keeps the `detail`. The `detail` names the pipe that failed and its path from the entry pipe, `Pipe '<failing pipe>' failed (<entry pipe> → … → <failing pipe>): <the fault's own message>`, and `user_action` names the next step for that pipe. A consumer that branched on `error_type == "PipelineExecutionError"` branches on the root fault's type instead.

So a run the caller's own method refuses reads its reason even under STRICT: a `PipeCondition` whose outcome is `fail`, a `PipeParallel` branch whose multiplicity does not match its output field, a step started without a required input, or a model named inline that the deck does not define all answer a **422** in the `input` domain, with a `detail` that says what to change. A model the deck names but does not serve stays a redacted `config` failure, since the deployment, not the caller, has to fix it.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json

{
  "type": "https://docs.pipelex.com/latest/errors/stuff-factory-error/",
  "title": "Stuff factory",
  "status": 422,
  "detail": "Pipe 'analyze_topic' failed (review_topic → analyze_topic): PipeParallel 'analyze_topic' cannot combine its branch results into its output 'TopicReview'. Branch 'draft_idea' gives result 'ideas' as a single 'Idea', but field 'ideas' of 'TopicReview' holds a list. Declare the field as a single concept in the structure of 'TopicReview', with type 'concept' and concept_ref 'Idea', or make branch 'draft_idea' output 'Idea[]'.",
  "instance": "/v1/execute",
  "error_type": "StuffFactoryError",
  "error_domain": "input",
  "user_action": {
    "kind": "change_input",
    "detail": "Branch 'draft_idea' gives result 'ideas' as a single 'Idea', but field 'ideas' of 'TopicReview' holds a list. Declare the field as a single concept in the structure of 'TopicReview', with type 'concept' and concept_ref 'Idea', or make branch 'draft_idea' output 'Idea[]'."
  },
  "request_id": "9f2c1ab3-…"
}
```

The failure of a `/start` run reaches its completion webhook as the same report, under the payload's `error` key (see [Async callbacks](#async-callbacks-webhook-payload)).

## Status codes

The HTTP status follows pipelex's `error_domain_to_http_status`:

- `error_domain = "input"` → **422** — the caller can fix it (bad `.mthds`, malformed arguments, validation failure).
- `error_domain = "config"` → **500** — the deployment needs a fix (missing env var, bad TOML override).
- `error_domain = "runtime"` → **500** — failure during execution (worker crash, upstream service failure).
- Unclassified / unknown → **500**.

A few specific statuses bypass the domain mapping:

- **400** — a well-formed request this deployment cannot serve. `error_type = "StartRequiresAsyncOrchestration"`: `POST /v1/start` is fire-and-forget by nature, and this deployment's orchestrator is blocking-only (the in-process `direct` default), so it refuses honestly rather than blocking and acking — use `POST /v1/execute` instead.
- **400** — `error_type = "BadRequest"`: the client disconnected before its request body was received in full. The client is gone before the answer, so this one is seen in the server's logs, at warning level.
- **401** — missing/invalid bearer token. `WWW-Authenticate: Bearer` is set. Only reachable when the deployment enables auth (`AUTH_MODE=api_key` or `AUTH_MODE=jwt`).
- **403** — authenticated but not authorized, or refused by deployment policy. The cases: a storage-ownership mismatch; `error_type = "OrchestrationModeOverrideForbidden"` — the request asked for an `orchestration_mode` this deployment does not allow overriding per request (`allow_request_orchestration_mode_override = false`); `error_type = "CustomCodeRequiresSandbox"` — the method (an uploaded bundle, or a fetched `method_ref` package) ships custom Python `.py` files and this deployment is not sandbox-hosted, so running caller-supplied code in-process is refused; `error_type = "MethodStructuresRefusedError"` — a fetched `method_ref` package declares in-process Python structure classes (`StructuredContent` subclasses), which hosted execution always refuses, sandbox or not — express the types as MTHDS concepts with inline structures instead (see [Pipe Run](pipe-run.md#running-a-method-by-address-method_ref)).
- **404** — `error_type = "MethodPackageNotFoundError"`: the `method_ref` repository was fetched, but no package in it matches the requested address by manifest identity. The `detail` lists the package addresses the repository does contain, so the caller can correct the selector.
- **409** — `error_type = "PipelineManagerAlreadyExistsError"`: the submitted `pipeline_run_id` is already registered for a run that is still in flight on this server. Completed and failed runs free their id, so this only fires for genuinely concurrent duplicates — resubmit after the in-flight run finishes, or pick a fresh id. Only `POST /v1/start` accepts a client-supplied `pipeline_run_id`, so only `/start` can produce it.
- **413** — request body exceeds the configured size limit (`MAX_REQUEST_BODY_MIB`, 100 MiB by default).
- **429** — an upstream inference provider rate-limited the run. `Retry-After` is set when the originating error carries `provider_metadata.retry_after_seconds`. Only `POST /v1/execute` runs inference, so only `/execute` can produce it.
- **501** — a request shape the published contract accepts but this server cannot serve. `error_type = "AsyncExecutionNotEnabledError"`: this deployment does not provide async pipeline execution (`POST /v1/start`). `error_type = "MethodRefNotSupported"`: the request selected its closure by a **registry-form** `method_ref` — not a `github.com/...` address — and no server-side method registry resolves those yet. Address-form references are fetched and resolved server-side (see [Pipe Run](pipe-run.md#running-a-method-by-address-method_ref)); use one of those, or submit inline `files[]`. Both 501s are permanent under the current deployment — do not retry.

The `method_ref` resolution errors are also mapped explicitly rather than through the domain table: `MethodRefParseError`, `MethodFetchError`, `MethodPackageAmbiguityError`, `MethodPackageTooLargeError` and `MethodPackageSymlinkError` are **422** (the caller can fix the reference, pin a tag, shrink the package, or remove the symlink it carries), `MethodPackageNotFoundError` is the **404** above, and `MethodStructuresRefusedError` is a **403**, whether the method was fetched by `method_ref` or sent as a bundle. These pipelex `MethodRefError` subclasses do not classify an `error_domain`, so without the explicit mapping they would fall through to the 500 default — which would misreport caller-fixable failures as server faults.

Every route that takes a JSON body refuses one whose arrays and objects nest more than 128 levels deep, the body's own envelope included, with a **422** `InvalidJSON` whose `detail` says the body is nested too deeply. The depth is checked before the body is parsed, so the answer does not depend on the Python version or the stack size the server runs with. The bound is fixed rather than configurable, and real inputs stay far below it.

The run routes read their body as plain JSON before anything else, and two refusals come from that step, both **422**. A body that is not valid UTF-8, not valid JSON, nested too deeply, or not a JSON object answers `InvalidJSON`. A body carrying, in any object at any depth, a key named `__class__` or `__module__`, or a key starting with `__kajson`, answers `ReservedObjectKey`, and the `detail` names the key, cut short when it is long. Those are the keys a kajson decoder reads as an order to import and instantiate a class, so the runner refuses them rather than carry them as data. Only keys are checked: a string value that mentions `__class__` is accepted.

A pipe selection the server cannot make is an input **422** named for its failure, never the generic `ValidationError`: `EntryPipeNotFoundError` when the selector names no pipe, and `EntryPipeAmbiguousError` when a bare code matches pipes in several domains. The run routes answer an unknown or ambiguous `pipe_code` that way. `POST /v1/pipe-io` answers every selection refusal that way, counting a request with no `pipe_ref` over a method that declares no `main_pipe` as `EntryPipeNotFoundError` and one over a method whose domains declare several as `EntryPipeAmbiguousError` (see [Pipe I/O](pipe-io.md#pipe-selection)).

The run routes' extension fields are validated before any method is fetched or any library loaded, and a failure there is a **422** whose `error_type` names the field that failed: `InvalidCallbackUrls` for `callback_urls`, `InvalidStorageScope` for `storage_scope`, `InvalidReadScope` for `read_scope`, `InvalidAnalyticsGroups` for `analytics_groups` (see [Pipe Run](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups)). A storage scope that does not lie under the run's read scope, whether either was sent or defaulted, is an `InvalidReadScope` as well. A failure on another extension field, or on more than one at once, carries the generic `ValidationError`, and the `detail` names every field that failed. `POST /v1/validate` takes `analytics_groups` too and classifies it the same way: a body failing on that field alone answers `InvalidAnalyticsGroups`, and one failing on it and another field answers `ValidationError`.

The HTTP status is the source of truth for success vs failure — there is no `success: true/false` field anywhere in the envelope.

Which statuses a given route can actually produce is documented per operation in the [committed OpenAPI artifact](openapi/pipelex-api.openapi.yaml), each as an `application/problem+json` `ProblemDocument`.

**What is *not* an error status:** an invalid `.mthds` bundle. On the diagnostic routes — `/validate`, `/resolve`, `/codegen`, and `/pipe-io` — a bundle that fails validation is the *successful product* of the call, so it rides a **200** discriminated on `is_valid: false`, carrying the same `validation_errors[]` described above. Non-2xx on those routes is reserved for *no verdict could be produced*. See [Pipe Validate](pipe-validate.md).

## Disclosure modes

The `ERROR_DISCLOSURE` env var controls how much of the originating error makes it onto the wire:

- `verbose` (default) — renders the full `ErrorReport`. Use in dev, staging, and any deployment where the caller is trusted.
- `strict` — redacts `detail` and provider fields for errors that do not author caller-facing messages. Specifically:
    - `detail` is preserved only when the error authored a caller-facing message: the bundle's validation verdict (`ValidateBundleError`), a parse error (`MthdsParserError`), and a failure the runtime classifies as the caller's own, such as a pipe refused while it is built or a run that the submitted method itself refuses (see [Run failures](#run-failures-the-root-fault-located-at-the-failing-pipe)). Everything else has `detail` replaced with a generic title-derived string.
    - `model`, `provider`, `provider_metadata` are always stripped — they have no business on a caller-facing surface.
    - The redaction is keyed on the **provenance of the message** (`_authors_caller_facing_message` ClassVar), not on `error_domain`. A `RuntimeError` raised `from` an `INPUT`-domain cause does not leak the wrapper's internal message.

Server logs are always verbose regardless of `ERROR_DISCLOSURE` — the operator sees the full picture, the caller sees what the error chose to disclose.

The mode governs **every** response, including the catch-all 500 (`error_category: "unknown"` — a failure that matched no more specific handler). Under `verbose` its `detail` is `"<ExceptionClass>: <message>"`; under `strict` it is the fixed `"An unexpected error occurred. The request id is included for support."`. A traceback never reaches the caller in either mode.

An unclassified failure is the one error a caller cannot diagnose from a request id alone, so it is exactly the one a `verbose` deployment must not turn into a dead end. If you want unclassified failures opaque, that is what `strict` is for — and note it redacts by message provenance, so a deployment wanting *nothing* leaked should set `strict` rather than rely on the catch-all to be silent.

## The `type` URI

`type` is a stable URI pointing at the per-class documentation page upstream:

```
https://docs.pipelex.com/latest/errors/<kebab-class-name>/
```

Every `PipelexError` subclass resolves to a live page (the trailing slash is canonical — pipelex emits it to match the MkDocs `use_directory_urls: true` form). The page describes the class, the typical cause, and how to recover.

API-authored errors (`ValidationError`, `BadRequest`, `Unauthenticated`, etc.) follow the same convention with their own slugs.

## Request correlation

Every response carries `X-Request-ID`. The middleware respects an inbound `X-Request-ID` header if present, otherwise mints one. It also binds that id onto the Pipelex runtime's log context for the duration of the request, so every record emitted underneath carries it as a `request_id` field — the server's own error lines and the runtime's lines from inside a run alike. Both run routes, `POST /v1/execute` and `POST /v1/start`, also put the id on the run's metadata, so when a run is dispatched to a worker, the lines the worker writes while it runs the run's workflow and activities carry the same id. What those lines look like, which fields they carry and where the id does not reach are in [Logging](logging.md).

When opening an issue, include the `request_id` from the response (or response headers) and the timestamp.

## Examples

### 422 — input validation failure

```http
POST /v1/execute
{
  "mthds_contents": ["domain = \"broken\"\nmain_pipe = \"Not A Valid Pipe Code!\"\n"]
}
```

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://docs.pipelex.com/latest/errors/validate-bundle-error/",
  "title": "Validate bundle",
  "status": 422,
  "detail": "Value error, Invalid main pipe syntax 'Not A Valid Pipe Code!'. Must be in snake_case.",
  "instance": "/v1/execute",
  "error_type": "ValidateBundleError",
  "error_domain": "input",
  "user_action": {
    "kind": "change_input",
    "detail": "Edit the bundle as each validation error says: apply its suggested fix where it has one, after confirming an unsafe one"
  },
  "request_id": "9f2c1ab3-…",
  "validation_errors": [
    {
      "category": "blueprint_validation",
      "message": "Value error, Invalid main pipe syntax 'Not A Valid Pipe Code!'. Must be in snake_case.",
      "error_type": "invalid_pipe_code_syntax",
      "domain_code": "broken"
    }
  ]
}
```

The single `detail` is the human summary; `validation_errors` is the machine-readable list a client maps to per-line diagnostics. Only the run routes answer an invalid bundle with this 422 — on the diagnostic routes the same bundle is a **200 `is_valid: false`** verdict, where per-file `source` attribution is also available — see [Structured validation errors](#structured-validation-errors) and [Sourcing submitted files](pipe-validate.md).

### 500 — deployment configuration fault

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://docs.pipelex.com/latest/errors/env-var-not-found-error/",
  "title": "Environment variable not set",
  "status": 500,
  "detail": "Missing required environment variable: COMPLETION_CALLBACK_SECRET",
  "instance": "/v1/start",
  "error_type": "EnvVarNotFoundError",
  "request_id": "9f2c1ab3-…"
}
```

`EnvVarNotFoundError` is a domain-less pipelex tool error — neither `error_domain` nor `retryable` is populated on the report, so both extension members are absent on the wire. The HTTP status is still **500** (the deployment, not the caller, has to fix it), but the classification fields only ride along when the originating error sets them. See [Fields](#fields).

Under `ERROR_DISCLOSURE=strict` the same failure has `detail` redacted to `"Server configuration error"` — the env var name lives in the server log only.

### 401 — missing bearer token

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: Bearer
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://docs.pipelex.com/latest/errors/unauthenticated/",
  "title": "Unauthenticated",
  "status": 401,
  "detail": "Missing bearer token.",
  "instance": "/v1/execute",
  "error_type": "Unauthenticated",
  "error_domain": "input",
  "retryable": false,
  "request_id": "9f2c1ab3-…"
}
```

## Async callbacks (webhook payload)

For [async pipeline runs](pipe-run.md) registering a `callback_url`, the failure payload delivered to the caller's webhook **does not** use this envelope. The webhook body carries the raw `ErrorReport` dict under an `error` key, alongside `pipeline_run_id` (the protocol field) plus the runtime's legacy `pipeline_run_id` / `status` keys — a non-HTTP receiver (queue, log shipper) does not necessarily want an RFC 7807 wrapper.

The classification fields (`error_type`, `error_domain`, `retryable`, etc.) surface identically on both paths; only the envelope members (`type`, `status`, `detail`, `instance`, `request_id`) are sync-only. See [Pipe Run → Async Completion Callbacks](pipe-run.md) for the full webhook contract.
