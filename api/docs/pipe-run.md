# Pipe Run

Execute pipelines with flexible input formats. Choose between synchronous execution (wait for completion) or asynchronous execution (non-blocking). Both routes are part of the [MTHDS Protocol](https://mthds.ai) — this server is the protocol's reference implementation.

> **About `mthds_contents` and MTHDS.** An "MTHDS file" is a Pipelex pipeline definition written in TOML (with the `.mthds` extension). The `mthds_contents` field on every endpoint below is a JSON array of those file contents as raw strings — typically `[open("my_pipe.mthds").read()]` from a client. You can either pass a `pipe_code` referring to a pipe already registered on the server, pass `mthds_contents` inline (the array must contain a file with a `main_pipe` property), or both.

### Execute Pipeline

Execute a Pipelex pipeline with flexible inputs and wait for completion.

**Endpoint:** `POST /v1/execute`

> **Backend selected by `orchestration_mode`.** `/execute` dispatches through the deployment's `orchestration_mode` (config default + optional policy-gated per-request `orchestration_mode` override), symmetric with `/start` — see [Configuration → Orchestration mode](configuration.md). On the orchestrator-agnostic base (`direct`, the default) it runs **in-process**; a `temporal` flavor dispatches the run to a worker and awaits it. `/execute` is **synchronous** (it returns the full output) and always uses `BLOCKING` delivery — wait-semantics is endpoint-set, never requestable, so there is no fire-and-forget option here (use `POST /v1/start`). A per-request backend override is honored only where the deployment sets `allow_request_orchestration_mode_override = true`; otherwise a token differing from the default is refused with a `403`.

**Request Body:**

```json
{
  "pipe_code": "your_pipeline_code",
  "mthds_contents": null,
  "inputs": {
    "input_name": "simple text or object"
  },
  "output_name": null,
  "output_multiplicity": null,
  "dynamic_output_concept_ref": null
}
```

**Request Fields:**

- `pipe_code` (string, optional): The code identifying the pipeline to execute. Required if no `mthds_contents` is provided, or if `mthds_contents` doesn't have a `main_pipe` property. Can be combined with `mthds_contents` to specify which pipe to execute from the provided MTHDS definition.
- `mthds_contents` (list[str], optional): Inline MTHDS file contents as raw strings (always an array, even for a single file). If provided without `pipe_code`, the bundle must contain a file with a `main_pipe` property.
- `inputs` (PipelineInputs, optional): Flexible input format - see [Input Format: PipelineInputs](#input-format-pipelineinputs) below
- `output_name` (string, optional): Name for the output slot
- `output_multiplicity` (string, optional): Output multiplicity setting (`"single"`, `"variable"`, or a specific number)
- `dynamic_output_concept_ref` (string, optional): Override output concept ref
- `bundle_b64` (string, optional): **Pipelex-API extension.** Base64-encoded zip of a whole method bundle — see [Shipping a method bundle](#shipping-a-method-bundle-custom-pipefunc). Mutually exclusive with `files`.
- `files` (dict[str, str], optional): **Pipelex-API extension.** The same bundle as a `{relative_path: text}` map (the unzipped equivalent of `bundle_b64`). Mutually exclusive with `bundle_b64`.
- `method_ref` (string, optional): **Pipelex-API extension.** Run a published method by address instead of inline source — see [Running a method by address](#running-a-method-by-address-method_ref). Mutually exclusive with `mthds_contents` and with a method bundle; `pipe_code` may accompany it to override the package's `main_pipe`.
- `storage_scope` (string, optional): **Pipelex-API extension.** The prefix every object this run writes lands under — see [Host-supplied run context](#host-supplied-run-context-storage_scope-and-analytics_groups).
- `read_scope` (string, optional): **Pipelex-API extension.** The prefix every stored object this run reads must lie under — see [Host-supplied run context](#host-supplied-run-context-storage_scope-and-analytics_groups).
- `analytics_groups` (dict[str, str], optional): **Pipelex-API extension.** The groups this run's telemetry belongs to, such as `{"organization": "org_acme"}` — see [Host-supplied run context](#host-supplied-run-context-storage_scope-and-analytics_groups).

**Validation Rules:**

- At least one of `pipe_code`, `mthds_contents`, a method bundle, or `method_ref` must be provided
- If only `pipe_code`: Must reference a pipe already registered in the library
- If only `mthds_contents`: Must contain a `main_pipe` property
- If both: `pipe_code` specifies which pipe to execute from the `mthds_contents`

**Response:**

```json
{
  "pipeline_run_id": "abc123...",
  "created_at": "2026-01-15T12:00:00Z",
  "state": "COMPLETED",
  "finished_at": "2026-01-15T12:00:05Z",
  "main_stuff_name": "result",
  "pipe_output": {
    "working_memory": {
      "root": { "result": { "content": { "...": "..." } } },
      "aliases": { "main_stuff": "result" }
    }
  }
}
```

**Response Fields:**

- `pipeline_run_id` (string): Unique identifier for the run.
- `created_at` (string): ISO timestamp when the pipeline was created.
- `state` (string): One of `"RUNNING"`, `"COMPLETED"`, `"FAILED"`, `"CANCELLED"`, `"ERROR"`, `"STARTED"`.
- `finished_at` (string | null): ISO timestamp when the pipeline finished, or `null` if still running.
- `main_stuff_name` (string | null): Key under `pipe_output.working_memory.root` where the main result lives. Use this to extract the typed output: `pipe_output.working_memory.root[main_stuff_name].content`.
- `pipe_output` (object): Result of the pipeline execution. Contains `working_memory` with `root` (every named stuff produced during the run) and `aliases` (built-in name mappings such as `main_stuff`).
- `pipe_output.tokens_usages` (array | null): Per-inference-call token usage in the client wire shape (`TokensUsageRecord`): `model_type`, model name/id, `pipe_code`, job-kind fields, `nb_tokens_by_category`, computed USD `cost` (`null` when the model has no rate table), and ISO timestamps. `null` when usage assembly was off for the run, `[]` when no inference happened. `pipe_output.usage_assembly_error` (string | null) is non-null when usage assembly failed. See the pipelex runtime's [TokensUsage Wire Records](https://docs.pipelex.com/under-the-hood/tokens-usage-wire-records/) for the full field reference.
- `pipe_output.graph_spec` (object | null): Best-effort execution graph of the run — the nodes and edges the run actually traversed. `null` when graph generation was off for the run, which is the `interpreter.pipeline_execution.is_generate_graph` setting (`true` in the packaged config); it does not depend on `runtime.tracing`, whose `is_enabled` selects a trace-emission backend rather than gating assembly. `pipe_output.graph_assembly_error` (string | null) is non-null when assembly ran and failed, which is what distinguishes a failed assembly from generation having been off.
- `pipe_output.pipe_io_artifacts` (object | null): The I/O artifacts describing the graph's data, carried beside `graph_spec` so that wherever the graph travels its description travels with it. It groups the same artifacts `/validate` produces — `pipe_io_contracts`, `input_form` and `output_form` — each keyed by namespaced `pipe_ref`, over the **run library's own pipes**: a dependency package's pipes are keyed by alias in the library but by bare `pipe_ref` in the artifacts, where they would collide with the host's, so they are left out and a graph node contributed by a dependency has no entry here. Holding it with the graph is what lets a viewer show a data node's value rather than only its shape. It is built only when the run generated a graph **and** `interpreter.pipeline_execution.graph.graphs_inclusion.graphspec_json` is on (both default to `true`), and only when `graph_spec` itself came out non-null — so a run with `graphspec_json = false` returns a graph with no artifacts beside it and no error, which is the one case where the two fields disagree. `pipe_output.pipe_io_artifacts_error` (string | null) is non-null when the build ran and failed. See [Pipe Validate](pipe-validate.md) for the artifacts' own field reference.
- `method_provenance` (object, only on `method_ref` runs): `{address, tag, commit_sha}` — the package's resolved full address, the requested tag (`null` for a bare address), and the commit SHA that was actually fetched. Absent for runs from inline source or a bundle. See [Running a method by address](#running-a-method-by-address-method_ref).

**Errors** are returned as [RFC 7807 `application/problem+json`](error-responses.md) bodies with HTTP 4xx/5xx status codes. The successful response body has no `status`/`error` field — the HTTP status code is the source of truth. An invalid bundle is refused before any pipe runs with a `422` carrying the same located `validation_errors` validating it gives ([Structured validation errors](error-responses.md#structured-validation-errors)), and a run that fails reports its root fault at the pipe that failed ([Run failures](error-responses.md#run-failures-the-root-fault-located-at-the-failing-pipe)).

---

### Start Pipeline

Start a pipeline execution and get its `pipeline_run_id` back with a `202` ack.

**Endpoint:** `POST /v1/start`

> **Fire-and-forget is a property of this endpoint, honored only by an async-capable backend.** `orchestration_mode` names only the deployment's backend; `/start` sets `FIRE_AND_FORGET` delivery and requires an orchestrator that can honor it. A Temporal deployment (`orchestration_mode = "temporal"`) enqueues the run and returns immediately with a `workflow_id`. On the orchestrator-agnostic base (`orchestration_mode = "direct"`, the default — see [Configuration → Orchestration mode](configuration.md)) the in-process orchestrator is blocking-only, so `/start` is **HONEST**: it refuses with a `400` (`StartRequiresAsyncOrchestration`) — use `POST /v1/execute` — rather than silently running blocking and acking. The completion callback fires on the async path.

**Request Body:**

```json
{
  "pipe_code": "your_pipeline_code",
  "mthds_contents": null,
  "inputs": {
    "input_name": "simple text or object"
  },
  "output_name": null,
  "output_multiplicity": null,
  "dynamic_output_concept_ref": null
}
```

**Request Fields:**

- `pipe_code` (string, optional): The code identifying the pipeline to execute. Required if no `mthds_contents` is provided, or if `mthds_contents` doesn't have a `main_pipe` property.
- `mthds_contents` (list[str], optional): Inline pipeline definitions (always an array, even for a single file). If provided without `pipe_code`, must have a `main_pipe` property.
- `inputs` (PipelineInputs, optional): Flexible input format - see [Input Format: PipelineInputs](#input-format-pipelineinputs) below
- `output_name` (string, optional): Name for the output slot
- `output_multiplicity` (string, optional): Output multiplicity setting (`"single"`, `"variable"`, or a specific number)
- `dynamic_output_concept_ref` (string, optional): Override output concept ref
- `bundle_b64` (string, optional): **Pipelex-API extension.** Base64-encoded zip of a whole method bundle — see [Shipping a method bundle](#shipping-a-method-bundle-custom-pipefunc). Mutually exclusive with `files`.
- `files` (dict[str, str], optional): **Pipelex-API extension.** The same bundle as a `{relative_path: text}` map (the unzipped equivalent of `bundle_b64`). Mutually exclusive with `bundle_b64`.
- `method_ref` (string, optional): **Pipelex-API extension.** Run a published method by address instead of inline source — see [Running a method by address](#running-a-method-by-address-method_ref). Mutually exclusive with `mthds_contents` and with a method bundle; `pipe_code` may accompany it to override the package's `main_pipe`.
- `storage_scope` (string, optional): **Pipelex-API extension.** The prefix every object this run writes lands under — see [Host-supplied run context](#host-supplied-run-context-storage_scope-and-analytics_groups).
- `read_scope` (string, optional): **Pipelex-API extension.** The prefix every stored object this run reads must lie under — see [Host-supplied run context](#host-supplied-run-context-storage_scope-and-analytics_groups).
- `analytics_groups` (dict[str, str], optional): **Pipelex-API extension.** The groups this run's telemetry belongs to, such as `{"organization": "org_acme"}` — see [Host-supplied run context](#host-supplied-run-context-storage_scope-and-analytics_groups).

**Validation Rules:**

- At least one of `pipe_code`, `mthds_contents`, a method bundle, or `method_ref` must be provided
- If only `pipe_code`: Must reference a pipe already registered in the library
- If only `mthds_contents`: Must contain a `main_pipe` property
- If both: `pipe_code` specifies which pipe to execute from the `mthds_contents`

**Important Notes:**

- This endpoint answers `202 Accepted` immediately with a `StartAck` carrying the `pipeline_run_id`
- The pipeline continues executing in the background
- `pipe_output` will be `null` in the response (pipeline hasn't completed yet)
- The request body MAY carry a client-supplied **`pipeline_run_id`** (max 128 chars): this server honors it, and the `StartAck.pipeline_run_id` echoes it back. When absent, the server generates one. (`StartAck.pipeline_run_id` is always authoritative — protocol rule.)

**Response (202):**

```json
{
  "pipeline_run_id": "abc123...",
  "created_at": "2026-01-15T12:00:00Z",
  "state": "STARTED",
  "finished_at": null,
  "main_stuff_name": null,
  "pipe_output": null,
  "workflow_id": "pipeline-abc123..."
}
```

**Response Fields:**

- `pipeline_run_id` (string): Unique identifier for the run. Use this to correlate callbacks (see below).
- `created_at` (string): ISO timestamp when the pipeline was started.
- `state` (string): Always `"STARTED"` from this endpoint — the pipeline is queued, not finished.
- `finished_at` (null): Always `null`; the pipeline hasn't completed.
- `main_stuff_name` (null): Always `null`; populated only on the eventual completion callback.
- `pipe_output` (null): Always `null`; the result isn't ready yet.
- `workflow_id` (string | null): The async orchestrator's workflow ID. A `202` ack is only ever returned by an async-capable backend (e.g. a Temporal flavor), so this carries that orchestrator's id; the in-process `direct` base never acks here — it returns a `400` (`StartRequiresAsyncOrchestration`) instead.
- `method_provenance` (object | null): `{address, tag, commit_sha}` for a `method_ref` run — see [Running a method by address](#running-a-method-by-address-method_ref); `null` for runs from inline source or a bundle.

**Errors** follow the same convention as `/execute`: HTTP 4xx/5xx with an [RFC 7807 `application/problem+json`](error-responses.md) body.

#### Async Completion Callbacks (optional)

`POST /v1/start` accepts an additional optional field in the request body, **`callback_urls`** — a list of HTTP(S) endpoints the server will POST to once the pipeline finishes. This is a **pipelex-api extension**, not part of the MTHDS Protocol (the protocol defines no completion channel; each implementation defines and documents its own extension args). SDK clients pass it through the generic `extra` mapping, e.g. `client.start(..., extra={"callback_urls": [...]})`.

```json
{
  "pipe_code": "your_pipeline_code",
  "inputs": { "input_name": "..." },
  "callback_urls": ["https://my-app.example.com/pipelex-finished"]
}
```

When the pipeline completes, each URL in the list receives a POST carrying:

- A completion notice in the body, not the run's output: `pipeline_run_id`, the delivery `state` (`"COMPLETED"` or `"FAILED"`, also sent under the legacy `status` key), `result_url` (when results were stored: the storage key prefix under which the result files sit, not a fetchable URL) and `error` (the raw `ErrorReport` dict on failure). The receiver reads the results from storage under that prefix.
- An **`X-Completion-Signature`** header — `HMAC-SHA256(secret, pipeline_run_id)` rendered as a hex digest

**Verifying the signature on the receiver side**

Your callback handler should recompute the same HMAC using its own copy of the shared secret and reject any request that doesn't match. Pseudocode:

```python
import hmac, hashlib

expected = hmac.new(
    SHARED_SECRET.encode("utf-8"),
    pipeline_run_id.encode("utf-8"),
    hashlib.sha256,
).hexdigest()

if not hmac.compare_digest(expected, request.headers["X-Completion-Signature"]):
    return Response(status=401)
```

The signer (this server) and the verifier (your callback receiver) must share the same secret value. The secret never travels over the wire — only the per-run HMAC does — so even if a callback request is intercepted, the secret stays safe.

**Server-side requirement**

Set the `COMPLETION_CALLBACK_SECRET` environment variable on the API server **only if** you use `callback_urls`. The variable is read lazily — the server boots fine without it, and only requires it when actually signing a callback. If you call `/start` with `callback_urls` and the env var isn't set, you'll get a 500 with `EnvVarNotFoundError: Environment variable 'COMPLETION_CALLBACK_SECRET' is required but not set`.

The receiver-side secret must be the same value. In typical deployments both sides pull from a shared secrets store (AWS Secrets Manager, Vault, etc.).

---

## Shipping a method bundle (custom PipeFunc)

`mthds_contents` carries only the `.mthds` text. When your method uses a **custom `PipeFunc`** — your own Python function — the code has to travel with the method too. Both `/execute` and `/start` accept the whole bundle in one of two mutually-exclusive forms:

- `bundle_b64`: a base64-encoded **zip** of the bundle directory (`.mthds` + `pipe_func.py` + an optional `requirements.txt`).
- `files`: the same content as a `{relative_path: text}` **map** (the unzipped equivalent) — handy for JSON clients that would rather not zip.

The server materializes the bundle into a temporary library directory for the run and tears it down afterward. The pipe to run comes from the bundle's `main_pipe` (or an explicit `pipe_code`, to pick which pipe in the bundle to run). A bundle carries its own `.mthds`, so it is **mutually exclusive with inline `mthds_contents`** — sending both is a `422` (they would load into one library with no dedup and a shared domain would collide).

**Example (`files` form):**

```json
{
  "files": {
    "main.mthds": "domain = \"demo\"\nmain_pipe = \"crunch\"\n\n[pipe.crunch]\ntype = \"PipeFunc\"\ndescription = \"Crunch numbers\"\ninputs = { data = \"Text\" }\noutput = \"Text\"\nfunction_name = \"crunch\"\n",
    "pipe_func.py": "def crunch(working_memory):\n    return \"...\"\n"
  },
  "inputs": { "data": "1,2,3" }
}
```

**Ingest guards.** Bundles are bounded at ingest and rejected with a clear error (never a silent truncation):

- A hard **file-count** ceiling (`MAX_BUNDLE_FILES`) and a **total decompressed-size** ceiling (`MAX_BUNDLE_TOTAL_KIB`) → `413 PayloadTooLarge`. The zip path bounds actual decompression, so a zip bomb cannot expand past the ceiling, and an oversized `bundle_b64` is refused on its encoded length *before* it is decoded into memory.
- **Path safety:** entry names that are absolute, use `..` traversal, use backslashes, or carry a Windows drive/`:` form → `422 InvalidBundle`.
- Supplying **both** `bundle_b64` and `files`, an empty bundle, or a corrupt zip → `422 InvalidBundle`; invalid base64 → `400 InvalidBase64`.

**Sandbox-hosted only for custom Python.** A bundle that ships any `.py` is honored **only on a sandbox-hosted deployment**, where the load path reads the source without importing it and execution happens in an isolated sandbox. On a non-hosted deployment such a bundle is refused with `403 CustomCodeRequiresSandbox` — running caller-supplied code in-process is never done implicitly. A bundle that carries only `.mthds` (no `.py`) is accepted on any deployment.

**No Python structure classes.** A structure class (a `StructuredContent` subclass) can only be used by importing its module into the runner's own process, which a sandbox-hosted deployment never does, so a bundle whose Python declares one is refused with a `403` (`MethodStructuresRefusedError`) naming each file and class, before anything is loaded. The rule is the same however the method arrives: inline as a bundle, or fetched by `method_ref`. Declare the types as MTHDS concepts with inline structures instead; a PipeFunc returns them by importing the classes the sandbox generates from those concepts (`from structures import <domain>__<Concept>`). The `structures` module that `pipelex build structures` writes is accepted as long as it is left as generated, and it is not sent to the sandbox, which generates its own.

---

## Running a method by address (`method_ref`)

Both `/execute` and `/start` accept **`method_ref`** — a globally resolvable address of a published method package, resolved **by this server** (a Pipelex-API extension; the hosted-only catalog selector `method_id` is a different, platform-resolved field that never reaches this runner):

```json
{
  "method_ref": "github.com/Pipelex/methods/documents@v0.1.0",
  "inputs": { "document": "https://example.com/report.pdf" }
}
```

**The reference grammar is `<address>[@<tag>]`.** The address is `github.com/<owner>/<repo>` optionally followed by a package selector within the repository (`github.com` only for now). A bare address means the repository's default branch at HEAD; `@<tag>` pins the repository at that **git tag** (recommended form `vX.Y.Z`) — branch names are refused, so a reference can never silently track a moving branch. Full browser URLs (`https://github.com/...`, including `/tree/<branch>/...` deep links) are accepted and normalized.

**Resolution.** The server fetches the repository (shallow clone, at the tag when one is named), records the **commit SHA** of what was fetched, and locates the requested package **by manifest identity**: it scans the clone for `METHODS.toml` manifests and selects the one whose declared address (plus `name`, for a package in a library repo) equals the requested address — never by directory path. The package's `.mthds` files then run exactly like an inline submission; its non-`.mthds` files travel like a bundle's.

**Entry pipe.** The pipe to run defaults to the package manifest's `main_pipe`; an explicit `pipe_code` in the request overrides it (to run another pipe from the fetched package).

**Provenance.** The response carries `method_provenance = {address, tag, commit_sha}` — on `/execute` only for `method_ref` runs, on the `/start` ack as a nullable field. Tags can move; the recorded SHA is what keeps a run explainable after the fact.

**Custom Python follows the bundle rules, plus one more.** What decides is *where the code would execute*: `.mthds` content is data, always acceptable. On a deployment that is **not** sandbox-hosted, a fetched package carrying any `.py` is refused with `403 CustomCodeRequiresSandbox`. On a sandbox-hosted deployment, PipeFunc `.py` is accepted (captured as text, executed in the isolated sandbox) — but a package declaring **Python structure classes** (`StructuredContent` subclasses) is refused with a `403` (`MethodStructuresRefusedError`), exactly as a bundle is: see [No Python structure classes](#shipping-a-method-bundle-custom-pipefunc).

**Errors.** Every resolution failure is a distinct RFC 7807 `problem+json` with the originating class as `error_type` (see [Error responses](error-responses.md)):

| Failure | Status | `error_type` |
|---|---|---|
| Reference does not match the grammar | 422 | `MethodRefParseError` |
| Repository could not be fetched, or `@<tag>` is not a tag | 422 | `MethodFetchError` |
| No package matches the address (message lists what the repo contains) | 404 | `MethodPackageNotFoundError` |
| More than one package matches | 422 | `MethodPackageAmbiguityError` |
| Package exceeds the fetched-package ceilings | 422 | `MethodPackageTooLargeError` |
| Package declares Python structure classes | 403 | `MethodStructuresRefusedError` |
| Package ships `.py` on a non-sandbox deployment | 403 | `CustomCodeRequiresSandbox` |

**The clone cache.** Fetched repositories are cached on local disk **keyed by resolved commit SHA** — never by tag. Each request first resolves the reference to its current SHA with a cheap `git ls-remote` (no clone); a cached SHA is reused, a new one (a moved tag, an advanced HEAD) triggers a fresh clone. The cache is per server instance and bounded by count, total bytes, and age.

**Environment knobs.** The cache: `MAX_METHOD_CACHE_CLONES` (default 64), `MAX_METHOD_CACHE_TOTAL_KIB` (default 512 MiB), `MAX_METHOD_CACHE_AGE_HOURS` (default 24), `METHOD_CACHE_DIR` (default: a fixed directory under the system temp dir). The fetch itself is bounded by the pipelex runtime's fetched-package ceilings: `PIPELEX_MAX_FETCHED_PACKAGE_FILES` (default 256), `PIPELEX_MAX_FETCHED_PACKAGE_TOTAL_KIB` (default 8 MiB), and the manifest-scan bounds `PIPELEX_MAX_SCANNED_MANIFESTS` (default 100 manifests considered per fetched repository) and `PIPELEX_MAX_MANIFEST_FILE_KIB` (default 256 KiB per `METHODS.toml` read during package location). All are read once at process start.

`method_ref` also selects the method on the tooling routes: natively on [`POST /v1/validate`](pipe-validate.md), and as the closure selector on [`/resolve` and `/codegen`](codegen.md) (address form resolved; the registry form stays a `501`).

---

## Host-supplied run context: `storage_scope` and `analytics_groups`

Both `/execute` and `/start` accept optional fields that describe the run's tenancy rather than its method: `storage_scope`, `read_scope` and `analytics_groups`. All are **Pipelex-API extensions**, and all are **data the host computes**, which is why they ride in the body: the caller's *identity* arrives separately, on the trusted `X-User-Id` header or the bearer token (see [Authentication](index.md#authentication)), because it is something a proxy vouches for rather than something the caller chooses. The runtime carries them opaquely and never reads a value by name, so it has no notion of what an organization or a tenant is.

```json
{
  "pipe_code": "your_pipeline_code",
  "inputs": { "input_name": "..." },
  "storage_scope": "org_acme/method_42/run_7",
  "read_scope": "org_acme",
  "analytics_groups": { "organization": "org_acme" }
}
```

**`storage_scope`** is the prefix every object the run writes lands under: one to three path-safe segments, onto which the runtime composes its own leaves (`assets/`, `generated/`, `results/`, `payloads/`). Omit it and the run is scoped to the caller's own id, which is right for a single-tenant deployment and wrong for a multi-tenant one: a host serving many tenants must send it. Each segment is one or more characters from `A-Za-z0-9_-`, so an empty segment, a leading or trailing slash, a `.` or `..`, or a fourth segment is refused with a `422` whose `error_type` is `InvalidStorageScope`.

**`read_scope`** bounds what the run may read: every `pipelex-storage://` key the run reads, whether an input, a URL a pipe builds or an image it shows a model, must lie under it, and a scoped run reads no local path at all. It follows the same segment rule as `storage_scope`, and the storage scope must be the read scope or lie under it, since a run reads back what it writes: `org_acme` covers `org_acme/method_42/run_7`, while `org_other` does not. Omit it and the run is scoped to the caller's own id when the deployment identifies its callers, which is also where their writes land by default, and unscoped when the deployment is single-tenant. A host serving many tenants must send it: a host that sends its own `storage_scope` but no `read_scope` is refused, since that storage scope lies under no caller's id. A malformed read scope, a storage scope outside it, or the local storage scope `local` beside one is a `422` whose `error_type` is `InvalidReadScope`, answered before any method is fetched or library loaded. A read the scope does not allow is refused when the run makes it, with the `error_type` `UriReadRefusedError`, whose message says where the URL sat without quoting it. On `/execute` it is a `422`. On `/start` it is a synchronous `422` when an input breaks the rule, and a run that ends `FAILED` with that error in its completion callback when a pipe reaches for the URL during the run.

**`analytics_groups`** names the entities the run's telemetry belongs to, as a mapping of group type to group key. The runtime carries it on the run as its opaque `extras` and stamps it on every span of the run as the attribute `pipelex.run.extras`, so every OpenTelemetry exporter receives it, and the deployment's own PostHog stream, when `telemetry.toml` sets `mode = "identified"`, attaches it to each capture as PostHog groups. That is what lets a generation made for one of your customers appear inside that customer's organization instead of under one identity for the whole deployment. What Pipelex's own Gateway telemetry stream receives is the runtime's decision, not this server's; the runtime this server pins attributes that stream the same way, with the run's `user_id` and these groups. The rules are the runtime's own, imported rather than restated here:

- A **group type** (a key of the mapping) is lowercase snake_case starting with a letter, at most 32 characters, such as `organization`.
- A **group key** (a value) is 1 to 128 characters from `A-Za-z0-9_-`. Whitespace, control characters and separators are refused, because the key is quoted into log lines and capture payloads.
- The mapping holds **at most five** entries, since a telemetry backend registers only a small fixed number of group types per project.
- It is **optional**. Omitting it, sending `null` or sending `{}` all mean the run belongs to no group, which misattributes nothing.

A mapping outside these rules is refused with a `422` whose `error_type` is `InvalidAnalyticsGroups`, before any method is fetched or any library loaded. A body that fails on more than one of the extension fields at once answers with the generic `ValidationError`, and its `detail` names every field that failed.

The caller's id is the run's person on that same stream, with one exception: a deployment with no user model attributes every run to the literal `single-tenant`, which the runtime declines as a person and replaces with the `user_id` configured in `telemetry.toml`. The groups do not depend on it, so a single-tenant deployment that sends `analytics_groups` still has them on every capture.

---

## Input Format: PipelineInputs

The `inputs` field accepts several shapes. Pipelex picks how to interpret each value from its structure — pass a string to a `Text` input and you get `TextContent`, pass a dict with `concept` and `content` keys and you get explicit concept resolution, etc. The cases below enumerate every supported form.

**The request body is plain JSON.** The Python objects in Cases 1.3 to 1.5, and the `DictStuff` instances further down, are what a Python caller writes; a Python client of this API serializes each one to plain JSON before sending it, and the server never rebuilds a Python class from the request. The class name does not travel, so each value is read against the entry pipe's declared input. A structured object (Case 1.3) arrives as its fields and a list of them (Case 1.4) as a list of those, and both are read as intended; a `DictStuff` arrives as the Case 2 envelope. A `ListContent` wrapper (Case 1.5) arrives as `{"items": [...]}`, which the server reads as one item rather than a list, and a native `TextContent` arrives as `{"text": ...}`, which a `Text` input refuses: over HTTP, send the bare list of items or strings instead, or the `{"concept": ..., "content": [...]}` envelope of Cases 2.2, 2.4 and 2.6. A body carrying a `__class__` or `__module__` key, or a key starting with `__kajson`, in any object at any depth is refused with a `422 ReservedObjectKey` (see [Error Responses](error-responses.md#status-codes)).

### How Input Formatting Works

**Case 1: Direct Content** - Provide the value directly (simplest)

- 1.1: String → `"my text"`
- 1.2: List of strings → `["text1", "text2"]`
- 1.3: StructuredContent object → `MyClass(arg1="value")`
- 1.4: List of StuffContent objects → `[MyClass(...), MyClass(...)]`
- 1.5: ListContent of StuffContent objects → `ListContent(items=[MyClass(...), MyClass(...)])`

**Note:** Cases 1.3 and 1.5 are at the same level - both handle content types that inherit from `StuffContent`, but for different purposes (custom classes vs. list wrappers).

**Case 2: Explicit Format** - Use `{"concept": "...", "content": "..."}` for control (plain dict or DictStuff instance)

- 2.1: String with concept → `{"concept": "Text", "content": "my text"}`
- 2.2: List of strings with concept → `{"concept": "Text", "content": ["text1", "text2"]}`
- 2.3: StructuredContent object with concept → `{"concept": "Invoice", "content": InvoiceObject}`
- 2.4: List of StructuredContent objects with concept → `{"concept": "Invoice", "content": [...]}`
- 2.5: Dictionary (structured data) → `{"concept": "Invoice", "content": {"field": "value"}}`
- 2.6: List of dictionaries → `{"concept": "Invoice", "content": [{...}, {...}]}`
- 2.7: File / document URL → `{"concept": "Document", "content": {"url": "https://…/file.pdf"}}`

**Pro Tip:** For **text inputs specifically**, skip the verbose format. Just provide the string directly: `"text": "Hello"` instead of `"text": {"concept": "Text", "content": "Hello"}`

---

## Case 1: Direct Content Format

When you provide content directly (without the `concept` key), Pipelex intelligently infers the type.

### 1.1: Simple String (Text)

The simplest case - just provide a string directly:

```json
{
  "inputs": {
    "my_text": "my text"
  }
}
```

**Result:** At a `Text` input, automatically becomes `TextContent` with concept `native.Text`

The input's declaration decides the reading for two native concepts. At an `Anything` input, the string becomes a `native.Anything` value holding the text, and a number, a boolean or an object is taken the same way, as a value of its own kind; a date sent as a string is read as text. An `Anything` input refuses `null` and a list, both with a `422`: a list is taken only by an `Anything[]` input, whose items are such values and can be neither `null` nor a list themselves. At a `JSON` input, a string is refused: a `JSON` input reads a JSON object literally, and a `JSON[]` input a list of objects. `NaN` and the infinities are refused at `Number`, `JSON` and `Anything` inputs, since JSON cannot carry them.

### 1.2: List of Strings (Text List)

Provide multiple text items as a list:

```json
{
  "inputs": {
    "my_texts": ["my text1", "my text2", "my text3"]
  }
}
```

**Result:** Becomes a `ListContent` containing multiple `TextContent` items

**Note:** The concept must be compatible with `native.Text` or an error will be raised. The one exception is an `Anything[]` input, where the list keeps the `native.Anything` concept and holds each string as text.

### 1.3: StructuredContent Object

Provide a structured object directly (for Python clients):

```python
# Python client example
from my_project.domain.domain_struct import MyConcept, MySubClass

inputs = {
    "invoice_data": MyConcept(arg1="arg1", arg2=1, arg3=MySubClass(arg4="arg4")),
}
```

**What is StructuredContent?**

- `StructuredContent` is the base class for user-defined data structures in Pipelex
- You create your own classes by inheriting from `StructuredContent`
- These classes are defined in your project's Python files
- Learn more: [Python StructuredContent Classes](https://docs.pipelex.com/pages/build-reliable-ai-workflows-with-pipelex/define_your_concepts/#3-python-structuredcontent-classes)

**Concept Resolution** (in-process calls only, where the object itself reaches the runtime; over HTTP the class name does not travel, and the declared input decides):

- The system searches all available domains for a concept matching the class name
- If multiple concepts with the same name exist in different domains → **Error**: Must specify domain
- If no concept is found → **Error**

### 1.4: List of StuffContent Objects

Provide multiple content objects in a plain Python list:

```python
# Python client example
inputs = {
    "invoice_list": [
        MyConcept(arg1="arg1", arg2=1, arg3=MySubClass(arg4="arg4")),
        MyConcept(arg1="arg1_2", arg2=2, arg3=MySubClass(arg4="arg4_2")),
    ],
}
```

**What it accepts:**

- Lists of `StructuredContent` objects (user-defined classes)
- Lists of native content objects (`TextContent`, `ImageContent`, etc.), in in-process calls only (over HTTP, see the plain-JSON note above)

**Requirements:**

- All items must be of the same type
- Concept resolution follows the same rules as 1.3
- Creates a new `ListContent` wrapper internally

### 1.5: ListContent of StuffContent Objects

Provide an existing `ListContent` wrapper object (in-process Python calls only; over HTTP, send the bare list of items, as the plain-JSON note above explains):

```python
# Python client example
from pipelex.core.stuffs.list_content import ListContent

inputs = {
    "invoice_list": ListContent(
        items=[
            MyConcept(arg1="arg1", arg2=1, arg3=MySubClass(arg4="arg4")),
            MyConcept(arg1="arg1_2", arg2=2, arg3=MySubClass(arg4="arg4_2")),
        ]
    ),
}
```

**Key Difference from Case 1.4:**

- Case 1.4: Plain Python list `[item1, item2]` → **Creates** a new `ListContent` wrapper
- Case 1.5: Already wrapped `ListContent(items=[item1, item2])` → **Uses** the wrapper directly

**Why Case 1.5 is Separate from Case 1.3:**

- `StructuredContent` and `ListContent` are **sibling classes** (both inherit from `StuffContent`)
- Case 1.3 handles user-defined structured data classes
- Case 1.5 handles list container wrappers
- They're at the same inheritance level, not parent-child

**Requirements:**

- All items within the `ListContent` must be `StuffContent` objects (this includes both `StructuredContent` and native content like `TextContent`, `ImageContent`)
- All items must be of the same type
- The `ListContent` cannot be empty
- Concept is inferred from the first item's class name (not from "ListContent")

**Use Case:** This format is useful when you already have data wrapped in a `ListContent` object from a previous pipeline execution or when working with Pipelex's internal data structures.

---

## Case 2: Explicit Format (Concept and Content)

Use the explicit format `{"concept": "...", "content": "..."}` when you need precise control over concept selection or when working with domain-specific concepts.

### 2.1: Explicit String Input

```json
{
  "inputs": {
    "text": {
      "concept": "Text",
      "content": "my text"
    }
  }
}
```

**Concept Options:**

- `"Text"` or `"native.Text"` for native text
- Any custom concept that is strictly compatible with `native.Text`

### 2.2: Explicit List of Strings

```json
{
  "inputs": {
    "documents": {
      "concept": "Text",
      "content": ["text1", "text2", "text3"]
    }
  }
}
```

**Result:** `ListContent` with multiple `TextContent` items

### 2.3: Structured Object with Concept

```json
{
  "inputs": {
    "invoice_data": {
      "concept": "Invoice",
      "content": {
        "invoice_number": "INV-001",
        "amount": 1250.00,
        "date": "2025-10-20"
      }
    }
  }
}
```

**Concept Resolution with Search Domains:**

When you specify a concept name without a domain prefix:

- ✅ If the concept exists in only one domain → Automatically found
- ❌ If the concept exists in multiple domains → **Error**: "Multiple concepts found. Please specify domain as 'domain.Concept'"
- ❌ If the concept doesn't exist → **Error**: "Concept not found"

**Using Domain Prefix:**
```json
{
  "concept": "accounting.Invoice"
}
```

This explicitly tells Pipelex to use the `Invoice` concept from the `accounting` domain.

### 2.4: List of Structured Objects

```json
{
  "inputs": {
    "invoices": {
      "concept": "Invoice",
      "content": [
        {
          "invoice_number": "INV-001",
          "amount": 1250.00
        },
        {
          "invoice_number": "INV-002",
          "amount": 890.00
        }
      ]
    }
  }
}
```

**Result:** `ListContent` with multiple structured content items

### 2.5: Dictionary Content

Provide structured data as a dictionary:

```json
{
  "inputs": {
    "person": {
      "concept": "PersonInfo",
      "content": {
        "arg1": "something",
        "arg2": 1,
        "arg3": {
          "arg4": "something else"
        }
      }
    }
  }
}
```

The system will:
1. Find the concept structure (with domain resolution as explained above)
2. Validate the dictionary against the concept's structure
3. Create the appropriate content object

### 2.6: List of Dictionaries

```json
{
  "inputs": {
    "people": {
      "concept": "PersonInfo",
      "content": [
        {
          "arg1": "something",
          "arg2": 1,
          "arg3": {"arg4": "something else"}
        },
        {
          "arg1": "something else",
          "arg2": 2,
          "arg3": {"arg4": "something else else"}
        }
      ]
    }
  }
}
```

### 2.7: File / Document Input

For pipes whose inputs declare `Document`, `Image`, or `PDF` (any URL-bearing native concept), provide a `url` inside `content`. The URL can be public HTTP(S), a `pipelex-storage://` URI, or a base64 data URL.

```json
{
  "inputs": {
    "cv": {
      "concept": "Document",
      "content": { "url": "https://example.com/resume.pdf" }
    },
    "headshot": {
      "concept": "Image",
      "content": { "url": "https://example.com/photo.jpg" }
    }
  }
}
```

**Optional fields on `Document` content:**

- `mime_type` (string) — e.g. `"application/pdf"`. Inferred from the URL when omitted.
- `filename` (string) — the original filename. Auto-extracted from local-file URLs.
- `title` (string) — display title for the document.
- `snippet` (string) — text excerpt or description.
- `public_url` (string) — public HTTPS URL when `url` is a private/storage URI.

If you pass `Document` content as a list (`[{"url": "…"}, {"url": "…"}]`), Pipelex wraps it in a `ListContent` automatically — same rules as Case 2.4.

### Using DictStuff Instances (Python Clients Only)

For Python clients, you can also pass `DictStuff` instances instead of plain dicts. `DictStuff` is a Pydantic model with the same structure as the explicit format.

```python
from pipelex.client import PipelexClient
from pipelex.core.stuffs.stuff import DictStuff

client = PipelexClient(api_token="YOUR_API_KEY")

# Using DictStuff instance with dict content
response = await client.execute_pipeline(
    pipe_code="process_invoice",
    inputs={
        "invoice": DictStuff(
            concept="accounting.Invoice",
            content={
                "invoice_number": "INV-001",
                "amount": 1250.00,
                "date": "2025-10-20",
            },
        ),
    },
)

# Using DictStuff instance with list of dicts content
response = await client.execute_pipeline(
    pipe_code="process_invoices",
    inputs={
        "invoices": DictStuff(
            concept="accounting.Invoice",
            content=[
                {"invoice_number": "INV-001", "amount": 1250.00},
                {"invoice_number": "INV-002", "amount": 890.00},
            ],
        ),
    },
)

# Using DictStuff instance with list of strings (for Text concept)
response = await client.execute_pipeline(
    pipe_code="analyze_texts",
    inputs={
        "documents": DictStuff(
            concept="Text",
            content=["document 1", "document 2", "document 3"],
        ),
    },
)
```

**DictStuff Structure:**

- `concept` (str): The concept code (with optional domain prefix)
- `content` (dict[str, Any] | list[Any]): The actual data content

**Content Types:**

- **Dictionary**: Single structured object → Creates a single Stuff
- **List of dicts**: Multiple structured objects → Creates ListContent with validated items
- **List of strings** (for Text-compatible concepts): Creates ListContent of TextContent

**Note:** `DictStuff` instances are automatically converted to plain dicts and processed through the standard Case 2 logic.

---

## Search Domains Explained

When you reference a concept by name (like `"Invoice"` or `"PersonInfo"`), Pipelex needs to find it in your loaded domains.

### Automatic Search

```json
{
  "concept": "Invoice"
}
```

**What happens:**
1. Pipelex searches all available domains for a concept named `"Invoice"`
2. If found in **exactly one domain** → ✅ Uses that concept
3. If found in **multiple domains** → ❌ Error: "Ambiguous concept: Found 'Invoice' in domains: accounting, billing. Use 'domain.Invoice' format."
4. If **not found** → ❌ Error: "Concept 'Invoice' not found in any domain"

### Explicit Domain Specification

To avoid ambiguity, specify the domain explicitly:

```json
{
  "concept": "accounting.Invoice"
}
```

**Format:** `"domain_name.ConceptName"`

This tells Pipelex exactly which concept to use, bypassing the search.

### Best Practices

- Use simple names (`"Invoice"`) when you have unique concept names across domains
- Use domain-prefixed names (`"accounting.Invoice"`) when:
  - You have concepts with the same name in different domains
  - You want to be explicit about which concept to use
  - You're building APIs that need to be unambiguous

---

## Multiple Input Combinations

Combine different input types in a single request:

```json
{
  "inputs": {
    "text": "Analyze this contract for risks.",
    "category": {
      "concept": "Category",
      "content": {"name": "legal", "priority": "high"}
    },
    "options": ["option1", "option2", "option3"],
    "invoice": {
      "concept": "accounting.Invoice",
      "content": {
        "invoice_number": "INV-001",
        "amount": 1250.00
      }
    }
  }
}
```

In this example:

- `text` uses direct string format (Case 1.1)
- `category` uses explicit format with structured content (Case 2.5)
- `options` uses direct list format (Case 1.2)
- `invoice` uses explicit format with domain prefix and structured content (Case 2.5)

---



