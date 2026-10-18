# Error Responses

Every error returned by the API is an RFC 9457 `application/problem+json` **problem document**, named by a registry code and seen through the view the request's identity gives it. That holds for a failure the Pipelex runtime raised, which is every domain error, every run failure and the catch-all, and for a refusal the runner authors itself at its own boundary, such as a malformed body, a missing token, a payload over its limit or a path no route serves: there is one shape, and a client branches on its `code`.

## Envelope

A failure the runtime raised looks like this, in the caller view:

```json
{
  "type": "https://mthds.ai/errors/method.invalid",
  "title": "The method does not validate",
  "status": 422,
  "detail": "The method does not validate.",
  "code": "method.invalid",
  "domain": "method",
  "retry": "no",
  "next_step": {
    "kind": "change_method",
    "detail": "Fix each fault the problem's errors list, then validate the method again."
  },
  "errors": [
    {
      "code": "method.input_undeclared",
      "detail": "Pipe 'summarize' reads names its inputs do not declare: tone.",
      "params": { "pipe": "summarize", "variables": ["tone"] },
      "location": { "pipe": "summarize", "file": "summaries.mthds" }
    }
  ],
  "request_id": "9f2c1ab3-…"
}
```

`Content-Type` is `application/problem+json` and `X-Request-ID` is always echoed in the response headers. No member is ever written as `null`: a member with no value is absent.

## Members

**The RFC's members** — `type`, `title`, `status` and `detail` are always present:

- `type` — the page of the error's `code`. See [The `type` URI](#the-type-uri).
- `title` — the code's title, the same for every occurrence of the code.
- `status` — the HTTP status the code declares, repeated in the body. See [Status codes](#status-codes).
- `detail` — the sentence stating this occurrence, rendered from the code's template with the problem's parameters. It is written for a person to read: a program branches on `code`, never on a sentence.

**The MTHDS standard's members** — `code`, `domain`, `retry` and `next_step` are always present, and the others appear when they hold a value:

- `code` — the registry code naming the fault, such as `method.invalid` or `pipelex.config.variable_missing`: a code of the MTHDS standard, or a `pipelex.` code of the Pipelex error registry, listed on the [Error Codes](../errors/index.md) page. The code decides `type`, `title`, `status`, `domain`, `retry` and the sentences, so a consumer branches on it rather than on the class that raised the error, which a caller is never told.
- `domain` — who must act: `input` (the caller, by changing the request or its inputs), `method` (the method's author), `account` (the account's owner), `operator` (whoever runs this server) or `runtime` (nobody beforehand: wait, retry or report).
- `retry` — whether repeating the same request can succeed: `yes`, as for an inference provider's rate limit; `no`; or `outcome_unknown`, when the request may have taken effect. A client retries blindly only on `yes`.
- `retry_after` — on a code whose verdict is `yes`, the delay in seconds the provider asked for before a retry. A `429` also carries it as a `Retry-After` header, rounded up.
- `next_step` — what the reader does next: its `kind`, such as `change_input`, `change_method`, `change_model`, `wait`, `retry`, `fix_configuration` or `report`, and its `detail`, a sentence rendered from the code's template. The step is the reader's own, so the caller view and the operator view of one failure can give different steps.
- `params` — the facts the code's sentences name, by the registry's names, such as the failing `pipe` or the `model` a method named. A parameter only the operator may read never rides here.
- `location` — where the fault is: on a run failure the failing `pipe` and its `path` from the entry pipe, and elsewhere an `input`, a `field`, a batch `item`, an `attempt`, or a `file` with its `line` and `column`. See [Run failures](#run-failures-the-root-fault-located-at-the-failing-pipe).
- `errors` — one item per fault, for a refusal of several at once: each with its own `code`, `detail`, `params` and `location`, and on a method that does not validate the `suggestions` and `suggested_fix` of its validation item. See [Structured validation errors](#structured-validation-errors).
- `pipeline_run_id` — the run the problem belongs to.

**Pipelex's members:**

- `request_id` — server-correlated identifier for the request. Echoed from inbound `X-Request-ID` if provided, otherwise generated. Use this when reporting issues.
- `diagnostics` — present in the operator view alone. See [Views chosen by identity](#views-chosen-by-identity).

### The runner's own refusals

A refusal the runner authors itself, before the runtime is asked anything, is a problem document like any other, named by its code and seen through the view the request's identity gives it. Its `detail` and `next_step` are its code's sentences, and the runner's own account of what it checked rides the operator view's `diagnostics.message`. The codes it answers are listed under [Status codes](#status-codes). A few conventions hold across them:

- A field the route's rules refuse is `request.invalid`, whose `field` parameter, also its `location.field`, names the field as the request spells it, or a dotted path into the body such as `callback_urls.0`. When several fields fail at once, `errors` carries one `request.invalid` item per refused field, so a client fixes them all in one go, and the problem's own `field` is the first of them. The items stop at a bound, since a list the caller sent can fail item by item, and the operator view's `diagnostics.message`, which names each fault with pydantic's account of it, stops at the same bound and says how many more faults there were. A rule of the request model that concerns several fields together names the one to change: sending two of `mthds_contents`, `files` and `method_ref` names the second, sending none names the first, and `mthds_sources` beside a `method_ref`, or of another length than `mthds_contents`, names `mthds_sources`. Only a body that is not a JSON object names the field `body`.
- A body, or an encoded part of one, that cannot be parsed is `request.malformed`, whose `reason` says why: `not_json`, `not_utf8`, `integer_too_long`, `bad_base64`, `bad_zip`, `too_deeply_nested` or `body_incomplete`, and `unreadable` for a `400` or a `422` the framework raised while reading the request that no check of the runner's own made first, which keeps the status it was raised with. A client's malformed request is never answered as a fault of the server.
- Any other refusal the framework raises keeps its status and its meaning, under a code whose required parameters the runner can fill: the framework says nothing about a refusal but its status and a header, so a code whose parameters it cannot know gives way to one whose parameters it can. A `401` is `auth.missing_credential`, keeping the `WWW-Authenticate` challenge it was raised with; a `403` is `auth.invalid_credential`, since `auth.forbidden` names a `requirement` the framework does not; a `404` is `request.not_found`, and a `405` `request.method_not_allowed`, keeping its `Allow`; a `413` is `request.malformed` with the reason `too_large`, since `request.too_large` states a `limit` and a `size` the framework does not; and a `429` is `runtime.unavailable`, whose verdict invites a retry, keeping its `Retry-After`, since `account.rate_limited` states a `limit` and a `window` the framework does not. Any other `4xx`, such as a `415`, is `request.malformed` with the reason `unreadable`. Each answers with the status it was raised with, whichever status its code declares. A `5xx` the framework raises is its own fault, `runtime.unexpected`.
- A request past one of this runner's size limits is `request.too_large`, a **413** whose `limit` and `size` parameters give the limit and what the request carried, always in bytes: an encoded value, a file of `resources` or a `bundle_b64` archive, is measured by the bytes its encoded length carries, read before it is decoded.
- A method tree the runner refuses to read as a method is `method.package_invalid`, whose `reason` names the rule the tree breaks and whose `path` or `limit` says where or how far.

The members the runner's refusals used to carry are gone: no refusal carries an `error_type`, `error_domain`, `retryable` or `instance`. The request's path is not echoed, since `request_id`, which the runner takes from an inbound `X-Request-ID` or mints, is what correlates a response with the server's records.

## Views chosen by identity

A failure the runtime raised is one problem seen through a view, and the identity the request authenticated picks the view. No deployment setting picks it.

| How the request authenticated | View |
|-------------------------------|------|
| `AUTH_MODE=api_key`: the static API key is the operator's own credential | The operator view |
| `AUTH_MODE=none` with `TRUST_FORWARDED_IDENTITY_HEADERS=true`: the only party reaching this server is the trusted proxy in front of it, such as the hosted platform, which owes its own callers their caller view | The operator view |
| `AUTH_MODE=jwt`: a caller's token | The caller view |
| `AUTH_MODE=none` without the trusted proxy, or a request refused before any authentication ran | The caller view |

A refusal the runner authors before any authentication ran, such as a body over the size limit or a path no route serves, is answered in the caller view.

**The caller view** carries the code's sentences, rendered from the parameters a caller may read, and the step for the caller: for a code of the `operator` domain, whose actor is whoever runs this server, that is what the caller can do meanwhile, such as choosing another model. It never carries the error's own message, its class, a path on the host, a provider's answer or a foreign exception's text, whatever the failure. A problem this server relays with a code its own registries do not hold, such as one a newer worker built, reaches the caller with the generic step of its kind, and `report` for a code of the `operator` domain, since its recorded step was written for the operator.

**The operator view** adds the operator's step and `diagnostics`:

- `error_class` — the class of the error the problem was built from.
- `message` — that error's own message.
- `causes` — the errors along its cause chain, each with its class and the code it carries by itself.
- `params` — the parameters only an operator may read, such as the variable `pipelex.config.variable_missing` names, which also render into the operator's step.
- `model` — the model handle, when the failure is attributable to one.
- `provider` — what the inference provider answered: its `name` (the backend), `status`, `code`, `request_id` and `message`.
- `migration` — a pending configuration migration that explains the failure.
- `runtime_version` — the version of the Pipelex runtime that built the problem.
- `trace_id`, `span_id` — the OpenTelemetry span the failure happened in, when one was recording.

Every text in a problem that the runtime did not write itself, a message, a provider's answer or a parameter, is cut to a bounded length, keeping its head and ending with ` […]`.

The catch-all, a failure no more specific handler matched, answers `runtime.unexpected` with a **500** in both views: the caller reads that code's sentences, and the operator view reads the exception's class and message in `diagnostics`. A traceback never reaches a response in either view, and neither the traceback nor the exception's text reaches a log: the server's error line names the classes of the exception's chain and the frames it was raised through (see [Logging](logging.md)).

The server's own record of a failure the runtime raised is built from the operator view, whichever view the response carries, so it names the error's class, its code and what the inference provider answered (see [Logging](logging.md)).

## Structured validation errors

When a bundle fails validation, the runtime builds one structured item per fault — the per-error diagnostics an editor maps to per-line problems — and every surface of this server carries them as the MTHDS standard's **problem items**. On the diagnostic routes (`/validate`, `/resolve`, `/codegen`, `/pipe-io`) an invalid bundle is the successful product of the call: a **200 `is_valid: false`** verdict carrying the items as `errors` (see [Pipe Validate](pipe-validate.md)). On the run routes (`/execute`, `/start`), where an invalid bundle means the run cannot proceed, it is a **422** `method.invalid` problem carrying the same items as its `errors`. Built by pipelex's one shared builder, the items name the same faults at the same places wherever they appear, and the same as the agent CLI's. A valid verdict's `warnings` are problem items too, in the same shape.

Each item is one fault:

| Member | Meaning |
|---|---|
| `code` | The registry code of the fault: the code its type maps to, such as `method.input_undeclared` for an input a pipe reads but does not declare, `model.unknown` for a model the deck does not define, `method.syntax` for a TOML syntax error or `method.dependency_missing` for a package the method calls and no one supplied. A `dry_run` item's code is its failure's own, and an item no stage classified takes `method.schema_violation`, or the code of the refusal behind it. |
| `detail` | The code's sentence, rendered from the item's parameters, or the code's title when the item lacks a parameter the sentence names. A program branches on `code`, never on a sentence. |
| `params` | The facts the item's locators give the code, by the registry's names: the `pipe`, the `variables` it reads, the `concept` or `model` it names, the `model_type`, a `finding` quoting the validation's own account. |
| `location` | Where the fault is: the `pipe`, the `field` within the bundle, and the `file` with its 1-based `line` and `column` when the parser stopped there. On the in-memory submit path the `file` is the matching `mthds_sources[i]` (see [Sourcing submitted files](pipe-validate.md)), so it is absent when the caller sent no sources. Beside a server's own library directories, an item never names one of their files, nor a template file one of their `PipeDocGen` steps names. |
| `suggestions` | On a `model.unknown` item, the deck's close matches of the kind the pipe needs. |
| `suggested_fix` | A structured, deterministic fix for this fault — present only when the fix planner derived one. See [Suggested fixes](#suggested-fixes). |

An item writes no member that has no value: an absent member is not `null`.

Every invalid verdict carries a **non-empty** list of items — the structured-info invariant is total. A parse-level failure the runtime cannot attribute to a known pipe, concept or field — an empty blueprint, an elaborator failure — still becomes one residual item carrying the failure as its `finding`, so the list is never empty on an invalid verdict. A TOML syntax error is a `method.syntax` item whose `location` holds the `line` and `column` the parser stopped at, and the `file` when the caller sent one. A failing dry run is one item per failing pipe, located at the innermost pipe that failed. A dry run whose every failure belongs to someone other than the method's author, such as a storage outage, is no verdict about the method: it answers the failure's own code, with every failure riding its `errors`.

On the run routes, **every refusal of the bundle while it loads is this verdict**, and the load happens before any pipe runs: a misspelled concept, a wiring mismatch, an unknown model, a TOML fault or a refusal raised while a pipe is built all answer the same **422** `method.invalid` carrying the same items validating the bundle gives. None of them reaches a run as a `500`. An entry pipe the bundle does not declare answers `request.pipe_not_found`, and a bare code matching pipes in several domains `request.pipe_ambiguous`.

## Suggested fixes

A problem item may carry a `suggested_fix`: a deterministic repair the runtime's fix planner derived from the *typed* error data — never by parsing a message string. It is the MTHDS standard's fix, the same object on a verdict's item and on a problem's. It is optional and additive. An item the planner has no rule for simply omits the member, and a client that ignores `suggested_fix` entirely behaves exactly as before.

```json
{
  "code": "method.output_concept_mismatch",
  "detail": "A pipe's output concept does not fit",
  "params": { "pipe": "summarize_and_translate" },
  "location": { "pipe": "summarize_and_translate", "file": "translate.mthds" },
  "suggested_fix": {
    "fix_code": "match-sequence-output",
    "description": "Set output of pipe 'summarize_and_translate' to 'Translation' to match its last step",
    "safety": "safe",
    "file": "translate.mthds",
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
- `file` — the file the ops target, when known. **An applier must only apply ops to the file they target** — in a multi-file library the ops are meaningless against any other file.
- `ops` — the semantic TOML patch operations, in order.

**Ops** are addressed by `table_path` (the containing table, e.g. `["pipe", "my_seq"]`). Each op's `kind` names its shape: read `kind` off the wire and you know exactly which other fields the op carries, because each kind is its own shape in the OpenAPI artifact rather than one open shape with everything optional. An op whose `kind` is none of those below, which a newer runtime could send, is read as an unknown op that an applier never applies.

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

When a run fails, the problem describes the **root fault**, never the run-level wrapper around it: the first Pipelex error down the cause chain that carries a code of its own, or the innermost one when none does. The wrappers that only locate the failure take their cause's code, so every member is the root fault's — `code`, `type`, `title`, `domain`, `retry`, the HTTP status, the sentences and the parameters — and the wrappers add only where it happened, as the `location` members: `pipe`, the pipe that failed, and `path`, the pipe codes from the entry pipe down to it. A code that declares a `pipe` parameter names the failing pipe in its sentences too. A consumer reads the location from those members, never from a sentence.

So a run the caller's own method or request refuses says what to change: a `PipeCondition` whose outcome is `fail`, a `PipeParallel` branch whose multiplicity does not match its output field, a step started without a required input, or a model named inline that the deck does not define all answer a **422** whose code is the caller's own, in the `input` or the `method` domain, with a step saying what to change. A model the deck names but does not serve is `model.unavailable`, a **501** in the `operator` domain: the caller's step is to choose another model or ask whoever runs the server to serve it, and the operator's to configure a backend for it.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json

{
  "type": "https://mthds.ai/errors/pipe.output_multiplicity",
  "title": "A pipe's output does not have the declared multiplicity",
  "status": 422,
  "detail": "Pipe 'analyze_topic' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'.",
  "code": "pipe.output_multiplicity",
  "domain": "method",
  "retry": "no",
  "next_step": {
    "kind": "change_method",
    "detail": "Declare the output 'ideas' as 'list', or make pipe 'analyze_topic' produce 'single'."
  },
  "params": {
    "pipe": "analyze_topic",
    "output": "ideas",
    "produced": "list",
    "declared": "single"
  },
  "location": {
    "pipe": "analyze_topic",
    "path": ["review_topic", "analyze_topic"]
  },
  "request_id": "9f2c1ab3-…"
}
```

In the operator view the same failure adds `diagnostics`, whose `message` is the combine's own restatement, naming the branch whose result it could not combine and the setting to change. The failure of a `/start` run reaches its completion webhook as the same problem, under the payload's `error` key (see [Async callbacks](#async-callbacks-webhook-payload)).

## Status codes

The HTTP status of a failure the runtime raised is the one its code declares in the registry, the `status` member's value, and each code's page on [Error Codes](../errors/index.md) states it. A code the registries give none, which only a client's own failure has, answers **500**. Two codes of the same domain can answer different statuses, so a client reads `code`, `domain` and `retry`, never the status, to decide what to do. The statuses a run meets most:

- **422** — the caller's request or method: `method.invalid` and the method's other codes, `input.missing` and the input's other codes, `request.pipe_not_found`, `request.pipe_ambiguous`, `model.unknown`, `model.content_refused`.
- **429** — `provider.rate_limited`: an upstream inference provider rate-limited the run, a retry can succeed, and `Retry-After` is set when the provider gave a delay. Only `POST /v1/execute` runs inference, so only `/execute` can produce it.
- **500** — the operator's configuration, such as `pipelex.config.variable_missing` or `pipelex.config.invalid`, and the catch-all `runtime.unexpected`.
- **501** — something this deployment does not serve: `model.unavailable`, a model it serves no backend for; `runtime.unsupported`, async pipeline execution (`POST /v1/start`) on a deployment that does not provide it. Nothing is broken, and a caller meets the refusal each time it asks, so its log line is a warning, never an error (see [Logging](logging.md)).
- **502** — an upstream service failed: `provider.unavailable`, `provider.failed`, `provider.quota_exhausted`, `provider.credential_refused`, `method.fetch_failed`. A **504** is `provider.timeout`.

A few runtime refusals worth knowing by their code:

- **404** — `method.not_found`: the `method_ref` repository was fetched, but no package in it matches the requested address by manifest identity, or it holds no such tag. The problem's sentences name the reference.
- **409** — `pipelex.run.already_exists`: the submitted `pipeline_run_id` is already registered for a run that is still in flight on this server. Completed and failed runs free their id, so this only fires for genuinely concurrent duplicates — resubmit after the in-flight run finishes, or pick a fresh id. Only `POST /v1/start` accepts a client-supplied `pipeline_run_id`, so only `/start` can produce it.
- **422** — the `method_ref` resolution refusals the caller can fix: `request.invalid` for a reference that does not parse, `method.ambiguous`, and `method.package_invalid` for a package past its limits or carrying a symbolic link. `pipelex.deployment.python_structures_refused` is a **422** too: a method, fetched by `method_ref` or sent as a tree, declares in-process Python structure classes (`StructuredContent` subclasses), which hosted execution always refuses, sandbox or not — express the types as MTHDS concepts with inline structures instead (see [Pipe Run](pipe-run.md#running-a-method-by-address-method_ref)).

The runner's own refusals answer these codes:

- **401** — `auth.missing_credential` for a request carrying no bearer token, `auth.invalid_credential` for a token the runner refuses, and `auth.credential_expired` for an expired one, each with `WWW-Authenticate: Bearer` set. Only reachable when the deployment enables auth (`AUTH_MODE=api_key` or `AUTH_MODE=jwt`), or trusts a proxy, which then answers `auth.missing_credential` when it forwarded no identity, with no `WWW-Authenticate`, since that deployment reads no bearer token. A forwarded `X-User-Id` that is not a single path-safe segment is no credential of the caller's: it is a **422** `request.invalid` naming the field `X-User-Id`.
- **403** — `auth.forbidden`, whose `requirement` names what the request lacks: `signed_upload_target` for a `PUT /v1/blobs/{sha256}` without a valid upload target, its signature missing, forged, expired, or signed for another hash or scope, so ask `POST /v1/blobs/missing` for a fresh target; `read_scope_under_caller` on a `jwt` deployment, for a request that sent a `read_scope` not lying under the caller's own `user_id`, which is the only scope its token may read (see [Pipe Run](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups)).
- **404** — `request.not_found`: no route serves the request's path.
- **405** — `request.method_not_allowed`: the route does not accept the request's HTTP method. The response carries the `Allow` header listing the methods it accepts.
- **413** — `request.too_large`: the request body exceeds the configured size limit (`MAX_REQUEST_BODY_MIB`, 100 MiB by default), or a part of it exceeds its own: an encoded `bundle_b64` archive over `MAX_BUNDLE_TOTAL_KIB`, a file in `resources` over `MAX_RESOURCE_FILE_KIB`, the files in `resources` over `MAX_RESOURCES_TOTAL_KIB`, or a blob upload over the per-file tree limit.
- **422** — `request.invalid` for a field the route's rules refuse, `request.malformed` for a body or an encoded part that cannot be parsed, `request.unsupported` for a **registry-form** `method_ref` — not a `github.com/...` address — which no server-side method registry resolves yet (its `reason` is `registry_form_method_ref`; use an address or send the method's tree in `files`), and `pipelex.deployment.orchestration_override_forbidden`, naming the `requested_mode`, for a request asking for an `orchestration_mode` this deployment does not allow overriding per request (`allow_request_orchestration_mode_override = false`).
- **500** — `runtime.misconfigured`: the runner's own configuration cannot serve the request, such as a missing `API_KEY` or `JWT_SECRET_KEY`, a `PUBLIC_BASE_URL` that is not an HTTP URL, or missing package metadata. Which setting is at fault is the operator's to read, in `diagnostics.params.component`, and in the `error.params.component` of the server's error line whichever view the response took. `pipelex.deployment.token_claims_invalid` is a **500** too: a token whose signature holds carries a `user_id` claim that is missing, unsafe or reserved, which its issuer, not its bearer, must fix.
- **501** — `runtime.unsupported` naming the `capability` `asynchronous execution`: `POST /v1/start` is fire-and-forget by nature, and this deployment's orchestrator is blocking-only (the in-process `direct` default), so it refuses honestly rather than blocking and acking — use `POST /v1/execute` instead. `pipelex.deployment.custom_code_requires_sandbox`: the method holds custom Python `.py` files and this deployment is not sandbox-hosted, so running caller-supplied code in-process is refused; its `origin` says whether the code came in the request's `bundle` or a fetched `package`.
- **500** — `pipelex.storage.damaged`, naming the kind of storage as `scheme`, on the routes that read files a request names by hash (`POST /v1/execute`, `POST /v1/start`, `POST /v1/validate`, `POST /v1/resolve`, `POST /v1/codegen` and `POST /v1/pipe-io`): the bytes the blob store holds under a hash do not hash to it, or are not the size it holds them at, so the object stored there is damaged. `PUT /v1/blobs/{sha256}` answers it too for an upload whose bytes hash to an object held at another size, since the runner never writes over a blob. Its verdict is not to retry, since a retry reads the same damaged object, and its step is to report it: the operator removes the object the server's line `Stored blob bytes do not match their hash` names under `blob_sha256` (see [Logging](logging.md#blob-store-lines)), after which the blob is uploaded again.

A client that disconnects before its request body was received in full is answered `request.malformed` with the reason `body_incomplete`, which only the server's logs show, at warning level, since the client is gone before the answer.

Every route that takes a JSON body refuses one whose arrays and objects nest more than 128 levels deep, the body's own envelope included, with a **422** `request.malformed` whose `reason` is `too_deeply_nested`. The depth is checked before the body is parsed, so the answer does not depend on the Python version or the stack size the server runs with. The bound is fixed rather than configurable, and real inputs stay far below it.

The run routes read their body as plain JSON before anything else, and the routes that declare a typed body parse it before validating it, so the same refusals come from that step, all **422**. A body that is not valid UTF-8 or not valid JSON answers `request.malformed` with the reason `not_utf8` or `not_json`, and one holding an integer longer than Python reads from text (`sys.get_int_max_str_digits()`, 4,300 digits by default) the reason `integer_too_long`; and one that is not a JSON object `request.invalid` naming the field `body`. A body carrying, in any object at any depth, a key named `__class__` or `__module__`, or a key starting with `__kajson`, answers `pipelex.security.reserved_key`, whose `keys` parameter names the key, cut short when it is long. Those are the keys a kajson decoder reads as an order to import and instantiate a class, so the runner refuses them rather than carry them as data, and logs the refusal's security event. Only keys are checked: a string value that mentions `__class__` is accepted.

A pipe selection the server cannot make is an input **422** named for its failure: `request.pipe_not_found` when the selector names no pipe, and `request.pipe_ambiguous` when a bare code matches pipes in several domains. The run routes answer an unknown or ambiguous `pipe_code` that way. `POST /v1/pipe-io` answers every selection refusal that way, counting a request with no `pipe_ref` over a method that declares no `main_pipe`, or whose domains declare several, as `request.pipe_unspecified`, which names the declared ones as its `candidates`, and a manifest `main_pipe` the method lacks or declares in several domains as the method's own `method.pipe_unresolved` or `method.ref_ambiguous` (see [Pipe I/O](pipe-io.md#pipe-selection)).

The run routes' extension fields are validated before any method is fetched or any library loaded, and a failure there is a **422** `request.invalid` naming the field that failed, `callback_urls`, `storage_scope`, `read_scope` or `analytics_groups`, or a path into it (see [Pipe Run](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups)). A storage scope that does not lie under the run's read scope, whether either was sent or defaulted, names `read_scope`. A body failing on several fields at once carries one item per refused field in `errors`. A callback URL whose scheme is not `http` or `https`, or whose host the SSRF rules refuse, is the security refusal `security.input_url_refused`, which logs its security event and names the class of destination it refused, never the URL. `POST /v1/validate` takes `analytics_groups` too and refuses it the same way.

A method sent as a tree, in `files` or `bundle_b64`, is read under the MTHDS standard's tree rule before anything loads, on the run routes and `/validate` alike (see [Pipe Run](pipe-run.md#sending-a-method-as-a-tree)). A key or an entry the rule refuses, two shipped packages a reference could not tell apart, or a tree past `MAX_METHOD_TREE_FILES`, `MAX_METHOD_TREE_FILE_KIB` or `MAX_METHOD_TREE_TOTAL_KIB`, or a method past `MAX_METHOD_DEPENDENCIES` or `MAX_METHOD_REQUEST_TOTAL_KIB` across its trees, is a **422** `method.package_invalid` whose `reason` names the rule: the standard's tree refusal codes, such as `invalid_tree_path`, `duplicate_key`, `excluded_name` or `path_collision`, with the `path` it refuses, or the runner's own, one per rule and one per limit: `too_many_files`, `file_too_large` and `tree_too_large` for a tree, `too_many_dependencies` and `method_too_large` for a request's trees together, `bundle_too_many_files` and `bundle_too_large` for a `bundle_b64` archive, `manifest_missing`, `manifest_invalid`, `package_name_invalid`, `dependency_address_collision` and `no_bundle`, with the `path` or the `limit` it names. A key that is not a tree path without leaving the tree, empty or holding a backslash or a colon, is `invalid_tree_path`. A path of the tree that would leave its root is the security refusal `security.input_path_refused`, naming the `rule` it broke, `absolute` or `parent_segment`, never the path. A malformed entry, or `dependencies` that do not fit the request, is a **422** `request.invalid` naming the field. A hash entry this runner does not hold is a **422** `request.blobs_missing` whose `missing_blobs` parameter lists the SHA-256 hashes to upload through the blob routes before sending the request again, and one it holds at another size than the entry states a **422** `request.invalid`: the entry's size is the one to correct, since uploading the bytes again would not change the size they are held at. The blob routes answer in the same vocabulary: a body whose SHA-256 is not the one its path names is a **422** `request.invalid` naming the field `body`, one hash listed with two sizes a **422** `request.invalid` naming `blobs`, and a blob past the per-file limit a **413** `request.too_large`. None of them invites a retry, since the same request is refused again.

The files a request sends in `resources` are checked before the bundle loads and again once it is parsed (see [Pipe Validate](pipe-validate.md#sending-the-files-the-steps-read-resources)). A key that would leave the bundle is the security refusal `security.input_path_refused`, naming the `rule` it broke; any other key that cannot name a file inside the bundle, two keys naming the same file, more files than `MAX_RESOURCES_PER_REQUEST`, a file none of the bundle's steps names, and files that cannot make one method tree, such as two keys equal once case-folded, are **422** `request.invalid` naming the field `resources`; and a value that is not base64 is a **422** `request.malformed` with the reason `bad_base64`. They answer the same on every route, the diagnostic ones included: they are the request's fault, not the bundle's.

The HTTP status is the source of truth for success vs failure — there is no `success: true/false` field anywhere in the envelope.

Which statuses a given route can actually produce is documented per operation in the [committed OpenAPI artifact](openapi/pipelex-api.openapi.yaml), each as an `application/problem+json` `ProblemDocument`.

**What is *not* an error status:** an invalid `.mthds` bundle. On the diagnostic routes — `/validate`, `/resolve`, `/codegen`, and `/pipe-io` — a bundle that fails validation is the *successful product* of the call, so it rides a **200** discriminated on `is_valid: false`, carrying the same `errors[]` items described above. Non-2xx on those routes is reserved for *no verdict could be produced*. See [Pipe Validate](pipe-validate.md).

## The `type` URI

`type` is the page of the error's `code`:

```
https://mthds.ai/errors/<code>              a code of the MTHDS standard, such as method.invalid
https://docs.pipelex.com/errors/<code>      a pipelex. code, such as pipelex.config.variable_missing
```

Both families are listed on the [Error Codes](../errors/index.md) page, and `title` is the code's title. A Pipelex code's type URI names no documentation version: the documentation site answers it with the code's page in the latest release (see [The pages and the type URI](../contribute/error-registry.md#the-pages-and-the-type-uri)).

The runner's own refusals carry a code like every other error, so their `type` is their code's page too.

Before every error carried its code, the `type` of an error was derived from its class or, for a refusal the API authored, from its `error_type`, and named a page per class. Those pages are retired, and the documentation site redirects each one to the page of its class's code, or to the Error Codes index when the class is gone or raises no single code, so a stored `type` still leads somewhere useful.

## Request correlation

Every response carries `X-Request-ID`. The middleware respects an inbound `X-Request-ID` header if present and valid, otherwise mints one, a ULID. A valid id is 1 to 128 ASCII letters, digits, `_` and `-`, the rule a run applies to the id it is handed too (`pipelex.system.job_metadata.is_valid_request_id`): the id is echoed in a header and written into log lines, where a space, a quote or an `=` could forge a field. It also binds that id onto the Pipelex runtime's log context for the duration of the request, so every record emitted underneath carries it as a `request_id` field — the server's own error lines and the runtime's lines from inside a run alike. Both run routes, `POST /v1/execute` and `POST /v1/start`, also put the id on the run's metadata, so when a run is dispatched to a worker, the lines the worker writes while it runs the run's workflow and activities carry the same id. What those lines look like, which fields they carry and where the id does not reach are in [Logging](logging.md).

When opening an issue, include the `request_id` from the response (or response headers) and the timestamp.

## Examples

### 422 — a method that does not validate

```http
POST /v1/execute
{
  "mthds_contents": ["domain = \"summaries\"\nmain_pipe = \"summarize\"\n\n[pipe.summarize]\ntype = \"PipeLLM\"\ndescription = \"Summarize a text\"\ninputs = { text = \"Text\" }\noutput = \"Text\"\nprompt = \"Summarize $text in the style of $tone.\"\n"],
  "mthds_sources": ["summaries.mthds"]
}
```

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://mthds.ai/errors/method.invalid",
  "title": "The method does not validate",
  "status": 422,
  "detail": "The method does not validate.",
  "code": "method.invalid",
  "domain": "method",
  "retry": "no",
  "next_step": {
    "kind": "change_method",
    "detail": "Fix each fault the problem's errors list, then validate the method again."
  },
  "errors": [
    {
      "code": "method.input_undeclared",
      "detail": "Pipe 'summarize' reads names its inputs do not declare: tone.",
      "params": { "pipe": "summarize", "variables": ["tone"] },
      "location": { "pipe": "summarize", "file": "summaries.mthds" }
    }
  ],
  "request_id": "9f2c1ab3-…"
}
```

The `detail` is the human summary; `errors` is the machine-readable list a client maps to per-line diagnostics. Only the run routes answer an invalid bundle with this 422 — on the diagnostic routes the same bundle is a **200 `is_valid: false`** verdict carrying the same items as `errors` — see [Structured validation errors](#structured-validation-errors) and [Sourcing submitted files](pipe-validate.md).

### 500 — deployment configuration fault

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://docs.pipelex.com/errors/pipelex.config.variable_missing",
  "title": "A configuration variable is not set",
  "status": 500,
  "detail": "A variable the runtime's configuration refers to is not set.",
  "code": "pipelex.config.variable_missing",
  "domain": "operator",
  "retry": "no",
  "next_step": {
    "kind": "report",
    "detail": "Report this to whoever runs the runtime."
  },
  "request_id": "9f2c1ab3-…"
}
```

`pipelex.config.variable_missing` is a code in the `operator` domain: the deployment, not the caller, has to fix it, so the caller's step is to report it. The operator view of the same failure carries the `fix_configuration` step and `diagnostics`, whose `message` names the variable, `Missing required environment variable: COMPLETION_CALLBACK_SECRET`, which no caller reads.

### 401 — missing bearer token

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: Bearer
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://mthds.ai/errors/auth.missing_credential",
  "title": "No credential was sent",
  "status": 401,
  "detail": "This route needs a credential, and the request carried none.",
  "code": "auth.missing_credential",
  "domain": "account",
  "retry": "no",
  "next_step": {
    "kind": "check_credentials",
    "detail": "Send the request with a credential this runtime accepts."
  },
  "request_id": "9f2c1ab3-…"
}
```

### 422 — two fields the route refuses

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
X-Request-ID: 9f2c1ab3-…

{
  "type": "https://mthds.ai/errors/request.invalid",
  "title": "The request does not match the route's schema",
  "status": 422,
  "detail": "The request's field 'storage_scope' does not match the route's schema.",
  "code": "request.invalid",
  "domain": "input",
  "retry": "no",
  "next_step": {
    "kind": "change_input",
    "detail": "Correct the field 'storage_scope' as the route's schema requires, then send the request again."
  },
  "params": { "field": "storage_scope" },
  "location": { "field": "storage_scope" },
  "errors": [
    {
      "code": "request.invalid",
      "detail": "The request's field 'storage_scope' does not match the route's schema.",
      "params": { "field": "storage_scope" },
      "location": { "field": "storage_scope" }
    },
    {
      "code": "request.invalid",
      "detail": "The request's field 'analytics_groups' does not match the route's schema.",
      "params": { "field": "analytics_groups" },
      "location": { "field": "analytics_groups" }
    }
  ],
  "request_id": "9f2c1ab3-…"
}
```

The operator view of the same refusal adds `diagnostics`, whose `message` holds the rules each field broke, in the request model's own words, which can quote what the caller sent and so never reach a caller.

## Async callbacks (webhook payload)

For [async pipeline runs](pipe-run.md) registering a `callback_url`, the payload delivered to the caller's webhook **does not** use this envelope: it is a completion notice carrying `pipeline_run_id`, the delivery `state` (also sent under the legacy `status` key) and, when results were stored, `result_url`. A failed run adds its problem under an `error` key, so a non-HTTP receiver such as a queue or a log shipper reads the same `code`, `domain`, `retry`, sentences and `location` as the synchronous answer, without an HTTP status.

The problem rides in the view of whoever started the run, as the request that started it authenticated them: a `/start` request carrying the operator's credential, or forwarded by the trusted proxy, has its webhooks carry the operator view, `diagnostics` included, and any other request the caller view. A host that builds its own webhook targets picks the view with `WebhookTarget.problem_view`, which is the caller view when it names none. See [Pipe Run → Async Completion Callbacks](pipe-run.md) for the full webhook contract.
