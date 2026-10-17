# Error Responses

Every error returned by the API is an RFC 9457 `application/problem+json` document. A failure the Pipelex runtime raised, which is every domain error, every run failure and the catch-all, answers its **problem document**, named by a registry code and seen through the view the request's identity gives it. A refusal the API authors itself, such as a malformed body, a missing token or a payload over its limit, answers a problem document of its own, classified by an `error_type`.

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

### API-authored errors

A refusal the API authors itself, before the runtime is asked anything, carries no `code` yet. It keeps the classification members it had before the problem document, beside the RFC's `type`, `title`, `status` and `detail`:

- `error_type` — the refusal's name, such as `ValidationError`, `InvalidJSON`, `Unauthenticated` or `PayloadTooLarge`, the member to branch on. See [Status codes](#status-codes).
- `error_domain` — `input` for a refusal the caller can fix, `config` for one the deployment must.
- `retryable` — always present, and `false`: every such refusal is a request to correct or a deployment to fix.
- `instance` — the request's path.
- `request_id` — as above.
- `tree_refusal` — on a **422** `InvalidMethodFiles`, the MTHDS standard's refusal of a method tree the request sent: `{"code": "<refusal code>", "names": [...]}`, the code one of the standard's tree refusal codes, such as `invalid_tree_path`, `duplicate_key`, `excluded_name` or `malformed_entry`, and `names` the keys, paths or addresses it refuses. A name holding a code point UTF-8 cannot encode, such as a lone surrogate a JSON escape can carry, is written with that code point backslash-escaped. See [Pipe Run](pipe-run.md#sending-a-method-as-a-tree).
- `missing_blobs` — on a **422** `MissingBlobs`, the SHA-256 hashes the request named by hash entries that this runner does not hold at their stated size, to upload through the blob routes before sending the request again. See [Sending files by hash](pipe-run.md#sending-files-by-hash).
- `mismatched_blobs` — on a **422** `BlobMismatch` refusing a request's hash entries, each hash this runner holds at another size than its entry states, as `{"sha256": "…", "held_size": n}`: the entry's size is the one to correct, since uploading the bytes again would not change the size they are held at.

Its `detail` is the API's own sentence about what it checked, and it reads the same in every view.

## Views chosen by identity

A failure the runtime raised is one problem seen through a view, and the identity the request authenticated picks the view. No deployment setting picks it.

| How the request authenticated | View |
|-------------------------------|------|
| `AUTH_MODE=api_key`: the static API key is the operator's own credential | The operator view |
| `AUTH_MODE=none` with `TRUST_FORWARDED_IDENTITY_HEADERS=true`: the only party reaching this server is the trusted proxy in front of it, such as the hosted platform, which owes its own callers their caller view | The operator view |
| `AUTH_MODE=jwt`: a caller's token | The caller view |
| `AUTH_MODE=none` without the trusted proxy, or a request refused before any authentication ran | The caller view |

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

The catch-all, a failure no more specific handler matched, answers `runtime.unexpected` with a **500** in both views: the caller reads that code's sentences, and the operator reads the exception's class and message in `diagnostics`. A traceback never reaches a response in either view.

The server's own record of a failure the runtime raised is built from the operator view, whichever view the response carries, so it names the error's class, its code and what the inference provider answered (see [Logging](logging.md)).

## Structured validation errors

When a bundle fails validation, the runtime builds one structured item per fault — the per-error diagnostics an editor maps to per-line problems — and where they surface depends on the endpoint. On the diagnostic routes (`/validate`, `/resolve`, `/codegen`, `/pipe-io`) an invalid bundle is the successful product of the call: a **200 `is_valid: false`** verdict carrying the items whole as `validation_errors` (see [Pipe Validate](pipe-validate.md)). On the run routes (`/execute`, `/start`), where an invalid bundle means the run cannot proceed, it is a **422** `method.invalid` problem carrying the same items as its `errors`, each with its own code. Built by pipelex's one shared builder, the items name the same faults at the same places wherever they appear, and the same as the agent CLI's.

Each `validation_errors` item of a verdict is one categorized validation failure:

| Field | Meaning |
|---|---|
| `category` | The failure family — one of `blueprint_validation`, `pipe_factory`, `pipe_validation`, `dry_run`. |
| `message` | Human-readable description of this specific error. On a `dry_run` item it names the pipe, then the sentence the failure's code renders for a caller, never the failure's own text. |
| `error_type` | Finer error subtype within the category, when the source error provides one. |
| `source` | The owning file of the error, when the runtime could attribute it to one: on `blueprint_validation` and `pipe_validation` items, and on a `dry_run` item, where it is the file of the pipe whose dry run failed. On the in-memory submit path it is the matching `mthds_sources[i]` (see [Sourcing submitted files](pipe-validate.md)), so it is absent when the caller sent no sources. Absent on `pipe_factory` items and on the parse-level residual described below. Beside a server's own library directories, an item never names one of their files, nor a template file one of their `PipeDocGen` steps names. |
| `pipe_code`, `concept_code`, `domain_code` | The pipe / concept / domain the error is about, when applicable. On a `dry_run` item they name the innermost pipe that failed, not the controller the failure passed through. |
| `field_path`, `field_name` | The offending field within the bundle, when the error localizes to one. |
| `variable_names`, `missing_concept_code`, `missing_pipe_code`, `declared_concepts` | Extra context for specific failure shapes (undefined variables, an unresolved concept, pipe or package reference, the set of concepts that were declared). On an `unresolved_package_dependency` item, `missing_pipe_code` is the reference as written, `<address>->domain.code`, so the package's address is the part before `->`. |
| `line`, `column` | The 1-based position where the TOML parser stopped, on a TOML syntax error. |
| `model_reference`, `model_type`, `suggestions` | On an `unknown_model` item — a pipe naming a model the deployment's model deck does not define — the reference as the bundle wrote it, the kind of model the pipe needs (`llm`, `extract`, …), and the deck's close matches of that kind. With exactly one suggestion the item also carries an `unsafe` `suggested_fix` renaming the model. On an `llm_setting_refused_by_model` item — a `PipeLLM` or `PipeStructure` whose model setting the model it resolves to refuses, which its worker would refuse at the first call — `field_name` and `field_path` name the `model` or `model_to_structure` field holding the setting, and `model_reference` is the preset, alias or model that field names, absent when it writes the setting inline or the pipe leaves it to the deck's override or default. |
| `template_file`, `template_location` | On a `template_check_warning` item, which rides the valid verdict's `warnings` rather than `validation_errors`, the template file as the `PipeDocGen` step names it and the place in it the engine's finding names, in the engine's own words (a defined name, a Table, a cell, a shape, a tag); `template_location` is absent when the engine names no place. A step of the server's own library directories is named by its `pipe_code` and `domain_code` alone: its item carries no `template_file`, and its message reads `<host library file>` where it named the file. |
| `suggested_fix` | A structured, deterministic fix for this error — present only when the fix planner derived one. See [Suggested fixes](#suggested-fixes). |

Items carry only the fields that apply to their category — absent fields are omitted, not null.

On a `422` problem, each item becomes one `errors` entry: its `code` is the code its `error_type` maps to (`method.input_undeclared` for a `missing_input_variable`, `model.unknown` for an `unknown_model`), a `dry_run` item's is its failure's own, and an item no stage classified takes `method.schema_violation` or the code of the refusal behind it; its `detail` is that code's sentence and its `params` the facts the item's locators give it; its `location` holds the item's `pipe`, `field`, `file`, `line` and `column`; and it keeps the item's `suggestions` and `suggested_fix`.

Every invalid verdict carries a **non-empty** list of items — the structured-info invariant is total. A parse-level failure the runtime cannot attribute to a known pipe/concept/field — an empty blueprint, an elaborator failure — still becomes one `blueprint_validation` residual item carrying the failure message (no `source`, no `error_type` at this layer), so the list is never empty on an invalid verdict. A TOML syntax error is an item of the same category without an `error_type`, which carries the `line` and `column` the parser stopped at and the `source` when the caller sent one. A failing dry run is one `dry_run` item per failing pipe, located at the innermost pipe that failed. A dry run whose every failure belongs to someone other than the method's author, such as a storage outage, is no verdict about the method: it answers the failure's own code, with every failure riding its `errors`.

On the run routes, **every refusal of the bundle while it loads is this verdict**, and the load happens before any pipe runs: a misspelled concept, a wiring mismatch, an unknown model, a TOML fault or a refusal raised while a pipe is built all answer the same **422** `method.invalid` carrying the same items validating the bundle gives. None of them reaches a run as a `500`. An entry pipe the bundle does not declare answers `request.pipe_not_found`, and a bare code matching pipes in several domains `request.pipe_ambiguous`.

## Suggested fixes

A validation error item may carry a `suggested_fix`: a deterministic repair the runtime's fix planner derived from the *typed* error data — never by parsing a message string. It rides a verdict's `validation_errors` item and a problem's `errors` item as the same object. It is optional and additive. An item the planner has no rule for simply omits the field, and a client that ignores `suggested_fix` entirely behaves exactly as before.

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
- **501** — something this deployment does not serve: `model.unavailable`, a model it serves no backend for; `runtime.unsupported`, async pipeline execution (`POST /v1/start`) on a deployment that does not provide it.
- **502** — an upstream service failed: `provider.unavailable`, `provider.failed`, `provider.quota_exhausted`, `provider.credential_refused`, `method.fetch_failed`. A **504** is `provider.timeout`.

A few runtime refusals worth knowing by their code:

- **404** — `method.not_found`: the `method_ref` repository was fetched, but no package in it matches the requested address by manifest identity, or it holds no such tag. The problem's sentences name the reference.
- **409** — `pipelex.run.already_exists`: the submitted `pipeline_run_id` is already registered for a run that is still in flight on this server. Completed and failed runs free their id, so this only fires for genuinely concurrent duplicates — resubmit after the in-flight run finishes, or pick a fresh id. Only `POST /v1/start` accepts a client-supplied `pipeline_run_id`, so only `/start` can produce it.
- **422** — the `method_ref` resolution refusals the caller can fix: `request.invalid` for a reference that does not parse, `method.ambiguous`, and `method.package_invalid` for a package past its limits or carrying a symbolic link. `pipelex.deployment.python_structures_refused` is a **422** too: a method, fetched by `method_ref` or sent as a tree, declares in-process Python structure classes (`StructuredContent` subclasses), which hosted execution always refuses, sandbox or not — express the types as MTHDS concepts with inline structures instead (see [Pipe Run](pipe-run.md#running-a-method-by-address-method_ref)).

The API's own refusals, which carry an `error_type` and no code, answer these statuses:

- **400** — `StartRequiresAsyncOrchestration`: `POST /v1/start` is fire-and-forget by nature, and this deployment's orchestrator is blocking-only (the in-process `direct` default), so it refuses honestly rather than blocking and acking — use `POST /v1/execute` instead. `BadRequest`: the client disconnected before its request body was received in full, which only the server's logs show, at warning level, since the client is gone before the answer; or a forwarded `X-User-Id` is not a single path-safe segment.
- **401** — `Unauthenticated`, `InvalidToken` or `TokenExpired`: a missing, invalid or expired bearer token, with `WWW-Authenticate: Bearer` set. Only reachable when the deployment enables auth (`AUTH_MODE=api_key` or `AUTH_MODE=jwt`), or trusts a proxy that forwarded no identity.
- **403** — `OrchestrationModeOverrideForbidden`: the request asked for an `orchestration_mode` this deployment does not allow overriding per request (`allow_request_orchestration_mode_override = false`). `BlobUploadNotAuthorized`: a `PUT /v1/blobs/{sha256}` without a valid upload target, its signature missing, forged, expired, or signed for another hash or scope, so ask `POST /v1/blobs/missing` for a fresh target. `CustomCodeRequiresSandbox`: the method (a tree sent with the request, or a fetched `method_ref` package) holds custom Python `.py` files and this deployment is not sandbox-hosted, so running caller-supplied code in-process is refused.
- **413** — `PayloadTooLarge`: the request body exceeds the configured size limit (`MAX_REQUEST_BODY_MIB`, 100 MiB by default), or a part of it exceeds its own: a `bundle_b64` archive over `MAX_BUNDLE_FILES` or `MAX_BUNDLE_TOTAL_KIB`, or `resources` over `MAX_RESOURCES_PER_REQUEST`, `MAX_RESOURCE_FILE_KIB` or `MAX_RESOURCES_TOTAL_KIB`.
- **501** — `MethodRefNotSupported`: the request selected its closure by a **registry-form** `method_ref` — not a `github.com/...` address — and no server-side method registry resolves those yet. Address-form references are fetched and resolved server-side (see [Pipe Run](pipe-run.md#running-a-method-by-address-method_ref)); use one of those, or submit inline `files[]`. It is permanent under the current deployment — do not retry.

Every route that takes a JSON body refuses one whose arrays and objects nest more than 128 levels deep, the body's own envelope included, with a **422** `InvalidJSON` whose `detail` says the body is nested too deeply. The depth is checked before the body is parsed, so the answer does not depend on the Python version or the stack size the server runs with. The bound is fixed rather than configurable, and real inputs stay far below it.

The run routes read their body as plain JSON before anything else, and two refusals come from that step, both **422**. A body that is not valid UTF-8, not valid JSON, nested too deeply, or not a JSON object answers `InvalidJSON`. A body carrying, in any object at any depth, a key named `__class__` or `__module__`, or a key starting with `__kajson`, answers `ReservedObjectKey`, and the `detail` names the key, cut short when it is long. Those are the keys a kajson decoder reads as an order to import and instantiate a class, so the runner refuses them rather than carry them as data. Only keys are checked: a string value that mentions `__class__` is accepted.

A pipe selection the server cannot make is an input **422** named for its failure: `request.pipe_not_found` when the selector names no pipe, and `request.pipe_ambiguous` when a bare code matches pipes in several domains. The run routes answer an unknown or ambiguous `pipe_code` that way. `POST /v1/pipe-io` answers every selection refusal that way, counting a request with no `pipe_ref` over a method that declares no `main_pipe` as `request.pipe_unspecified` and one over a method whose domains declare several as `request.pipe_ambiguous` (see [Pipe I/O](pipe-io.md#pipe-selection)).

The run routes' extension fields are validated before any method is fetched or any library loaded, and a failure there is a **422** whose `error_type` names the field that failed: `InvalidCallbackUrls` for `callback_urls`, `InvalidStorageScope` for `storage_scope`, `InvalidReadScope` for `read_scope`, `InvalidAnalyticsGroups` for `analytics_groups` (see [Pipe Run](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups)). A storage scope that does not lie under the run's read scope, whether either was sent or defaulted, is an `InvalidReadScope` as well. A failure on another extension field, or on more than one at once, carries the generic `ValidationError`, and the `detail` names every field that failed. `POST /v1/validate` takes `analytics_groups` too and classifies it the same way: a body failing on that field alone answers `InvalidAnalyticsGroups`, and one failing on it and another field answers `ValidationError`.

A method sent as a tree, in `files` or `bundle_b64`, is read under the MTHDS standard's tree rule before anything loads, on the run routes and `/validate` alike (see [Pipe Run](pipe-run.md#sending-a-method-as-a-tree)). A key or an entry the rule refuses, two shipped packages a reference could not tell apart, or `dependencies` that do not fit the request is a **422** `InvalidMethodFiles` carrying `tree_refusal` when the standard's reader refused it; a hash entry this runner does not hold is a **422** `MissingBlobs` carrying `missing_blobs`, and one it holds at another size than the entry states a **422** `BlobMismatch` carrying `mismatched_blobs`; a tree past `MAX_METHOD_TREE_FILES`, `MAX_METHOD_TREE_FILE_KIB` or `MAX_METHOD_TREE_TOTAL_KIB`, or a method past `MAX_METHOD_DEPENDENCIES` or `MAX_METHOD_REQUEST_TOTAL_KIB` across its trees, is a **422** `MethodTreeTooLarge`. The blob routes answer in the same vocabulary: a body whose SHA-256 is not the one its path names, or one hash listed with two sizes, is a **422** `BlobMismatch`, and a blob past the per-file limit a **422** `MethodTreeTooLarge`. Every one of these carries `retryable: false`. Bytes the blob store holds under a hash that do not hash to it are a **500** `BlobStoreCorrupted`: the deployment's storage is damaged, and its operator removes the object for the blob to be uploaded again.

The files a request sends in `resources` are checked before the bundle loads and again once it is parsed (see [Pipe Validate](pipe-validate.md#sending-the-files-the-steps-read-resources)). A key that cannot name a file inside the bundle is a **422** `InvalidResourcePath` and a value that is not base64 a **400** `InvalidBase64`, both the API's own refusals; a file none of the bundle's steps names, and files that cannot make one method tree, such as two keys equal once case-folded, are **422** problems with the code `request.invalid`, or `security.input_path_refused` for a path the tree rule refuses, on every route, the diagnostic ones included: they are the request's fault, not the bundle's, and none invites a retry, since the same request is refused again.

The HTTP status is the source of truth for success vs failure — there is no `success: true/false` field anywhere in the envelope.

Which statuses a given route can actually produce is documented per operation in the [committed OpenAPI artifact](openapi/pipelex-api.openapi.yaml), each as an `application/problem+json` `ProblemDocument`.

**What is *not* an error status:** an invalid `.mthds` bundle. On the diagnostic routes — `/validate`, `/resolve`, `/codegen`, and `/pipe-io` — a bundle that fails validation is the *successful product* of the call, so it rides a **200** discriminated on `is_valid: false`, carrying the same `validation_errors[]` described above. Non-2xx on those routes is reserved for *no verdict could be produced*. See [Pipe Validate](pipe-validate.md).

## The `type` URI

`type` is the page of the error's `code`:

```
https://mthds.ai/errors/<code>              a code of the MTHDS standard, such as method.invalid
https://docs.pipelex.com/errors/<code>      a pipelex. code, such as pipelex.config.variable_missing
```

Both families are listed on the [Error Codes](../errors/index.md) page, and `title` is the code's title. A Pipelex code's type URI names no documentation version: the documentation site answers it with the code's page in the latest release (see [The pages and the type URI](../contribute/error-registry.md#the-pages-and-the-type-uri)).

API-authored errors (`ValidationError`, `BadRequest`, `Unauthenticated`, etc.) carry no code, and their `type` is still derived from their name, `https://docs.pipelex.com/latest/errors/<kebab-name>/`, a URL the documentation site sends to the Error Codes index.

Before every error carried its code, the `type` of an error the runtime raised was derived from its class in the same way and named a page per class. Those pages are retired, and the documentation site redirects each one to the page of its class's code, or to the Error Codes index when the class is gone or raises no single code, so a stored `type` still leads somewhere useful.

## Request correlation

Every response carries `X-Request-ID`. The middleware respects an inbound `X-Request-ID` header if present, otherwise mints one. It also binds that id onto the Pipelex runtime's log context for the duration of the request, so every record emitted underneath carries it as a `request_id` field — the server's own error lines and the runtime's lines from inside a run alike. Both run routes, `POST /v1/execute` and `POST /v1/start`, also put the id on the run's metadata, so when a run is dispatched to a worker, the lines the worker writes while it runs the run's workflow and activities carry the same id. What those lines look like, which fields they carry and where the id does not reach are in [Logging](logging.md).

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

The `detail` is the human summary; `errors` is the machine-readable list a client maps to per-line diagnostics. Only the run routes answer an invalid bundle with this 422 — on the diagnostic routes the same bundle is a **200 `is_valid: false`** verdict carrying the items whole as `validation_errors` — see [Structured validation errors](#structured-validation-errors) and [Sourcing submitted files](pipe-validate.md).

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
  "type": "https://docs.pipelex.com/latest/errors/unauthenticated/",
  "title": "Unauthenticated",
  "status": 401,
  "detail": "Missing bearer token.",
  "instance": "/v1/execute",
  "request_id": "9f2c1ab3-…",
  "error_type": "Unauthenticated",
  "error_domain": "input",
  "retryable": false
}
```

## Async callbacks (webhook payload)

For [async pipeline runs](pipe-run.md) registering a `callback_url`, the payload delivered to the caller's webhook **does not** use this envelope: it is a completion notice carrying `pipeline_run_id`, the delivery `state` (also sent under the legacy `status` key) and, when results were stored, `result_url`. A failed run adds its problem under an `error` key, so a non-HTTP receiver such as a queue or a log shipper reads the same `code`, `domain`, `retry`, sentences and `location` as the synchronous answer, without an HTTP status.

The problem rides in the view of whoever started the run, as the request that started it authenticated them: a `/start` request carrying the operator's credential, or forwarded by the trusted proxy, has its webhooks carry the operator view, `diagnostics` included, and any other request the caller view. A host that builds its own webhook targets picks the view with `WebhookTarget.problem_view`, which is the caller view when it names none. See [Pipe Run → Async Completion Callbacks](pipe-run.md) for the full webhook contract.
