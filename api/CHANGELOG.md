# Changelog

This changelog ends at v0.33.2, the server's last release from the `Pipelex/pipelex-api` repository. The server is now released together with pipelex, under pipelex's version, and its changes are recorded in the pipelex repository's own `CHANGELOG.md`.

## [v0.33.2] - 2026-10-01

### Changed

- **The server is moving into `Pipelex/pipelex`**: from the next release, the server ships from the pipelex repository's `api/` directory together with the pipelex library and under its version number, so the next `pipelex/pipelex-api` image tag is a pipelex version; the image name, its port and its `/root/.pipelex` mount do not change, and this repository will be archived once the move lands.

### Fixed

- **The `callback_urls` description says what a completion webhook carries**: the OpenAPI description and the run docs said the runner posts the run's result to each callback URL; they now say the body is a completion notice (`pipeline_run_id`, `state` with its legacy `status` alias, the `result_url` storage key prefix and `error`), and that the results themselves stay in storage under that prefix. The description also says that the `X-Completion-Signature` header signs the run id, not the body.

## [v0.33.1] - 2026-09-30

### Fixed

- **A pipe selection refusal names its failure in `error_type`**: on `POST /v1/pipe-io` and `POST /v1/build/inputs`, `/v1/build/output` and `/v1/build/runner`, a selection the server cannot make is still an input `422`, but its `error_type` is now `EntryPipeNotFoundError` (a `pipe_ref` naming no pipe, a manifest `main_pipe` the closure lacks, or no `pipe_ref` over a closure declaring no `main_pipe`) or `EntryPipeAmbiguousError` (a bare code matching several domains, or no `pipe_ref` over a closure whose domains declare several `main_pipe`s), the values the run routes answer for an unknown or ambiguous `pipe_code`, where it was the `ValidationError` of a malformed request. The problem's `type` and `title` follow the class, and so does its `user_action`, except that the two refusals of an omitted `pipe_ref` ask for a `pipe_ref` instead of a pipe-code check.
- **The published OpenAPI never names the hosted selector field**: the `POST /v1/pipe-io` request schema's description no longer names the hosted catalog's selector field, and a test keeps that name out of the whole document.

## [v0.33.0] - 2026-09-30

### Highlights

**A method's I/O artifacts without a validation.** `POST /v1/pipe-io` returns the pipe I/O contracts, input form and output form of one pipe, or of every pipe, off one load of the method and with no dry run, so a caller that shows a method, prepares its inputs or generates types for it no longer pays for a `/v1/validate` sweep. The per-pipe selectors also stop calling an ambiguous pipe missing.

### Added

- **`POST /v1/pipe-io`**: returns a method's `pipe_io_contracts`, `input_form` and `output_form` without a dry run, keyed by qualified `pipe_ref`, for the selected pipe or, with `all_pipes: true`, for every pipe, beside the resolved `pipe_ref`, the method's own `default_pipe_ref`, `pending_signatures` and `is_runnable`. It takes the same `files` or `method_ref` closure selector and `pipe_ref` as the `/v1/build/*` routes, `include_files: true` echoes the closure's `.mthds` files, and each artifact equals `/v1/validate`'s same-named view for a closure both routes accept.

### Fixed

- **An ambiguous pipe selector says it is ambiguous**: on `POST /v1/build/inputs`, `/v1/build/output` and `/v1/build/runner`, a bare `pipe_ref` or manifest `main_pipe` that matches pipes in several domains is still a `422`, and its detail now says the code matches several domains and names the qualified refs to choose from, where it said the pipe was not found.

## [v0.32.0] - 2026-09-29

### Highlights

**The runner no longer trusts the run body or the methods it is handed.** `POST /v1/execute` and `POST /v1/start` parse their body as plain JSON, which closes a path by which any caller could make the runner import and instantiate a class. On `pipelex` 0.70.0, a run reads storage only under its read scope, every template renders in Jinja's sandbox, a URL fetch refuses private destinations, and a sandbox-hosted deployment refuses a bundle that declares Python structure classes. A multi-tenant host must now send `read_scope`, and a method that ran on 0.69.0 can now be refused, as the entries below describe.

### Changed

- **Pinned `pipelex` 0.70.0 (Breaking)**: up from `==0.69.0`, exactly. It is the release that carries the read scope and the structure-class refusal described under Security, and it hardens the runtime for methods it did not write, so a method that ran on 0.69.0 can now be refused, as the entries below describe. The `.pipelex/` config shipped here already sits at the current schema, and the release moves no own-key backend's model roster.
- **PipeCompose, PipeSearch and PipeImgGen refuse an input they never read (Breaking)**: as PipeLLM already did, validation refuses a declared input that none of the pipe's templates reads, as `extraneous_input_variable` naming the input. Reference it in a template, or remove it from `inputs`.
- **A structure field naming an undeclared concept refuses the load (Breaking)**: a concept whose field names a concept that no bundle it can see declares is now refused at load with `LibraryLoadingError`, naming the concept, its bundle and the missing structure class, where it loaded and then failed at first use with pydantic's "not fully defined" error.
- **`POST /v1/codegen` stamps `engine_version` `0.70.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.69.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **A template's reads are seen wherever it makes them**: an input read only through a subscript, a call or a `{% set %}`, such as `{{ items[0].text }}` or `{{ record['meta'].title }}`, now counts as read, where validation refused it as unread, and `{{ combo.summary }}` resolves the named parts of a `Composite` output, which rendered empty.
- **Concepts holding other concepts resolve**: a field typed by a method package's concept, by a concept an earlier load declared, by a concept backed by a Python class, or as `native.Anything` now resolves, where each loaded and then failed at first use with pydantic's "not fully defined" error.
- **A generated file's storage key names its format**: a fetched `image/svg+xml` is stored under a `.svg` key, and a type with no extension of its own under `.bin`, where both got `.jpg`.

### Security

- **The run body is plain JSON, and class markers in it are refused (Breaking)**: `POST /v1/execute` and `POST /v1/start` parse their body with a plain JSON parser instead of kajson, which imported and instantiated any class a body named with `__class__` and `__module__`, so any caller able to reach the runner could run code on it. A body carrying a `__class__` or `__module__` key, or a key starting with `__kajson`, in any object at any depth now answers `422 ReservedObjectKey`, and the published request schema no longer offers a serialized working memory as `inputs`.
- **Runs read only under their read scope (Breaking)**: `POST /v1/execute` and `POST /v1/start` take a `read_scope`, the prefix every `pipelex-storage://` key a run reads must lie under, and a scoped run reads no local path. Omitted, it is the caller's own id on a deployment that identifies callers and unscoped on a single-tenant one, so a multi-tenant host must send it; a malformed read scope, or a storage scope outside it, is a `422` `InvalidReadScope`. A read outside the scope is refused when the run makes it, as `UriReadRefusedError`: a `422` on `/execute`, and on `/start` a synchronous `422` for an input or a run that ends `FAILED` for a URL a pipe reaches during the run.
- **A bundle declaring Python structure classes is refused (Breaking)**: on a sandbox-hosted deployment, a `files` or `bundle_b64` bundle whose Python declares a `StructuredContent` subclass now answers `403` `MethodStructuresRefusedError` naming each file and class, as a fetched `method_ref` package already did, and none of its modules is imported. Declare the types as MTHDS concepts instead; the unedited module `pipelex build structures` writes is accepted.
- **Every template renders in Jinja's sandbox (Breaking)**: a prompt, a compose or construct template, an image or search prompt, or a condition expression may read data and call methods of plain values only. One that reaches for a Python internal, calls a method of a Pipelex or pydantic object, or reads a name starting with an underscore other than an input's `_stuff_name`, `_content_class`, `_concept_code` and `_stuff_code` fails with `Jinja2TemplateSecurityError`, and validation refuses the visible cases as `template_private_name`. `_content` and `stuff` are no longer readable on an input, and a PipeCompose construct `from` path or a `list_to_dict_keyed_by` name with a segment starting with an underscore is refused at validation.
- **Fetching a URL refuses private destinations (Breaking)**: every download of a URL a value carries, such as a document to extract or a prompt image for a provider that does not take URLs, now refuses a host that is `localhost`, a cloud metadata alias, or resolves to a private, loopback, link-local or metadata address, on every redirect hop, and fails the pipe with `SsrfBlockedError` naming the host. The guarded fetch ignores `HTTP_PROXY` and `HTTPS_PROXY`. The image keeps the guard on; a self-hosted deployment reading documents from an intranet host, or reaching the internet only through a proxy, sets `[runtime.network] is_fetch_ssrf_guard_enabled = false`, as [Configuration](docs/configuration.md) describes.

## [v0.31.0] - 2026-09-28

### Highlights

**Run inputs take the values their concept declares, and own-key backends offer today's models.** On `pipelex` 0.69.0, an `Anything` input accepts a string, a number, a boolean or an object and a `JSON` input an object, where most of them used to be refused, and the image's own-key backend files are now the pinned release's, so a deployment that switches one on is offered the current model roster. A deployment that mounts its own `.pipelex/` renames its Bedrock handle to `bedrock_aioboto` and replaces any model handle that went.

### Changed

- **Pinned `pipelex` 0.69.0 (Breaking)**: up from `==0.68.0`, exactly, the release that moves structured output to `instructor` 1.17 and the provider SDKs with it, so the image now carries `mistralai` 2.x and `aiobotocore` 3.x in place of `aioboto3`. Under `instructor` 1.17 the `instructor/openai_structured_outputs` structure method sends a non-strict tool schema, so OpenAI no longer enforces the schema itself; pipelex still validates the response and re-asks on a mismatch.
- **The Bedrock SDK handle is `bedrock_aioboto` (Breaking)**: the shipped `.pipelex/inference/backends/bedrock.toml` now sets `sdk = "bedrock_aioboto"`, and a deployment that mounts its own `.pipelex/` still setting `sdk = "bedrock_aioboto3"` keeps booting but fails every call to those Bedrock models. `pipelex migrate` names such a file without rewriting it, so replace the handle by hand, in `[defaults]` and in any model table that overrides it.
- **`Anything` and `JSON` run inputs are read by what they declare (Breaking)**: on `POST /v1/execute` and `POST /v1/start`, a bare string at an `Anything` input becomes a `native.Anything` value rather than `native.Text`, a bare string at a `JSON` input is refused, an item holding `concept` and `content` keys inside a bare `Anything[]` or `JSON[]` list is refused, an explicit single value at a fixed-count `Concept[N]` input raises `MultiplicityCountMismatchError`, and `NaN` or an infinity at a `Number`, `JSON` or `Anything` input is refused. A value the fallback cannot build, such as a list of plain objects at a `Dynamic` input, now answers `StructureValidationError` naming the input and its concept instead of `StuffFactoryError`.
- **The `json_schema` of an `Anything` value excludes arrays and `null`**: in the `pipe_io_contracts` that `POST /v1/validate` and `POST /v1/execute` return, the `json_schema` of a single `Anything` input or output now carries `"not": {"type": ["array", "null"]}`, and so does the `items` schema of an `Anything[]` input, so a form or validator generated from it refuses what the run refuses.
- **`POST /v1/build/inputs` renders a `JSON` input as the bare object (Breaking)**: the compact template of a `JSON` input is the object itself, where it was the envelope `{"concept": "native.JSON", "content": {"json_obj": …}}`.
- **`POST /v1/codegen` stamps `engine_version` `0.69.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.68.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.
- **Own-key backends offer the pinned `pipelex` model roster (Breaking)**: the image's `inference/backends/` files, unchanged since `pipelex` 0.14.0, are now the `pipelex` 0.69.0 kit's, as is `inference/routing_profiles.toml`, so a deployment that switches on an own-key backend is offered the current models and resolves the model deck's default aliases, whose GPT-5.6 targets `openai` and `azure_openai` did not declare. Handles that went, which a method must replace on a deployment that switched their backend on: on `openai`, `gpt-3.5-turbo`, `gpt-4`, `gpt-4-turbo`, the dated `gpt-4o-2024-11-20` and `gpt-4o-mini-2024-07-18`, every `gpt-4.1`, `gpt-5`, `gpt-5.1` and `gpt-5.2` handle, and `o1`, `o3`, `o3-mini` and `o4-mini`; on `azure_openai`, every `gpt-4.1`, `gpt-5`, `gpt-5.1` and `gpt-5.2` handle, and `o1`, `o1-mini`, `o3` and `o3-mini`; on `google` and `portkey`, `gemini-3.0-pro` (replaced by `gemini-3.1-pro`) and `gemini-3.0-flash-preview` (renamed `gemini-3.0-flash`), and on `portkey` also `o4-mini`; on `bedrock`, `claude-3.7-sonnet`; on `openrouter`, `google/gemini-3-pro-preview`. The kit's new `minimax` and `pipelex_manifold` backends ship switched off, the unused `perplexity` and `pipelex_inference` files are gone, and the default Pipelex Gateway deployment, whose catalog comes from the remote config, is unaffected.

### Fixed

- **`Anything` and `JSON` inputs take the values they declare**: an `Anything` input accepts a string, a number, a boolean or an object, and `Anything[]` a list of them, where all but a bare string used to be refused, while `null` and a list at a single `Anything` input, and a `null` or nested-list item of an `Anything[]` list, are refused with a `422`; a `JSON` input accepts an object and `JSON[]` a list of objects, which used to be refused with an error naming neither the input nor its concept.
- **Structured output on Gemini works with enum fields and honours the prompt settings**: on a deployment that enables the `google` backend, a structured call whose schema has an enum field no longer fails on every attempt, and the system prompt, temperature and token limit now reach Gemini.
- **A structured-output call keeps its provider error and re-asks when the model returns no tool call**: a rate limit, timeout or refused connection inside a structured call keeps its category and retryability instead of reading as an unknown error, and a response carrying no tool call or no JSON is re-asked instead of failing at once.
- **A model the inference gateway refuses reads as a configuration fault**: the gateway's `model_not_allowed_error` refusal is now a `config` error whose `user_action` is `change_model` naming the model handle, where it told the caller to review the prompt, parameters and inputs; the status stays `500`.

## [v0.30.0] - 2026-09-28

### Highlights

**A run dispatched to a worker keeps the caller's request id.** On `pipelex` 0.68.0, the lines a worker writes while it runs a `POST /v1/execute` run carry the `request_id` the response echoes, and the runtime's own span moves under `pipelex.*` on every log line.

### Changed

- **Pinned `pipelex` 0.68.0 (Breaking)**: up from `==0.67.0`, exactly, the release whose `execute` accepts the inbound request id the host is serving. The `.pipelex/` config shipped here already sits at the current schema, so no migration is required, but a deployment that selects the `gcp` log sink instead of `json` now refuses to boot when Google rejects its credentials, where it used to boot and lose every record in silence.
- **A log line's trace keys name the host's span, and the runtime's span moves under `pipelex.*` (Breaking)**: `trace_id`, `span_id` and `trace_flags` now name the process's current OpenTelemetry span, which this server does not open, so they are absent unless the deployment runs it under OpenTelemetry instrumentation of its own. A line the runtime emits from inside a traced run carries the runtime's span as `pipelex.trace_id` and `pipelex.span_id` instead, so a query that joined lines to the runtime's exported spans on `trace_id` now joins on `pipelex.trace_id`.
- **`POST /v1/codegen` stamps `engine_version` `0.68.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.67.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **A distributed `POST /v1/execute` run's worker lines carry the request id**: the route now puts the request id it resolved on the run's metadata, as `POST /v1/start` already did, so on a deployment whose `orchestration_mode` dispatches to a worker, such as `temporal`, the lines the worker writes while it runs the run's workflow and activities carry the `request_id` the response echoes. The logging page now says how the id reaches a worker's lines, and that a `POST /v1/validate` dispatched to a worker does not carry it yet.

## [v0.29.0] - 2026-09-27

### Highlights

**A caught error reaches the caller with its reason and its place.** A run of an invalid bundle is refused before any pipe runs with the same located validation items `/validate` gives, a failed run names the pipe that failed and its root fault, and a run the caller's own method refuses keeps its explanation under STRICT disclosure.

### Added

- **Validation items carry more locators**: a TOML syntax error's item carries the 1-based `line` and `column` the parser stopped at, an `unresolved_concept` item carries `declared_concepts`, and the new `unknown_model` item carries `model_reference` (the reference as the bundle wrote it), `model_type` and `suggestions` (the model deck's close matches of that kind), with an `unsafe` rename fix when there is exactly one. The OpenAPI artifact publishes the new fields and the new `unknown_model` value of `PipeValidationErrorType`.
- **A run graph marks a list-valued stuff**: every io item of a `graph_spec` carries `multiplicity`, `true` when the stuff is a list, a fixed-count one included, and `null` otherwise, so a renderer can show a `Document[]` input or a `Record[]` output as a list. The schema also admits a positive integer, which the runtime does not emit.

### Changed

- **Pinned `pipelex` 0.67.0 (Breaking)**: up from `==0.66.1`, exactly, the release that carries the located error reporting the entries below describe. The `.pipelex/` config shipped here already sits at the current schema, so no migration is required. The next step of an invalid-bundle verdict, its `user_action.detail`, now reads "Edit the bundle as each validation error says: apply its suggested fix where it has one, after confirming an unsafe one".
- **The run routes refuse an invalid bundle with its validation verdict (Breaking)**: `POST /v1/execute` and `POST /v1/start` answer every refusal of the bundle while it loads, before any pipe runs, with the `422` `ValidateBundleError` problem document carrying the same located `validation_errors` `POST /v1/validate` gives, which STRICT disclosure keeps. A misspelled concept or a wiring mismatch used to answer a `500`, a TOML fault a `422` without items, and an unknown model the raw model-choice error. An entry pipe the bundle does not declare still answers its own `PipeNotFoundError`.
- **A failed run reports its root fault, located at the failing pipe (Breaking)**: a run failure's problem document carries the `error_type`, `title`, `type`, `error_domain` and status of the innermost Pipelex error rather than the run-level wrapper's, and its `detail` opens with `Pipe '<pipe>' failed (<entry pipe> → … → <pipe>):`, so a consumer branching on `error_type == "PipelineExecutionError"` branches on the root fault's type. A run the caller's own method refuses, such as a `PipeCondition` whose outcome is `fail`, a `PipeParallel` branch whose multiplicity does not fit its field, a step missing a required input or an inline model the deck does not define, answers a `422` with a `detail` STRICT disclosure keeps, where it answered `500` with `An internal error occurred.`. The completion webhook's `error` carries the same report.
- **Every load-time refusal is an item of the validation verdict (Breaking)**: `POST /v1/validate`, `POST /v1/resolve`, `POST /v1/codegen` and `POST /v1/build/*` answer any refusal of the submitted bundle, an unknown model and a pipe factory's refusal included, as a `200` `is_valid: false` verdict with a located item, where some of them escaped as a no-verdict problem document.
- **A failing dry run is one located `dry_run` item per failing pipe (Breaking)**: an invalid verdict's `validation_errors` carries one `dry_run` item per pipe whose dry run failed, with the `pipe_code`, `domain_code` and `source` of the innermost pipe that failed, where it carried a single message-only item for the whole sweep. Its message is the failure's own when that is caller-facing and its title otherwise, so a configuration fault met during a dry run no longer reaches the caller through the verdict.
- **`POST /v1/codegen` stamps `engine_version` `0.67.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.66.1` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **A verdict names no path on the server**: an item located inside a package a method depends on by address names the bundle by the package's address and its path inside it, and an item located in one of the server's own library directories carries no `source` or `field_path` naming its file, so STRICT disclosure no longer hands a caller a path on the host.

## [v0.28.1] - 2026-09-27

### Changed

- **Pinned `pipelex` 0.66.1**: up from `==0.66.0`, exactly. The release makes loading a library cheaper, since `are_classes_equivalent` settles most comparisons without generating a JSON schema, and it adds `load_from_crate(..., is_crate_prevalidated=True)`, which this server does not call. Nothing on the wire, in the configuration or in the logs moves.

## [v0.28.0] - 2026-09-25

### Highlights

**The runner's logs are structured.** Every line it writes to stderr is one JSON object with each value under a key of its own, the request id rides every record a request emits, the Pipelex runtime's included, and secrets are scrubbed before a line is written.

### Changed

- **The server's logs are structured, one JSON object per line on stderr (Breaking)**: `[runtime.log] sink = "json"` replaces the Rich console renderer, `console_log_target` moves to `stderr`, and `pretty_print_mode = "silent"` stops an operator pipe drawing its "Output of pipe" panel on the thread serving a request. Every value an error line carries — `route`, `status`, `error_type`, `error_domain`, `retryable`, `user_id` / `pipe_code` / `pipeline_run_id` when the request bound them, and `detail` on the failures this API authors itself — is a key of its own now rather than part of a `key=value` run inside the message, and `request_id` rides the runtime's request-scoped log context, so it lands on every record emitted during a request, including the ones Pipelex emits from inside a run. The message is a short sentence built only from the status and the error type, so no caller-supplied string reaches it and the API's own escaping is gone: the sink is what serializes a value now. A log query matching `event=api_error` as text has to move to the `event` field. The new `docs/logging.md` documents the line and every field on it. Uvicorn's own banner and access log are unchanged and still plain text.
- **Pinned `pipelex` 0.66.0 (Breaking)**: up from `==0.65.0`, exactly, the release that carries the structured-log seam the entry above rides on: named fields and the run-scoped log context, the `json` sink selected by `[runtime.log] sink`, the redaction of secrets before any sink sees a record, and Rich behind the `cli` extra, which this server's extras leave out. On this server's lines that means a credential echoed into `detail` reads `[REDACTED]`, a control character in a field's value reads as its printable escape (`\n` where a caller sent a newline), and a line logged inside a traced run carries `trace_id`, `span_id` and `trace_flags`; `docs/logging.md` says so. The `.pipelex/` config shipped here already sits at the schema that release migrates to, so no migration is required. One change reaches an operator beyond the logs: the S3 storage provider now signs links and reads and writes objects on the bucket's own regional host, `<bucket>.s3.<region>.amazonaws.com`, so a deployment whose egress rules allow S3 by hostname must allow `*.s3.<region>.amazonaws.com`. Nothing on the wire moves.
- **`POST /v1/codegen` stamps `engine_version` `0.66.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.65.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **A local image build no longer bakes the builder's own Pipelex overrides in**: `.pipelex/pipelex_override.toml` and `.pipelex/telemetry_override.toml` are untracked per-developer files, so CI never had them, but `make docker-build` copied whatever the developer had into the image — their storage backend, their log level, their telemetry credentials. A locally built image then behaved differently from the published one, with nothing in the diff to say so. `.dockerignore` excludes them; an operator still supplies overrides to a container by mounting them at `/root/.pipelex`.

## [v0.27.5] - 2026-09-25

### Changed

- **`POST /v1/validate` graphs a `method_ref` package's manifest entry pipe**: the valid arm's `graph_spec` is now drawn from the pipe `default_pipe_ref` names, so a package whose `METHODS.toml` names a `main_pipe` is graphed from that pipe rather than from its primary bundle's own `main_pipe`. A published method whose entry pipe only its manifest declares, which used to answer `graph_spec: null`, now carries its graph, and a manifest `main_pipe` the package does not resolve answers `null` rather than a graph of another pipe. Inline `mthds_contents` are graphed as before.
- **Pinned `pipelex` 0.65.0**: up from `==0.64.2`, exactly. The runtime's bundle-validator seam now takes the pipe to graph, which the `POST /v1/validate` change above rides on. The `.pipelex/` config schema did not move, so no migration is required.
- **`POST /v1/codegen` stamps `engine_version` `0.65.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.64.2` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **In-page links on the Pipe Validate docs page**: the page's topical sections are now headings, so the links to the effective entry pipe, the opt-in extras, sourcing submitted files, where validation runs and who the validation is done for land on their section instead of the top of the page, from that page and from Pipe Builder. The deployment resource note is back under where validation runs.

## [v0.27.4] - 2026-09-24

### Changed

- **Pinned `pipelex` 0.64.2**: up from `==0.64.1`, exactly, a patch release that keeps the message of an unknown model reference under strict error disclosure. A `/v1/validate` or run of a method naming a model the deck does not know now answers its 422 with the model that was named and the "Did you mean" suggestions, instead of "An internal error occurred.". No wire, config or OpenAPI change.
- **`POST /v1/codegen` stamps `engine_version` `0.64.2`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.64.1` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

## [v0.27.3] - 2026-09-24

### Changed

- **Pinned `pipelex` 0.64.1**: up from `==0.64.0`, exactly, a patch release whose runtime change keeps a test run's telemetry off the Pipelex Gateway stream and which moves its own exact pin to `mthds` 0.16.0, so the image now ships that version. Nothing on the wire moves — the committed `docs/openapi/pipelex-api.openapi.yaml` changes only in its `info.version` — and the `.pipelex/` config schema did not move, so no migration is required.
- **`POST /v1/codegen` stamps `engine_version` `0.64.1`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.64.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

## [v0.27.2] - 2026-09-24

### Added

- **`analytics_groups` on `POST /v1/validate` and `POST /v1/build/runner`**: both routes dry-run the submitted pipes, and that telemetry — the `pipe_dry_run` event and the dry runs themselves — is now attributed to the caller: the authenticated user and the request's optional `analytics_groups`, which follow the same rules as on a run and are refused with the same `422` `InvalidAnalyticsGroups`. Before this, every validation on a hosted deployment reported under one constant id per deployment.

### Changed

- **Pinned `pipelex` 0.64.0**: up from `==0.63.0`, exactly, because the caller a validation is done for is a required argument of the runtime's bundle-validator seam from that release on, and the runtime now carries a run's caller context as `extras`, which the `analytics_groups` wire field maps onto. Nothing else on the wire moves and the `.pipelex/` config schema did not move, so no migration is required.
- **`POST /v1/codegen` stamps `engine_version` `0.64.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.63.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

## [v0.27.1] - 2026-09-23

### Added

- **`analytics_groups` on `POST /v1/execute` and `POST /v1/start`**: a run request may carry an opaque mapping of group type to group key, such as `{"organization": "org_acme"}`, which the runtime stamps on every span of the run as `pipelex.run.analytics_groups` and which the deployment's own PostHog stream, in `identified` mode, attaches to each capture as PostHog groups. It follows the runtime's own rules — lowercase snake_case group types, group keys from `A-Za-z0-9_-`, at most five entries — and a mapping outside them is refused with a `422` whose `error_type` is `InvalidAnalyticsGroups`; omitting it leaves the run in no group.

### Changed

- **Pinned `pipelex` 0.63.0**: up from `==0.62.0`, exactly, for the run-scoped analytics groups and per-caller telemetry that `analytics_groups` rides on. A deployment reporting to its own PostHog or OpenTelemetry backend now sees each run under its caller — the run's `user_id` becomes the PostHog `distinct_id` and is written on every span as `pipelex.run.user_id` — while a single-tenant deployment, whose runs all carry the shared `single-tenant` id, keeps reporting under its configured identity. Nothing on the wire moves and the `.pipelex/` config schema did not move, so no migration is required.
- **`POST /v1/codegen` stamps `engine_version` `0.63.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.62.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **A run route's `422` names the extension field that failed**: every failure on `pipeline_run_id`, `callback_urls`, `orchestration_mode` or `storage_scope` used to answer `error_type` `InvalidCallbackUrls`, including a traversal in `storage_scope` on a request that carried no callback at all. An invalid `storage_scope` now answers `InvalidStorageScope`, an invalid `callback_urls` still answers `InvalidCallbackUrls`, and a failure on any other field, or on more than one at once, carries the generic `ValidationError`.

## [v0.27.0] - 2026-09-21

### Changed

- **Pinned `pipelex` 0.62.0**: up from `==0.61.0`, exactly, for the shipped model deck's move onto the models the Pipelex Gateway serves from Azure. Nothing on the wire moves — the committed `docs/openapi/pipelex-api.openapi.yaml` changes only in its `info.version` — and the `.pipelex/` config schema did not move, so no migration is required.
- **The vendored model deck resolves only to models the Pipelex Gateway serves from Azure (Breaking)**: this image serves the `.pipelex/inference/` tree it ships rather than the installed wheel's kit, and that deck had not been re-synced since v0.14.0, so every previous pin move left the roster untouched. Every default alias and preset keeps its name, but the language ladder is now the GPT-5.6 range — the premium tier and `@best-gpt` resolve to `gpt-5.6-sol`, the general and large-context tiers to `gpt-5.6-terra`, the small tiers to `gpt-5.6-luna`, where they previously resolved to `claude-4.7-opus`, `claude-4.6-sonnet`, the Gemini `*-latest` pair and `gpt-4o-mini` — and image generation's tiers resolve to `gpt-image-2` in place of `nano-banana` and `nano-banana-2`. `GET /v1/models` answers this deck, so its `aliases` and `waterfalls` change with it, and `$engineering-codebase-analysis` reaches its model through `@default-large-context-code` rather than a provider-named alias.
- **A deployment holding its own provider key must declare the new handles (Breaking)**: the Pipelex Gateway resolves them from the remote config it fetches at boot, so the default deployment needs nothing, but the vendored `backends/` rosters declare none of the GPT-5.6 range. Such a deployment still starts — `missing_presets_reaction` is `log`, and an alias satisfies the deck's membership check without its target being declared — and then answers `500` on the first `/execute` that takes a default tier. Declare the handles in the backend file, or keep the previous models by naming them in an `x_custom_llm_deck.toml`, which `pipelex update` never touches.
- **The vendored deck declares `temperature = 1` throughout (Breaking)**: every model in the GPT-5.6 range fixes its temperature at 1, so every preset states that value in place of one the worker would override while warning on every call, and `[llm.choice_defaults].default_temperature` is 1 for the same reason. Presets are therefore distinguished by their model tier and their reasoning effort alone, so `$writing-factual` and `$writing-creative` now issue the same call. A method that needs a temperature of its own must write an inline LLM settings table — `model = { model = "gpt-4o", temperature = 0.8 }`.
- **The vendored Gateway roster reference agrees with the deck again**: `backends/pipelex_gateway_models.md` and its plain twin are generated from the served remote config and had never been refreshed since this repo was created, so they advertised `gpt-5.2` and carried no `gpt-5.6-*` handle at all while the deck resolved every tier to one. Both are re-synced, so the reference an operator opens to pick a handle now matches what the deck runs on.
- **`POST /v1/codegen` stamps `engine_version` `0.62.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.61.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **The vendored deck no longer aliases a handle no enabled backend declares**: `@best-claude` and `@default-premium` both resolved to `claude-4.7-opus`, which the vendored `backends/anthropic.toml` does not declare — it stops at `claude-4.6-opus`. The re-synced deck removes the dangling target.

### Removed

- **`best-claude`, `best-gemini` and `best-mistral` are gone from the vendored deck (Breaking)**: an alias naming a provider cannot honestly resolve to a GPT model, and the image deck's `best-gemini` goes with them. A method referencing one now fails validation with the usual alias-not-found error; declare it in an `x_custom_llm_deck.toml` to keep it.

## [v0.26.1] - 2026-09-20

### Changed

- **Pinned `pipelex` 0.61.0**: up from `==0.60.0`, exactly, for a set of fixes to the way generated and remote images are fetched and stored, which are the changes that actually reach a run here. Nothing on the wire moves — the committed `docs/openapi/pipelex-api.openapi.yaml` is unchanged — and the `.pipelex/` config schema did not move either, so no migration is required. The model roster is unaffected as well: 0.61.0 revises the handles in pipelex's own bundled kit, but this server reads the vendored `.pipelex/inference/` it ships rather than that kit, so `GET /v1/models` answers exactly what it answered under 0.60.0.
- **`POST /v1/codegen` stamps `engine_version` `0.61.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.60.0` no longer matches until it is regenerated. `POST /v1/build/runner` carries the same stamp.

### Fixed

- **A generated image is stored and reported under its real media type**: `pipelex` resolved a generated image's mime type to mint its storage key but never handed that type to the storage provider, so S3 stored every generated image untyped and served it back as `binary/octet-stream`; an image fetched from a remote URL now also keeps the type that URL served instead of falling through to a hardcoded `image/jpeg`. A caller that trusts the `mime_type` on an image a run returns, or that serves the stored object straight to a browser, now gets the type the bytes actually are.
- **A remote image that fails to download no longer fails the whole run**: the upstream fallback for an unreachable remote image — log the warning, keep the URL — guarded on exception types the fetch never raised, so a 404 or a timeout on an image input propagated out and failed the run instead. A fetch given no explicit timeout also had no timeout at all, leaving a hanging server to block the caller indefinitely. Both are fixed in `pipelex` 0.61.0 and `POST /v1/execute` inherits them.

## [v0.26.0] - 2026-09-19

### Changed

- **Pinned `pipelex` 0.60.0**: up from `==0.59.0`, exactly, so a stuff on the wire names its concept instead of carrying its definition. The release also corrects `PINNED_NATIVES_MTHDS_VERSION`, which labelled the engine's pinned native set `1.0.0` where the standard pins it at `2.0.0`. It brings `mthds` 0.15.0 in with it, and the `.pipelex/` config schema did not move, so no migration is required.
- **A returned stuff names its concept by ref (Breaking)**: every working memory `POST /v1/execute` returns now spells each stuff as `{"concept": "<domain>.<Code>", "content": …}` instead of carrying the whole `Concept` object with its `description`, `structure_class_name` and `refines`, which is what the standard's I/O contract asks for — a stuff names its concept and the definition stays in the library the method loads. The committed `docs/openapi/pipelex-api.openapi.yaml` is regenerated to match: `Stuff.concept` is now a `string` where it was a `$ref` to `Concept`. A caller that read `concept.code`, `concept.domain_code` or `concept.structure_class_name` off a returned stuff must read the ref string and resolve it against the method's own definitions, and a caller that validated a response back into a typed `Stuff` can no longer do so, because the definition no longer travels with the data.
- **`POST /v1/codegen` stamps `engine_version` `0.60.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.59.0` no longer matches until it is regenerated.

### Fixed

- **`make pylint` lints `api/`**: the target, which `make check` runs, linted the installed `pipelex` package in `.venv` instead of this repository's own code, so `api/` was never checked by pylint. It now lints `api` and `tests`.

## [v0.25.0] - 2026-09-16

### Changed

- **Pinned `pipelex` 0.59.0**: up from `==0.58.0`, exactly, so a run no longer renders every traced input and output to Rich text and HTML on the execution path, which on the hosted runner happened on the Temporal worker's workflow thread. The release also fixes the "Output of pipe" panels hanging a run in `poor` pretty-print mode on a narrow headless console, and escapes every `<` in the graph and stuff viewer pages. It adds `pretty_print_mode` (`rich`, `poor` or `silent`) under `[runtime.log]`, which this server leaves at its `rich` default.
- **The graph spec's `IOSpec` no longer carries `data_text` or `data_html` (Breaking)**: `pipelex` 0.59.0 removes the text and HTML renderings of traced data, so both fields are gone from every graph spec the run routes return, and the committed `docs/openapi/pipelex-api.openapi.yaml` is regenerated to match. A graph spec saved by an earlier version is refused when read back. The settings that asked for those renderings, `stuff_text_content` and `stuff_html_content` under `[interpreter.pipeline_execution.graph.data_inclusion]`, no longer exist and boot rejects them, so they are removed from this server's `.pipelex/pipelex.toml`; an operator running it against their own `.pipelex/` must run `pipelex migrate` or delete the two keys by hand.
- **A remote input is checked for syntax only (Breaking)**: an http(s) URL on a `Document` or `Image` input is refused before the run with `PipelineInputUrlInvalidError`, answered as a 422, only when it does not parse. Whether the resource exists is no longer checked up front: the operator that fetches it raises `RemoteFileFetchError`, an `INPUT`-domain error naming the URL and the answer it got, in place of a raw `httpx` error. Those fetches now identify themselves as `Pipelex/0.59.0`, without the `(https://pipelex.com)` suffix. A local file path must still exist before the run starts.
- **`POST /v1/codegen` stamps `engine_version` `0.59.0`**: the stamp is the pinned `pipelex` version, so a `codegen.lock` committed against `0.58.0` no longer matches until it is regenerated.

## [v0.24.0] - 2026-09-14

### Changed

- **License (Breaking)**: `pipelex-api` is now licensed under the Elastic License 2.0 (ELv2) instead of MIT: `LICENSE` names Evotis S.A.S. as the copyright holder, the package metadata declares the SPDX expression `Elastic-2.0` in place of the MIT license classifier, which makes hatchling 1.27 or later a requirement for building from source, the OpenAPI contract the server publishes carries `info.license` `Elastic-2.0` (the committed `docs/openapi/pipelex-api.openapi.yaml` is regenerated to match, its summary now calling the runner source-available), and the Docker image's `org.opencontainers.image.licenses` label reads `Elastic-2.0`; every earlier version and Docker image tag, up to and including v0.23.0, stays under MIT. ELv2 is source-available: you may run `pipelex-api` for your own team or company, on your own infrastructure or in your own cloud account, while its main limitation rules out offering others a hosted API or runner that executes methods, whether they send the methods themselves or pick them from a catalog you make available. `LICENSE` carries the full terms, including its conditions on notices and redistribution, and the [license page](https://docs.pipelex.com/latest/license/) explains how Pipelex reads them.
- **Pinned `pipelex` 0.58.0**: up from `==0.57.0`, exactly, for the relicense of `pipelex` to the Elastic License 2.0, which this server now depends on under that license. The runtime did not change and neither did the `.pipelex/` config schema, so no migration is required.
- **`POST /v1/codegen` stamps `engine_version` `0.58.0`**: the stamp is the pinned `pipelex` version, so every generated artifact header and every `codegen.lock` this release emits differs from the previous one, and a lock committed against `0.57.0` no longer matches until it is regenerated.

## [v0.23.0] - 2026-09-08

### Added

- **`POST /v1/execute` carries the run's I/O artifacts beside its execution graph**: `pipe_output.pipe_io_artifacts` groups the `pipe_io_contracts`, `input_form` and `output_form` that `/validate` produces, keyed by namespaced `pipe_ref` over the run library's own pipes, so a consumer rendering a run's graph can describe a data node from the run itself rather than pairing that graph with a validation of some other bundle text. It is `null` unless the run generated a graph with `graphs_inclusion.graphspec_json` on, and `pipe_io_artifacts_error` carries the message when the build ran and failed.

### Changed

- **Pinned `pipelex` 0.57.0**: up from `==0.56.0`, exactly, for the `PipeIOArtifacts` carrier and its SPI transport that the `/v1/execute` addition above reads back onto the public wire. The `.pipelex/` config schema did not move, so no migration is required.
- **The normalized crate is stamped `mthds_version: "2.0.0"` (Breaking)**: `pipelex` 0.57.0 moves to `mthds` 0.14.0, whose `MTHDS_STANDARD_VERSION` was cut from `1.0.0`, so every crate `POST /v1/resolve` emits and `POST /v1/build/runner` normalizes carries the new stamp and a consumer comparing against `1.0.0` has to move. Crate fingerprints are unaffected — `mthds_version` is excluded from the hashed payload by design — but a `METHODS.toml` pinning the old major, such as `^1.0.0`, now warns where it did not before. The MTHDS Protocol version is unchanged at `0.6.0`.
- **`POST /v1/codegen` stamps `engine_version` `0.57.0`**: the stamp is the pinned `pipelex` version, so every generated artifact header and every `codegen.lock` this release emits differs from the previous one, and a lock committed against `0.56.0` no longer matches until it is regenerated.
- **OpenAPI artifact regenerated** for the new `PipeIOArtifacts` schema and the `pipe_io_artifacts` / `pipe_io_artifacts_error` fields it brings to `PipeOutputWire`, both inherited from pipelex's `PipeOutput` rather than declared here. Nothing was removed and no type loosened, but `PipeOutputWire` publishes `additionalProperties: false`, so a strictly-validating client generated from the previous artifact rejects the added fields until it is regenerated.

### Fixed

- **The `/execute` response reference documents its execution graph**: `docs/pipe-run.md` listed `tokens_usages` and `usage_assembly_error` under `pipe_output` but never `graph_spec` or `graph_assembly_error`, so a caller reading the reference had no way to learn the graph was on the wire at all. Both are documented now, beside the `pipe_io_artifacts` pair added above, each with the configuration setting that actually gates it.
- **The `/validate` reference documents the `output_form` view**: `docs/pipe-validate.md` still described `input_form` as the only supported `views` token and carried no field reference for `output_form`, which has been wrong since that view shipped in v0.22.0.

## [v0.22.0] - 2026-09-03

### Added

- **`POST /v1/validate` carries the output-form descriptor, under the new `views` token `output_form`.** The valid arm gains a second opt-in structured view beside `input_form`, with identical mechanics: a supported token attaches a same-named top-level field, keyed exactly like `pipe_io_contracts`; without the token the field is absent and the body is byte-identical to a request that omits `views`; an unknown token is still lenient-ignored rather than a 422.

  Two tokens rather than one, because they answer separate questions — a caller building a fill-in form wants the inputs, a caller rendering a result or registering a tool signature with a return type wants the output — and neither should pay for the other. Like `input_form`, the field is a canonical report field re-declared with a default here so the wire gate keeps it out of the published schema's `required` set, and it rides the valid arm only: it derives from a crate an invalid bundle never assembled.

  The payload's **schema** needs no token: it rides `pipe_io_contracts[…].output.json_schema`, which the standard added in the same version. That pairing is the point — the descriptor states what the output IS, the schema names the property its payload arrives under, and a consumer holding one but not the other is back to inferring the other from a value.

- **`POST /v1/validate` reports the effective entry pipe.** The valid arm carries a new wire-only extra, `default_pipe_ref` (string | null): the qualified `domain.pipe_code` a caller gets by omitting the pipe selector — the pipe a selector-less run of that same request would execute. On a `method_ref` request it is the fetched package manifest's `main_pipe`, qualified against the closure; otherwise, and when the manifest declares none, it is the closure's primary blueprint's `main_pipe` qualified by its domain. It is `null` when no entry pipe is determined: no blueprint declares `main_pipe`, or a manifest names a pipe the closure does not declare or declares in several domains — cases in which a selector-less run by that address would fail to resolve it too. The field closes a real gap for validate-by-address: the canonical report is manifest-blind (`bundle_blueprint` is the batch's primary blueprint), so a package whose `METHODS.toml` entry differs from, or exists without, a bundle-level `main_pipe` validated with a report from which a consumer could only derive the wrong entry pipe, or none. It states the **run** default rather than the `/build/*` routes' stricter one: a closure whose domains each declare a `main_pipe` is refused by `/build/*` but runs happily, so the field names the pipe that would run. It rides the valid arm only — the invalid arm assembles no library. See `docs/pipe-validate.md` → "The effective entry pipe".

### Fixed

- **The per-pipe build routes honor a fetched package's manifest `main_pipe`.** `POST /v1/build/{inputs,output,runner}` with an address-form `method_ref` and no `pipe_ref` used to answer `422` ("the closure declares no `main_pipe`") whenever the package's domains declared none themselves — even though its `METHODS.toml` named an entry pipe, which the run routes already honored. The tooling routes now default the pipe with the run routes' precedence: the request's `pipe_ref`, then the fetched manifest's `main_pipe`, then the closure's own declared `main_pipe` (still a `422` when that declares none, or several). Inline `files[]` requests carry no manifest and behave exactly as before. A manifest `main_pipe` naming a pipe the closure does not contain is a `422` that says where the selector came from. `/resolve` and `/codegen` select no pipe and are unchanged. The OpenAPI artifact's `pipe_ref` / `requested_pipe_ref` descriptions are regenerated to say so.

## [v0.21.0] - 2026-08-29

### Added

- **`method_ref` on the wire — run a published method by address.** `POST /v1/execute` and `POST /v1/start` accept `method_ref` as a third run source, mutually exclusive with `mthds_contents` and with a `files`/`bundle_b64` bundle. An **address-form** reference — `github.com/<owner>/<repo>`, an optional package selector, an optional `@<tag>` (tags only; branch names are refused) — is fetched server-side, the package located by manifest identity, and its files materialized as the run's library. The entry pipe defaults to the manifest's `main_pipe`; `pipe_code` overrides it. The `/execute` response, the `/start` ack, and the run logs carry `method_provenance` — the resolved `{address, tag, commit_sha}` — so a run by reference is always attributable to an exact commit. See `docs/pipe-run.md` → "Running a method by address".
- **`/v1/validate` accepts `method_ref` natively.** `mthds_contents` is now optional there: exactly one of `mthds_contents` or `method_ref` selects what is validated. A fetched package's real relative file names feed `mthds_sources`, so per-file attribution in `validation_errors[]` names the package's own files. Selector-resolution failures (parse, fetch, no package found) are non-2xx `problem+json` — never an `is_valid: false` verdict.
- **Tooling routes resolve address-form `method_ref`.** `POST /v1/resolve`, `POST /v1/codegen`, and `POST /v1/build/{inputs,output,runner}` now resolve an address-form `method_ref` through the same fetch path (only `.mthds` data travels — a package's Python never loads on these routes). The **registry form** (any non-address reference) keeps the `501` `MethodRefNotSupported` until a method registry exists.
- **SHA-keyed clone cache.** Fetched repositories are cached on disk per resolved commit SHA — a `git ls-remote` pre-resolution turns the reference into a SHA before any clone, so a cached commit is never re-cloned and a moved tag always fetches fresh (never cached by tag alone). The cache is bounded by count, total bytes, and age, tunable via `METHOD_CACHE_DIR`, `MAX_METHOD_CACHE_CLONES`, `MAX_METHOD_CACHE_TOTAL_KIB`, and `MAX_METHOD_CACHE_AGE_HOURS` (see `docs/configuration.md`).
- **Execution-locus security gate for fetched packages.** On a deployment that is not sandbox-hosted, a fetched package shipping any `.py` is refused with `403` `CustomCodeRequiresSandbox`. On a sandbox-hosted deployment, PipeFunc `.py` is accepted (captured as text, executed in the sandbox), but a package declaring Python structure classes is always refused with `403` `MethodStructuresRefusedError` — structures would import into the runner's own process.
- **Distinct error surface for `method_ref` failures.** `MethodRefParseError`, `MethodFetchError`, `MethodPackageAmbiguityError`, and `MethodPackageTooLargeError` map to `422`; `MethodPackageNotFoundError` to `404` (its detail lists the packages the repository does contain); `MethodStructuresRefusedError` to `403` — each an RFC 7807 `problem+json` document. Documented in `docs/error-responses.md`.

### Changed

- **Pinned `pipelex` 0.55.0** (up from `==0.54.0`, exactly). It brings the `pipelex.methods` package — the reference grammar, the git fetcher with its bounds, package location by manifest identity, and the structure-refusal gate — that this release's `method_ref` support is built on. The `.pipelex/` config schema did not move, so no migration is required.
- **OpenAPI artifact regenerated** for the new surface: the `method_ref` request fields, the `method_provenance` response fields (including the new `PipelexApiStartResponse`), and the per-route `403`/`404`/`501` problem responses.

## [v0.20.0] - 2026-08-28

### Changed

- **Pinned `pipelex` 0.54.0.** Up from `==0.53.0`, exactly; it brings `mthds` 0.11.1, which now types the input-form descriptor and the pipe I/O contract models for the whole stack. The `.pipelex/` config schema did not move, so no migration is required. Two upstream changes reach callers of this server:
  - **The `input_form` view's published schema is now the standard's kind-discriminated union (Breaking for generated clients).** `PipeInputFormDescriptor.fields` items are a `oneOf` over one closed model per field kind — `TextField`, `ProseField`, `DateField`, `NumberField`, `BooleanField`, `EnumField`, `DocumentField`, `ImageField`, `ObjectField`, `ListField`, `UnknownField` — discriminated on `kind`, with a parallel `*Item` family for list items. The flat `InputFormField` and the `FieldKind` enum leave the artifact, so a client regenerated from `docs/openapi/pipelex-api.openapi.yaml` loses those type names and gains the per-kind ones. The JSON on the wire is unchanged; hand-written clients are unaffected. The arms publish their full closed shapes (`additionalProperties: false`, real properties), as `mthds` 0.11.1 fixed the serializer annotation that previously erased them to opaque objects.
  - **A count of one is strictly singular (Breaking).** Upstream, `Concept[1]` is universally the single form: a `[1]` input takes the value itself and refuses a list, a `[1]` output produces one object rather than a one-item list, and `Concept[0]` is rejected at validation time. Methods executed through this server that relied on `[1]` list behavior must be updated.
- **OpenAPI docs** — Regenerated `docs/openapi/pipelex-api.openapi.yaml` for the pin. Beyond the `input_form` union above, four previously opaque schemas — `ConceptBlueprint`, `ConceptStructureBlueprint`, `ConstructBlueprint`, `InputSlotBlueprint` — now publish their real closed shapes instead of `{"additionalProperties": true}`, another consequence of the same upstream serializer fix.

### Added

- **Contract test for the `input_form` union.** `tests/unit/test_openapi_contract.py` now pins that `PipeInputFormDescriptor.fields` is discriminated on `kind` with exactly the standard's kind set, that every arm is a published closed schema with real properties, and that the flat `InputFormField`/`FieldKind` never resurface — so an upstream regression to the flat or opaque shape fails here instead of shipping silently.

## [v0.19.0] - 2026-08-26

### Added

- **New validation error type** — Added `input_presence_vacuous` to `PipeValidationErrorType`, an advisory lint that warns when a required method input points to a concept with no required fields. It is scoped to the bundle's declared `main_pipe`. This does not affect `is_valid`, but consumers performing exhaustive matches over the enum must handle the new member. (Breaking)

### Changed

- **Dependency** — Pinned `pipelex` to `0.53.0` (up from `0.52.0`). The `.pipelex/` config schema did not move, so no migration is required.
- **Warning output** — Intent-hint warnings are now capped at five unknown-hint-key findings per site, collapsing the rest into an `...and N more` item; hint keys or intent words longer than 60 characters are elided with an ellipsis.
- **OpenAPI docs** — Regenerated `docs/openapi/pipelex-api.openapi.yaml` to include the new `PipeValidationErrorType` member and updated docstring references (moved from `pipelex.pipeline.optionality_warnings` to `pipelex.pipeline.advisory_warnings`).

### Fixed

- **`.mthds` parsing** — An empty `[concept.X.structure]` table now parses as an object with no fields instead of being described as prose refining `native.Text`.
- **Python class reflection** — Registered Python classes declaring no fields now reflect as empty objects rather than `unknown`.
- **Domain locators** — Hierarchical domains (e.g., `legal.contracts`) are now split at the last dot rather than the first when building an advisory warning's locator, so the locator names the correct domain.

## [v0.18.0] - 2026-08-24

### Added

- **New `views` parameter on `/v1/validate`.** `ValidateRequest` now accepts `views: list[str]` (default `[]`), the structured-view counterpart to `render`. Tokens are resolved leniently and as a set: each is matched independently against the supported set, unknown or unsupported tokens are silently dropped and never trigger a 422, and order and duplicates do not matter. `input_form` is the only supported token today, attached exclusively to the valid arm of the response. The two lists are independent — a request may carry both, and a token does not cross axes.
- **Documentation.** `docs/pipe-validate.md` now covers the new `views` parameter, the previously undocumented `render` parameter (including the lenient, set-based, mutually independent mechanics they share), the `orchestration_mode` override, and the opt-in response fields (`input_form`, `rendered_markdown`).
- **Tests.** `tests/unit/test_validate_views.py` pins the gate: absent by default on both arms, present on the valid arm when requested, never on the invalid arm even when requested, unknown tokens ignored rather than rejected, and `views` / `render` resolving independently. `tests/unit/test_protocol_parity.py` gained the complementary pair — a default call omits `input_form`, and an opt-in call matches the local canonical report exactly.

### Changed

- **`input_form` is now an opt-in structured view on `/v1/validate` (Breaking).** v0.17.0 shipped it unconditionally on every valid verdict, as a side effect of the `pipelex` 0.52.0 pin rather than a decision. It is now gated: a caller that does not ask no longer receives it, so the high-frequency consumers — editor hooks, CI gates, agent loops — stop paying for a form they discard. An empty or unknown `views` list changes nothing either, so the default body is byte-identical to a request that omits the field entirely. Callers that need it must send `{"views": ["input_form"]}`, which returns exactly what v0.17.0 returned unconditionally. In the published OpenAPI artifact, `input_form` leaves `ValidReport`'s `required` set to reflect the opt-in wire behavior; the canonical report still requires it internally, so a backend that forgets to derive it fails loudly rather than shipping an empty view.

## [v0.17.0] - 2026-08-24

### Added

- **A source-less request now names the extension args this deployment does not handle.** A body that carries no run source this server understands, but at least one key it does not handle, gets a `422` naming those keys instead of the generic precondition text. The canonical case is a hosted client pointed at an open-source runner: `{"method_id": "mt_…"}` used to produce an obscure "pipe_code and mthds_contents cannot both be empty", and now explains that a hosted-only selector must be sent to the hosted API, which resolves it into a run source before any runner sees the request. The wording is deployment-neutral on purpose — the server reports what *it* handles rather than asserting anything about the caller's topology. Keys it does handle (`pipeline_run_id`, `callback_urls`, `orchestration_mode`, `storage_scope`, and the legacy singular `mthds_content`) are never named as unhandled, and a source-less body carrying only those keeps the base guidance. No wire-shape change and no OpenAPI artifact change.

### Changed

- **Pinned `pipelex` 0.52.0 (Breaking).** Up from `==0.50.0`, exactly, and `mthds` follows to 0.8.2 transitively. No code changed on this side — the report is assembled inside pipelex — but the published `/v1/validate` contract moved in several places:

  - `ValidReport` gained a **required** `input_form`, mapping each `pipe_ref` to a `PipeInputFormDescriptor`, so a caller can render a form from the verdict alone instead of reverse-engineering one from the emitted JSON Schema. The closed `FieldKind` vocabulary arrives with it. A consumer deserializing the report strictly must add the member.
  - `PipeInputContract.optional` (boolean) is **replaced** by `presence`, a three-valued `PresenceMarker` — `plain`, `optional` (`?`) or `force` (`!`) — so a `!` use-site assertion is now visible where it previously read as an ordinary required slot. Read `presence != "plain"` where you read `optional == true`.
  - `IOMultiplicity` gained `fixed`, and both the input and the output contract now carry `multiplicity`, with an `item_count` present exactly when it is `fixed`. A fixed-count list slot (`Concept[N]`, for `N > 1`) used to report `variable` and lose its count. Any consumer branching on `variable` to mean "a list" must accept `fixed` as a list too.
  - Every pipe blueprint's `inputs` map widened from `string` values to `string | InputSlotBlueprint`.
  - `PipeValidationError.error_type` gained the advisory `HintLintErrorType` members (`hint_unknown_key`, `hint_unknown_intent`, `hint_inapplicable_intent`). They ride the report's `warnings` and never make a verdict invalid, but an exhaustive `match` over the union has to handle them.

  Two authoring changes reach anyone posting `.mthds` content: an unknown key in a concept structure-field table is now rejected at parse instead of silently dropped, and `required = true` may no longer be paired with `default_value`. The `.pipelex/` config schema did not move, so no migration is required.

- **Four schemas in the OpenAPI artifact went opaque, upstream.** `ConceptBlueprint`, `ConceptStructureBlueprint`, `InputSlotBlueprint` and `InputFormField` now publish as a bare `{"type": "object", "additionalProperties": true}`. This is a side effect of how intent hints are serialized, not an intentional loosening: each model gained a `@model_serializer(mode="wrap")` returning `dict[str, Any]` in order to drop absent `hints` rather than emit `null`, and pydantic derives a model's **serialization** schema from that annotation — which is the one FastAPI publishes. The validation-mode schema is still complete and still `extra="forbid"`. The artifact is regenerated as-is rather than hand-patched, and the issue is filed upstream.

### Fixed

- **A source-less run request no longer slips through on an unknown key.** `RunRequest.validate_request` used to **waive** the "at least one of `pipe_code` / `mthds_contents` / method bundle" precondition whenever the body carried any key outside the declared fields, on the theory that an extension might be the method selector. That theory is obsolete under the layered extension policy written down in the Pipelex workspace spec `docs/specs/pipelex-platform-api.md`: an extension-borne method selector is resolved by the layer that owns it *before* the request reaches this server, so a body arriving here with no run source is an error whatever else it carries. The waiver was also already dead on every live path — the run routes build the model through `RunRequest.from_body`, which copies the declared fields only, so unknown keys were stripped before the validator ever saw them. Removing it is therefore behaviour-neutral, and the substantive change is the message described above. A body that does have a real run source still accepts unknown extension keys untouched: the model stays extension-open.

## [v0.16.0] - 2026-08-20

### Changed

- **Built on `pipelex`'s `RunMetadata` split (Breaking).** `JobMetadata` moved its run-constant half — `user_id`, `pipeline_run_id`, `storage_scope`, `request_id` — into a nested `RunMetadata`, reached as `job_metadata.run_metadata.*`. This server's own surface is untouched: `pipeline_run_setup` still takes those four as flat keyword arguments and builds the `JobMetadata` itself, so no route, request model or response shape changes. Only the test doubles that construct a `JobMetadata` directly had to follow.

  The wire contract is unchanged, including the published OpenAPI artifact — see below for the one place that was nearly not true.

- **Pinned `pipelex` 0.50.0.** Up from `==0.47.0`, an exact PyPI pin as this dependency is meant to be expressed. It was briefly a `[tool.uv.sources]` git rev while `RunMetadata` was unreleased; that is gone, and with it the transitive override a source imposes.

  The jump crosses three releases, so it picks up more than the `RunMetadata` split: `PipeFactoryErrorType` / `PipeValidationErrorType` moved to `pipelex.validation_error_types` (0.49.0), and the import follows them.

### Fixed

- **`PipeOutput` gained a field upstream, and `test_openapi_contract` earned its keep.** `pipelex` first carried the run's job on `PipeOutput` as a **model field**. `PipelexApiExecuteResponse.pipe_output` references `PipeOutput`, and `/v1/execute` returns `response.model_dump(...)` — so that field published `user_id`, `request_id`, `otel_context` and `trace_context` into this public API's response body **and** its committed OpenAPI schema.

  `test_execute_publishes_the_tokens_usage_wire_records` asserts `{"LLMTokensUsage", "ImgGenTokensUsage", "JobMetadata"}.isdisjoint(schemas)`, and it failed. Upstream now carries the value as a private attribute behind a property — readable by a transport resolving a storage scope, absent from `model_dump`, `model_json_schema` and therefore the wire. **No change was needed on this side**, which is the right shape of fix: the artifact was never supposed to have to trim it.

## [v0.15.1] - 2026-08-20

### Changed

- **Pinned `pipelex` 0.48.0.** Up from `==0.47.0`, exactly. A quiet bump for this server: nothing in it reaches the wire, the committed OpenAPI artifact is unchanged, and no tracked configuration moved. The release is upstream test infrastructure — a canonical MTHDS test corpus that now ships inside the `pipelex` wheel at `pipelex.test_extras.mthds_corpus`, with a loader API (`iter_entries()`, `get_entry()`) for selecting fixtures by tag, execution tier, validity and granularity.

  Worth knowing rather than acting on today: that corpus exists so consumers stop keeping their own copies of language-level `.mthds` methods, which is a duplication this repo's own tests currently have. Adopting it is a separate change, and this pin is what makes it available.

## [v0.15.0] - 2026-08-20

### Added

- **`storage_scope` — the runner is told where to write instead of deriving it.** `pipeline_run_setup` requires it, and this server never passed it, so every `/start` and `/execute` against a current `pipelex` died with `TypeError: pipeline_run_setup() missing 1 required keyword-only argument: 'storage_scope'` — a 500 from the runner and a 502 at the caller, on the happy path.

  It arrives in the **body**, not a header, because it is data rather than identity: the runner needs to know where to write, not who to trust. A multi-tenant host computes it where it knows its own tenancy (hosted Pipelex sends `<org_id>/<method_id>/<run_id>`) and this server treats it as an opaque prefix, composing its own leaves (`assets/`, `results/`, `payloads/`) onto it. Validated at the wire by `validate_storage_scope`, so a traversal is a `422` naming the field rather than a `500` from deep inside the run — the runtime seam validates too, so this is a second gate, not the only one.

  `_validate_extras` is a key ALLOWLIST rather than a passthrough, so the field had to be added there too — a key missing from it is dropped with no error, and the run would have written under the fallback prefix while answering `202`. Covered by tests that assert the constructor kwarg, not just the status code.

  **Omitted, a run is scoped to the caller's own id** — never a shared constant. That is the safe default for a single-tenant deployment, and it keeps a multi-tenant deployment that forgets to send a scope isolating its callers instead of pooling them. A shared literal here would be the `anonymous/` bug in a new spelling.

### Fixed

- **`uri_format` in the shipped `.pipelex/pipelex.toml` renders the filename only.** The placeholder set narrowed again: the storage prefix (`{storage_scope}` plus the `generated/` leaf) is composed in code so a config cannot omit it, leaving `{hash}` and `{extension}`. A config still naming `{storage_scope}` is refused at boot.

- **Every run's output was written to `<scope>/results/results/`.** The delivery target was built as `StorageTarget(key_prefix="results")`, from the layout where the executor composed `{user_id}/{key_prefix}{pipeline_run_id}` and the caller supplied the leaf. It now composes `{storage_scope}/{key_prefix}results` — the runtime owns the `results/` leaf — so passing it here applied it twice. Nothing failed: the write succeeded, the run reported COMPLETED, and only a later reader of `<scope>/results/` found an empty prefix, which is exactly where the hosted platform's run reconciler looks. `key_prefix` remains the caller's slot for an extra level between the scope and the leaf; it is not where the leaf comes from.

- **`uri_format` in the shipped `.pipelex/pipelex.toml` still used the removed `{primary_id}` / `{secondary_id}` placeholders.** The supported set is now `{extension}`, `{hash}`, `{storage_scope}`, so config validation raised `StorageConfigError` at fixture setup and **every** test in the suite errored — a total red that looked like a code failure and was purely stale config. Migrated to `{storage_scope}/{hash}.{extension}`, matching the kit default in `pipelex`.

### Changed

- **Pinned `pipelex` 0.47.0 (Breaking, and it moves this deployment's own config files).** Up from `==0.46.4`, exactly. 0.47.0 is the release that makes the runtime *told* where a run's bytes go instead of deriving it from who ran it, which is what the `storage_scope` work above is built on — so this server cannot run on 0.46.x at all: `pipeline_run_setup` now requires `storage_scope`, and calling it without one is a `TypeError` on the happy path, not a degraded mode.

  **It also narrows `uri_format`, and a config that has not moved fails at boot rather than at first use.** The format now renders the FILENAME only: the prefix is composed in code as `{storage_scope}/generated/`, so `{storage_scope}` is no longer a supported placeholder and `{primary_id}` / `{secondary_id}` stay retired. The tracked `.pipelex/pipelex.toml` here is already on `{hash}.{extension}`; **anyone running this server against their own `.pipelex/` must make the same edit**, or boot raises `StorageConfigError` naming the offending placeholder and listing the supported set. There is deliberately no migration for it — a value-domain narrowing on a free string can never be proven stale from the schema, so the failure is loud at boot instead of a silent rewrite of a value an operator may have chosen.

  Generated bytes consequently land under a `generated/` leaf beside `assets/` (what the caller supplied) and `results/` (the delivered envelope), rather than loose at the root of the scope.

- **Breaking: the `anonymous` caller no longer exists.** `ANONYMOUS_USER_ID` is gone, along with every branch that produced or tolerated it. It was reached by *fallback*: `_get_user_id` returned the literal `"anonymous"` whenever no identity had been established, and that string became the first path segment of every storage key the run wrote. A deployment serving many callers therefore put all of them in one namespace where each could read the others' outputs — and it looked like a working request the whole way through. A silent multi-tenant collision is the worst possible failure for a fallback to produce.

  Two changes replace it.

  **`TRUST_FORWARDED_IDENTITY_HEADERS=true` now rejects a request with no forwarded id (`401`).** Turning that flag on is a deployment asserting *"a proxy in front of me authenticates every caller"*. A request arriving without the header means that proxy is absent, misconfigured or bypassed, and continuing under a shared owner is exactly the degradation this removes. Previously both an absent header and the literal `anonymous` were read as "the proxy says this one is anonymous" and let through. **This is the hosted configuration**, so on a hosted deployment an unidentified request is now impossible rather than merely unlikely.

  **A deployment that declares no user model gets a named single tenant, not an unknown caller.** `AUTH_MODE=none` without a trusted proxy, or the shared static `api_key`, establishes no per-caller identity *by configuration* — that is one tenant, and `SINGLE_TENANT_USER_ID` names it. This is not the old sentinel renamed: nothing falls back to it, it is used only where the deployment has said it has no users, and `verify_jwt` refuses a token claiming it (so an authenticated caller on a server that *does* have users cannot land in that namespace).

### Removed

- **`POST /v1/upload` and `POST /v1/resolve-storage-url` are gone (Breaking).** Both were explicitly non-contract — neither the MTHDS Protocol nor the Pipelex API extensions ever included them, and both carried a "slated for replacement by the storage redesign, do not build new integrations on it" notice in their descriptions. That redesign has landed, and the routes moved to the hosted platform.

  They could not stay. Both keyed S3 objects by the caller's `user_id` (`{user_id}/assets/{uuid}.{ext}`) and authorized a read by comparing that first path segment against the requester — an ownership model with no notion of a team. This server has no organization concept to fix it with, which is precisely why the routes belong on the hosted side, where membership is already resolved before the request arrives.

  A self-hoster who was using them needs their own upload path. The storage *provider* is untouched: `get_storage_provider()`, `pipelex-storage://` URIs and everything the runtime does with them work exactly as before — only the two HTTP routes are removed. `ErrorType.INVALID_URI`, `UPLOAD_FAILED` and `PRESIGN_FAILED` are removed with them, and `api.security.is_safe_user_id` stays (the pipeline routes use it).
## [v0.14.0] - 2026-08-18

### Changed

- **Pinned `pipelex` 0.46.4 (Breaking, and it moves this deployment's own config files).** Up from `==0.45.0`, exactly. 0.46.0 reshapes the `pipelex.toml` root to mirror the runtime layers and drops the redundant `_config` suffix from keys — `[pipelex]` splits into `[runtime]` / `[interpreter]`, `[cogt]` becomes `[inference]` — so the tracked `.pipelex/` files in this repo were migrated in place with `pipelex migrate`, which kept every value this deployment had chosen and carried each section banner along with the table it introduces. **Anyone running this server against their own `.pipelex/` must run `pipelex migrate` after upgrading**, including on the inference backend files: 0.46.0 removes `prompting_target`, and a surviving per-model one fails the strict boot by name. Migrate with **0.46.1 or later**: 0.46.0's migrator left a moved table's banner behind, so a file it rewrote needs its comments tidied by hand — or its `.bak` restored and the migration re-run. The pin names 0.46.4 rather than 0.46.0 for a run of fixes that ride along and change nothing on this API's wire: 0.46.1 restores the migrator's comment fidelity, 0.46.2 keeps a `.gitignore` inside `.pipelex/` so the timestamped backups a migration leaves behind stop showing up as untracked files, 0.46.3 makes that `.gitignore` reach a machine that had nothing to migrate (0.46.2 wrote it only on a run that actually carried a file forward, which is the minority case), and 0.46.4 is pipelex's own dogfooding of the convention plus a fix to its config-sync gate — developer tooling in that repo, invisible here. This repo's root `.gitignore` already ignored `*.bak.*`, so the tracked `.pipelex/` here is unaffected either way.

- **The runner tolerates a stale-but-migratable config the way pipelex's own boot does.** `_resolve_http_error_mappers` loaded the raw config dict and validated it itself, which bypassed the boot tolerance 0.46.0 added — a config whose drift the migration ledger can fully explain. Because that call resolves at module import, the app would have died on the import line over a file `Pipelex.make` accepts moments later in `lifespan`, with the app-construction traceback instead of the "run `pipelex migrate`" warning. It now goes through `config_manager.load_config_validated`, the same tolerant entry point the boot uses. A config the ledger *cannot* explain still fails the app fast, as before.

- **Swept onto `build_registrar`'s new `boot_orchestrator` parameter.** 0.46.0 removed the `plugins.boot_orchestrator` config key: the boot orchestrator is a boot argument now, and an orchestrator plugin gates its hub-slot claims on the value the registrar was built with. `_resolve_http_error_mappers` passes `None`, which is correct rather than merely convenient — the gate governs only the slot claims, which this throwaway registrar never applies, while a plugin contributes its HTTP-error mapper unconditionally. So the resolved map is what it always was, and the import-time resolution stays honest.

- **Config access moved with the keys.** `get_config().pipelex.pipeline_execution_config` is `get_config().interpreter.pipeline_execution` — the only reader of the config tree in this repo.

- **OpenAPI artifact refreshed, and the suggested-fix op vocabulary changed shape (Breaking on the wire).** A `suggested_fix`'s `ops[]` were a single open `FixOp` carrying a `FixOpKind` enum beside optional fields; 0.46.0 makes them a **union discriminated on `kind`**, one member schema per kind (`SetKeyOp`, `EnsureTableOp`, `DeleteKeyOp`, `DeleteTableOp`, `RenameTableKeyOp`, and the two new `MoveKeyOp` / `RemapValueOp`). A client reading `kind` and branching is unaffected in substance; one that validates against the published `FixOp` schema must move to the union. Also in the artifact: `PromptingTarget` and every `prompting_target` field are gone, and `PipeLLM` gains `templating_style` — 0.46.0 makes prompt templating an authoring decision on the pipe rather than something inferred from the model, with the runtime default now XML tags.

### Fixed

- **`docs/error-responses.md` no longer carries the "Suggested fixes" section twice.** The whole section — prose, example, field list and op table — was duplicated verbatim; a reader hitting the second copy had no way to tell which was current. One copy remains, and it documents the discriminated-union op shape and the full seven-kind vocabulary.

## [v0.13.0] - 2026-08-14

### Changed

- **Pinned `pipelex` 0.45.0 (Breaking, and a hard pairing).** Up from `==0.43.1`, exactly. The pin crosses two releases, and the code changes below come from the first of them, not the one the pin is named after.

  0.45.0 adds per-node token usage, cost and model attribution to the run GraphSpec: `NodeSpec` gains a `usage` object, `GraphSpec` gains a run-level `usage` rollup, and each node's usage carries `by_model` — the model that *actually* ran, read off the usage records rather than off the authored choice or an unresolved alias. Both models are `extra="forbid"`, which is what makes the pairing hard in the other direction — an older `pipelex` rejects the new JSON — so this repo and `pipelex` 0.45.0 must move together. `graph_spec` is on this API's wire (`POST /v1/execute` carries one, `POST /v1/validate` a best-effort one) and is validated back from `model_dump(mode="json")` against `strict=True` models, so the new fields reach `docs/openapi/pipelex-api.openapi.yaml`, regenerated here.

  0.45.0's other two changes do not reach this repo: a `PipeCondition` dry run is now reproducible (it sorts its branch walk instead of iterating a hash-ordered set), and a `{concept, content}` envelope carrying an empty list is now a value rather than an error — the latter only widens what an input may be, so no caller that worked before stops working.

- **Swept onto automatic search scope (Breaking).** 0.44.0 replaced the `search_domain_codes` list across the public API (`PipelexMTHDSProtocol`, `pipeline_run_setup`, `InputShaper`, `WorkingMemoryFactory`) with a single `search_scope` string that `pipeline_run_setup` derives from the entry pipe itself, so `ApiRunner.start` no longer passes one. Caller-visible in how a request's inputs resolve their concepts: the scope is now the entry pipe's own domain — `alias->domain` when the entry pipe comes from a dependency package — rather than whatever the runner supplied, and every entry-lookup refusal (invalid string, miss, ambiguity) now arrives as `ConceptLibraryConceptNotFoundError`.

### Fixed

- **A bare `pipe_ref` resolves again on the build routes.** 0.44.0 made in-body pipe references strict: the resolver behind `get_required_pipe` is a key lookup with deliberately no bare-code search, because a reference that can find a pipe in a domain its author never named is one `[exports]` cannot constrain. `resolve_requested_pipe` was still on it, so `POST /v1/build/inputs`, `/v1/build/output` and `/v1/build/runner` answered `422 Pipe '<code>' not found in the submitted closure` for *every* bare `pipe_ref` — a closure declaring `smoke.echo` refused `"echo"`, the spelling the route's own contract promises to accept and echo back qualified.

  A code a human typed at an entry point is a different question from a reference one pipe makes to another, and 0.44.0 gave it its own answer: `get_required_entry_pipe` matches a bare code across every domain the library holds, ignores `[exports]` (package visibility governs in-body references, not hand-typed entry points), and excludes aliased dependency entries so installing a package cannot make a host pipe's code ambiguous. The route now uses it. An ambiguous bare code raises rather than picking a winner, and still surfaces as a `422` naming the candidates.

## [v0.12.0] - 2026-08-12

### Changed

- **Pinned `pipelex` 0.43.1 (Breaking, and a hard pairing).** Up from `==0.42.0`, exactly. The two releases must move together in both directions: 0.43.0 retires the single `pipelex.plugins` entry-point group, so a plugin still declared under it now fails the boot with `RetiredPluginEntryPointGroupError` rather than going quietly undiscovered — while 0.42.0 does not read the new groups at all and would discover no plugin published under them. The rest of 0.43's breaking surface does not reach this repo: `ImageReference` / `DocumentReference` moved to `pipelex.kernel.prompt_references`, `LLMPromptBlueprintValueError` / `ImgGenPromptBlueprintValueError` unified into `PromptContentError`, `StructuredContentComposer` dropped `pipe_run_params`, `InputShaper` now resolves through its injected provider, and 0.43.1 made `PipeRunParams.batch_max_concurrency` required — none of those symbols has an import site here.
- **OpenAPI artifact refreshed.** The committed schema tracks pipelex's own models, and 0.43.1 reworded the `CodegenTarget` docstring. Description text only — no route, field, type or requiredness moved, so the wire contract is unchanged.
- **Swept onto the plugin entry-point group split.** `pipelex` replaced its single `pipelex.plugins` entry-point group with `pipelex.plugins.kernel` and `pipelex.plugins.interpreter`, and `build_registrar` gained a required `entry_point_groups` parameter naming which of them to read. `_resolve_http_error_mappers` passes `ENTRY_POINT_GROUPS` from `pipelex.interpreter_plugins.builtins` — the composed both-group list, matching the `BUILTIN_PLUGINS` / `CORE_UNCONDITIONAL_PLUGIN_NAMES` it already injects and the `pipelex plugins list` diagnostic this function is modelled on. The runner boots the full interpreter, so it must read both groups: reading the kernel group alone would silently drop an installed orchestrator plugin's HTTP-error mapper and leave transport faults unmapped. The parameter is required rather than defaulted, so this omission would have surfaced as an import-time `TypeError` — the call site resolves at module scope, taking the whole app down on the next `pipelex` bump rather than degrading one feature. `test_exception_handlers.py` follows the matching `registrar.begin_plugin` signature change, passing `group=None`.

## [v0.11.1] - 2026-08-03

### Fixed

- **The catch-all 500 now honors `ERROR_DISCLOSURE` like every other response.** `handle_unexpected_error` hard-coded `"An unexpected error occurred. The request id is included for support."` and never read the disclosure mode, so a `verbose` deployment — the default, and what every deployment runs, since the var is unset everywhere — got real messages for every *classified* error and a dead end for the one error nobody classified. That is backwards: an unclassified failure is precisely the one a caller cannot diagnose from a request id alone. A raw `pydantic.ValidationError` escaping input building (it is not a `PipelexError`, so no handler claimed it) landed here, and its reason was reachable only in CloudWatch.

  Under `verbose`, `detail` is now `"<ExceptionClass>: <message>"`. Under `strict` the body is byte-identical to before — a deployment that wants nothing leaked keeps that, and provenance-gated redaction (`_authors_caller_facing_message`) is unchanged. A traceback still reaches the client in neither mode; the class name and full traceback continue to go to the operator log, correlated by request id. Docs: `docs/error-responses.md` → "Disclosure modes".

## [v0.11.0] - 2026-08-01

### Added

- **Storage transport documentation (`docs/storage-transport.md`):** documents the `/upload` and `/resolve-storage-url` routes — their non-public contract status, their role as the current transport behind the SDKs' input-preparation surface, the two-layer size-limit enforcement (request-level `422` vs. post-decode `413`), and the planned migration to `pipelex-platform`. Linked from `docs/index.md` and added to the `mkdocs.yml` nav.
- **Upload size-limit test:** `test_decoded_payload_over_cap_returns_413` covers the narrow window where a base64 payload clears the request's `max_length` validation but decodes over `MAX_UPLOAD_BYTES` — the only path that yields a `413`.

### Changed

- **Breaking — swept onto `pipelex`'s 0.41.0 restructuring.** The release deleted `pipelex.hub`, moved the MTHDS parser and the Pipe machinery out of `core/`, and relocated a set of types to the packages that own them; every import is re-pointed at the address that now defines the symbol.
  - **The hub split.** `pipelex.hub` is gone with no shim, split into `pipelex.runtime_hub` and `pipelex.interpreter_hub` by owning layer. This falls out neatly along the route boundaries: the storage and uploader routes take `get_storage_provider` from the **runtime** hub and the pipeline route takes the orchestrator/bundle-validator registries from it too, while the build-runner and crate-ops routes take the library and pipe accessors from the **interpreter** hub.
  - **`build_registrar` now requires its built-ins to be injected.** It no longer imports them, because the built-in list spans both layers and importing it inside a runtime-layer module would put the method interpreter back into every runtime closure. `_resolve_http_error_mappers` passes `BUILTIN_PLUGINS` / `CORE_UNCONDITIONAL_PLUGIN_NAMES` from `pipelex.interpreter_plugins.builtins` — the composed both-layer lists, matching the `pipelex plugins list` diagnostic this function is modelled on. The discovery function stays pure and repeatable, so resolving the mapper map at import is still safe.
  - **Address moves:** `PipelexBundleBlueprint` → `pipelex.mthds_parsing.pipelex_bundle_blueprint`; `PipeAbstract` → `pipelex.pipe_machinery.pipe_abstract`; the input/output renderers → `pipelex.pipe_machinery.rendering.*`; `PipelexBundleBlueprintValidationErrorData` → `pipelex.core.exceptions`; `JobMetadata` → `pipelex.system.job_metadata`.
  - The dotted pipelex class paths in `pyproject.toml`'s `runtime-evaluated-base-classes` (`PipeOutput`, `PipelexRunResultExecute`) were checked against 0.41.0 and did **not** move.
- **Breaking — wire-visible error rename:** `PipelexInterpreterError` is now `MthdsParserError`. The class name *is* the `error_type` value on the wire, so this changes what clients see — `docs/error-responses.md` (the caller-facing-`detail` allowlist) and the webhook-recovery test fixture are updated to match.
- **Dependencies:** Bumped `pipelex` from `0.40.0` to `0.42.0`.

### Fixed

- **`docs/error-responses.md` had a duplicated "Suggested fixes" section.** The 0.41.0 sweep accidentally duplicated the section (originally documented in v0.9.0) while moving surrounding content; removed the duplicate, no content change.

## [v0.10.0] - 2026-07-19

### Changed
- **Breaking: `/execute` now returns `pipe_output.tokens_usages` as client wire records (`TokensUsageRecord`), not dumps of pipelex's internal usage models.** The route applies pipelex's `apply_tokens_usage_wire_shape` to the response dump, so each record is flat and closed: `model_type`, model name/id, `pipe_code`, `job_category`, `unit_job_id`, `nb_tokens_by_category`, computed USD `cost` (`null` when the model has no rate table), ISO `started_at`/`completed_at`. Runtime internals (`job_metadata` and its contexts/ids, `unit_costs`) no longer cross the wire. Null semantics unchanged (`null` = usage assembly off, `[]` = no inference). Documented in [Pipe Run](docs/pipe-run.md).
- **The OpenAPI artifact now publishes the wire shape it actually emits.** `/execute` returns a `JSONResponse` built from the trimmed dump, so FastAPI never serializes through `response_model` — the declared 200 body was still the internal usage union (`LLMTokensUsage | ImgGenTokensUsage | …` with required `job_metadata` and `unit_costs`), and a client generated from the artifact would have rejected every real response carrying usage data. The route now declares `PipelexApiExecuteResponse` (the run result whose `pipe_output.tokens_usages` is `TokensUsageRecord[]`), so the published schema matches the body. The internal usage models leave the artifact entirely; `tests/unit/test_openapi_contract.py` pins the published record alongside the runtime guard, so the two fail together if either drifts again.
- **Dependencies:** Bumped `pipelex` from `0.39.1` to `0.40.0`. This release carries `apply_tokens_usage_wire_shape` and the `TokensUsageRecord` wire shape the `/execute` change above depends on. (It supersedes the interim `0.39.2` bump — which unblocked the hosted runner resolving against a git-sourced `dev` — with a released PyPI pin.)

## [v0.9.1] - 2026-07-15

### Changed
- **Dependencies:** Bumped `pipelex` from `0.39.0` to `0.39.1`.

## [v0.9.0] - 2026-07-14

### Added
- **`POST /v1/resolve` (MTHDS Protocol resolution capability):** resolve a library closure into its **normalized library crate** over HTTP. Request selects the closure with inline `files[]` (each `{content, source?}`) XOR a `method_ref`; a produced verdict is a `200` discriminated on `is_valid` — the canonical JSON crate (qualified refs, flattened refinement, materialized natives, fingerprint) on the valid arm, the structured `validation_errors[]` on the invalid arm. `method_ref` is accepted by the envelope but answers `501` (`MethodRefNotSupported`) until server-side method-registry resolution exists.
- **`POST /v1/codegen` (MTHDS Protocol type-projection capability):** project the crate into typed artifacts with the two explicit axes — `kind` (`types`) × `target` (`ts-zod`, `python-pydantic`, and the Pipelex-extension `python-structures`). The valid arm carries the **stamped** artifact set plus its `codegen.lock`: a client that writes them verbatim reproduces a local `pipelex codegen types` run byte-for-byte and passes the offline `pipelex codegen check`. An unknown `kind`/`target` (or a `pipe_ref` on the concept-set-wide `types`) is a request-shape `422` problem+json. There is deliberately no server-side check route (the drift check is offline by design), and no `inputs` kind: served-kind membership follows the stamp/lock trust chain, and an inputs template is a user-editable scaffold that is never stamped or locked — it rides `POST /v1/build/inputs` instead.
- **Docs:** new [Resolve & Codegen](docs/codegen.md) page; [Pipe Builder](docs/pipe-builder.md) rewritten to the new envelopes.
- **`postman-bundle` skill (renamed from `postman-run-bundle`) now covers the whole bundle surface:** besides `/v1/execute`, `/v1/start`, and `/v1/validate`, the skill and its `build_postman_query.py` script target `/v1/resolve`, `/v1/codegen` (with `--target ts-zod|python-pydantic|python-structures`), and `/v1/build/{inputs,output,runner}` (with `--output-format` for `build/output`, and `--inputs-format json|toml` + `--explicit` for `build/inputs`). New make targets `bundle-resolve` and `bundle-codegen`; the build routes ride the generic targets via `ENDPOINT=`. Postman pushes now land under a `Bundles/` top folder (was `Run Bundle/`) and merge by request name instead of replacing the whole per-bundle subfolder, so requests for different endpoints coexist.

- **`suggested_fix` on validation errors (from pipelex codegen):** a `validation_errors[]` item may now carry a structured, deterministic repair the runtime's fix planner derived from the *typed* error data (never by parsing a message string) — `fix_code` (kebab-case rule id), `description`, `safety` (`safe` | `unsafe`), an optional `source`, and `ops[]`: semantic TOML patch operations (`set_key`, `ensure_table`, `delete_key`, `delete_table`, `rename_table_key`) addressed by `table_path`. The ops are the machine contract; any rendered diff is presentation. Optional and additive — a non-fixable item omits the field and a client that ignores it is unaffected. It rides every surface that carries the items: the `200` invalid arms of `/v1/validate`, `/v1/resolve`, `/v1/codegen`, and `/v1/build/*`, and the RFC 7807 problem documents. Documented in [Error Responses → Suggested fixes](docs/error-responses.md#suggested-fixes).

### Changed
- **`pipelex` is pinned to a git rev while `codegen` is unreleased.** The dependency source moved from a local editable path (`../pipelex`) to a git rev on the `pipelex` repo. The editable path only ever resolved on a workspace checkout — it fails `uv sync` anywhere else, CI included. The pinned rev carries the unreleased codegen engine this API rides; it reverts to a plain `==<version>` PyPI pin once a `pipelex` release ships it.
- **The OpenAPI artifact now documents the real error contract.** Every failure this server emits is an RFC 7807 `application/problem+json` problem document, but the published artifact said otherwise: it advertised FastAPI's default `HTTPValidationError` on `application/json` for the 422 of nearly every route, `/v1/execute` and `/v1/start` documented no failure at all, and no route documented 401/403/409/413/429/500/501. Now every `/v1` operation documents `401`/`413`/`422`/`500` as a typed `ProblemDocument` under `application/problem+json`, plus the statuses it alone can produce — `/execute`: `403`, `429` (with `Retry-After`); `/start`: `400`, `403`, `409`, `501`; `/validate`: `403`; `/resolve` + `/codegen`: `501`. `GET /v1/version` stays public and 401-free. `HTTPValidationError` is gone from the artifact entirely.
- **Breaking — `/v1/resolve` and `/v1/codegen` are no longer tagged `x-mthds-protocol`.** They are **Pipelex API extensions**, not MTHDS Protocol operations: the protocol is, and stays, the five routes `execute` / `start` / `validate` / `models` / `version` that the standard's own normative OpenAPI defines. The flag is how a conformance suite or a third-party runner extracts the portable subset of the artifact, so tagging a Pipelex route misrepresented the standard. The *crate* `/v1/resolve` emits remains standard-owned (the MTHDS Library Crate Format) with brand-neutral wire fields — only the routes' protocol membership changed, and no request or response shape moved. `tests/unit/test_openapi_contract.py` now pins the tagged set exactly, in both directions.
- **Docs:** [Error Responses](docs/error-responses.md) gains a *Suggested fixes* section and the missing `missing_pipe_code` field, and its status-code list now covers the `400` (`StartRequiresAsyncOrchestration`), the `orchestration_mode` `403`, and the `method_ref` `501` (the `501` bullet also named a stale `/pipeline/start` path). The [Overview](docs/index.md) endpoint catalog gains the *Resolve & Codegen* section and `GET /`, and corrects the uploader auth requirement — `/v1/upload` and `/v1/resolve-storage-url` need an authenticated **user identity**, which `AUTH_MODE=api_key` does not establish (the key is shared, not per-caller).
- **Breaking — `/v1/build/{inputs,output,runner}` migrated onto the `/validate` verdict discipline:** a produced verdict is now always a `200` discriminated on `is_valid`. `build/inputs` and `build/output` wrap their previous bare JSON payload in the valid arm (`inputs` / `output` fields); an invalid bundle — including a failed dry-run of the requested pipe — is now a `200` `is_valid: false` with the structured `validation_errors[]` instead of a `422`. `build/runner` drops the retired `success` bool.
- **Breaking — `/v1/build/runner` rides the codegen types projection (D9):** the generated script spells its imports, example inputs, and output cast with the **emitted** class names, and the valid arm now also carries the `structures` projection it imports from (stamped `structures.py` + `codegen.lock`, written into a `structures/` directory beside the script) — matching what a local `pipelex build runner` scaffolds. A requested pipe recorded SKIPPED by the sweep (cross-package dependency absent from the request) remains a request-shape `422`.
- **Breaking — `/v1/build/*` now ride the same request envelope as `/v1/resolve` and `/v1/codegen`:** the closure selector is inline `files[]` (each `{content, source?}`) XOR a `method_ref` (`501` until the method registry lands), replacing the bare `mthds_contents[]` strings. The per-file `source` label means build diagnostics can finally name the owning file, and there is no second breaking migration waiting when `method_ref` resolution arrives. The pipe selector becomes **`pipe_ref`** — the qualified `domain.pipe_code`, and now **optional**: omitted, it defaults to the closure's declared `main_pipe`, exactly like `pipelex codegen inputs --pipe`. A closure declaring *no* `main_pipe`, or *several* across domains, cannot be defaulted, so an omitted `pipe_ref` is a `422` there. Every valid arm echoes the resolved `pipe_ref` plus the submitted `requested_pipe_ref` (absent when defaulted). The echoed `pipe_ref` is always **qualified**, read back off the resolved pipe rather than off the request — a bare code still resolves through the engine's cross-domain fallback, and the caller is told the qualified ref it landed on. The old bare-`mthds_contents` envelope now survives on `/v1/validate` alone, which keeps it because changing a protocol route's envelope is the MTHDS spec's call, not this server's.
- **Breaking — `/v1/build/inputs` and `/v1/build/output` are static; `allow_signatures` is gone from both.** They now resolve their closure through the same static core as `/resolve` and `/codegen` and read the requested pipe's *declared* IO — no dry-run sweep, so no `allow_signatures` (the flag only ever parameterized that sweep). A valid verdict from them says the closure is structurally sound, **not** that the pipe runs; runnability stays `/v1/validate`'s vocabulary. `/v1/build/runner` is the deliberate exception — a runner script *is* a promise the pipe runs, so it keeps both the sweep and the flag. When its `pipe_ref` is omitted the sweep cannot be scoped before the closure loads, so the whole closure is swept.
- **Breaking — `/v1/build/inputs` gains the CLI's two rendering axes, and its payload's JSON type follows the format.** New `format` (`json`, default | `toml`) and `explicit` (bool, default `false` — the ceremonial `{concept, content}` envelope instead of the default light, signature-driven shape), rendered through the same engine renderers `pipelex codegen inputs` uses. The template rides the field its format names: `inputs` (a parsed object) for JSON, `inputs_toml` (raw text) for TOML — TOML cannot ride as a parsed object without losing the concept comments and key order that are the reason to ask for it. The unselected field is omitted from the body. A pipe declaring no inputs is a *valid* verdict carrying an empty template, not an error (the CLI likewise exits 0 on it).

### Fixed
- **`/v1/build/runner` could read the wrong pipe's output multiplicity.** A blueprint's pipe map is keyed by *bare* code, and the multiplicity lookup scanned by bare code alone. In a closure where two domains declare a pipe with the same name, it returned whichever blueprint came first — so a list-output pipe could be handed a scalar runner script (`main_stuff_as` instead of `main_stuff_as_items`), and vice versa. The lookup now matches the owning domain too.
- **`/v1/build/output` with `format=python` was a hard `500`.** The route parsed *every* format with `json.loads` and typed the field `dict`, so the Python-source representation crashed on arrival. The representation now rides the field its format names, mirroring `/build/inputs`: `output` (a parsed object) for `schema`/`json`, `output_python` (source text) for `python`. Separately, a pipe whose `native.Anything` output has no determinable shape (which `render_output` reports with a bare `ValueError`) is now an honest request-shape `422` rather than an unhandled `500`.
- **Docs — [Error Responses](docs/error-responses.md) no longer contradicts the 200-verdict discipline.** Two sections still said an invalid bundle rides a `422` on the build routes, and the 422 example showed `POST /v1/validate` producing one; both now correctly attribute the `ValidateBundleError` 422 to the run routes (`/execute`, `/start`) alone, with the diagnostic routes answering `200` `is_valid: false`.

## [v0.8.0] - 2026-07-06

### Changed
- **Dependencies:** Bumped `pipelex` from `0.37.0` to `0.38.0`.
- **Adapted to pipelex 0.38.0 breaking changes:** `StrEnum` is now imported from the stdlib `enum` — pipelex 0.38.0 dropped Python 3.10 and deleted the `pipelex.types` re-export module that used to provide it. And `PipeSignature` is no longer a pipe type: a signature (contract-only pipe) is declared by **omitting** `type`, so the signature test fixtures and the `/validate` docs were updated to the typeless form (writing `type = "PipeSignature"` is now rejected by the runtime).

### Added
- **Optionality surface on `/validate` and working memory (from pipelex 0.38.0):** the regenerated OpenAPI artifact exposes pipelex's new optionals feature — `optional` (`?`) markers on IO contracts and data edges, `liftable_pipes` (pipes that may be skipped when an optional input resolves absent) plus a general `warnings` array on the validation report, `skip_reason` on graph nodes, and an `absences` ledger (`AbsenceRecord` / `AbsenceKind`) on the serialized working memory.

## [v0.7.0] - 2026-07-04

### Added
- **Core:** Introduced `PipelexPipeDispatchAck` payload to handle fire-and-forget job acknowledgments (returning IDs only), replacing incomplete `PipelexPipeRunOutput` objects for async dispatches.

### Changed
- **Architecture:** Replaced the `DeliveryMode` flag and unified `orchestrator.run()` method with explicit wait-semantics methods: synchronous `/execute` requests drive the blocking `orchestrator.execute()`, while asynchronous `/start` requests drive the fire-and-forget `orchestrator.start()`.
- **Dependencies:** Bumped `pipelex` from `0.36.0` to `0.37.0`.
- **Developer Tools:** Streamlined `Makefile` commands and `CLAUDE.md` docs: renamed `make c` to `make agent-check` and `make t` to `make agent-test` (both silent on success), and added `make cleanderived` to clear caches and compiled files.
- **Testing:** Aligned test stubs (`_StubOrchestrator`, `_RecordingStub`) and protocol conformance tests with the new `execute`/`start` protocol, and enhanced the `execute` stub to promote input stuff to main stuff via the `MAIN_STUFF_NAME` alias, enforcing the completed-memory invariant.
- **Documentation:** Updated internal API routing comments to reference `{MTHDS_BASE_URL}` instead of `{MTHDS_API_URL}`.

## [v0.6.0] - 2026-06-30

Orchestrator-agnostic base. `pipelex-api` no longer hard-wires Temporal: the published base names **no** orchestrator and runs every pipeline in-process, while distributed execution (Temporal, Mistral Workflows, …) becomes a deployment *flavor* = base image + exactly one orchestrator plugin + that plugin's activation. `api/` imports no `pipelex.temporal` / `temporalio`.

### Added
 - **`orchestration_mode` deployment config:** a top-level run's backend is read from a new packaged `api.toml` (`orchestration_mode`, default `direct`; `allow_request_orchestration_mode_override`, default `false`), env-layered like the Pipelex config (`api_{env}.toml` / `api_override.toml`). `orchestration_mode` is an **open string token** (core owns `direct`; each orchestrator plugin owns its own, e.g. `temporal`); an unregistered token fails loud at dispatch. `POST /v1/execute`, `POST /v1/start`, and `POST /v1/validate` may each carry a per-request `orchestration_mode` override, honored only when the deployment opts in — otherwise refused with a `403` (`OrchestrationModeOverrideForbidden`). The **delivery** axis (blocking vs fire-and-forget) is endpoint-intrinsic, never configured or requestable. See [Configuration → Orchestration mode](docs/configuration.md).
 - **Orchestrator HTTP-error mappers:** the app discovers each installed orchestrator plugin's transport-fault mapper (via the plugin SPI `add_http_error_mapper`) at construction and registers one RFC 7807 handler per mapped exception type — so a plugin's transport fault renders correctly while the base imports no orchestrator SDK.
 - **`make docker-run-hub` target:** pull and run the published `pipelex/pipelex-api` Docker Hub image without a local checkout or build, using the same `.env` contract as `make docker-run`. Pin a tag with `HUB_TAG=<tag>` (defaults to `latest`).

### Changed
 - **Two orthogonal axes — `orchestration_mode` (open token) + delivery (endpoint-set):** the backend (*which orchestrator*) and the wait-semantics (*whether the caller waits*) are now distinct. `orchestration_mode` names only the backend and is an open string token. Delivery is `DeliveryMode {BLOCKING, FIRE_AND_FORGET}`, threaded into the orchestrator by the endpoint and never received from a caller: `/execute` and `/validate` dispatch `BLOCKING`, `/start` dispatches `FIRE_AND_FORGET`. The conflated `execution_mode` enum (which carried `temporal_blocking` / `temporal_fire_and_forget` / `mistral_native`) is gone.
 - **`/execute` dispatches by `orchestration_mode`:** `POST /v1/execute` selects its backend from the resolved `orchestration_mode` — dispatching the locally-built run job through the hub's `OrchestratorRegistry` with `BLOCKING` delivery, symmetric with `/start` — instead of the boot-global pipe-run slot. `orchestration_mode` is the single source of truth for top-level dispatch (`boot_orchestrator` narrows to the execution stack). A per-request `orchestration_mode` override is gated by the same `403` policy as `/start`. The full output is preserved across the dispatch: the orchestrator's JSON-safe result is rehydrated back into the canonical `PipeOutput` the response wraps.
 - **`/start` is HONEST about fire-and-forget:** `POST /v1/start` builds the run job locally (preserving `request_id`, `output_multiplicity`, `dynamic_output_concept_ref`, run registration, and telemetry) and dispatches it through the hub's `OrchestratorRegistry` with `FIRE_AND_FORGET` delivery. It checks the resolved orchestrator's `supports_fire_and_forget` capability **before** loading a library: an async-capable backend (`temporal`, contributed by the `pipelex-temporal` plugin) acks `202` with its `workflow_id`, while the in-process `direct` base is blocking-only and is refused with a `400` (`StartRequiresAsyncOrchestration`) — use `/execute` — instead of silently running blocking and acking.
 - **`/validate` dispatches by `orchestration_mode` (verdict-as-value):** like `/start`, `/validate` resolves the deployment's `orchestration_mode` and dispatches through the hub's `BundleValidatorRegistry`, returning the verdict as a value — a 200 valid `PipelexValidationReport` or a 200 invalid `ErrorReport` (no exception-as-control-flow at the route). Validation is inherently blocking, so there is no delivery axis here. `direct` validates **in-process** on the API side; a `temporal` mode dispatches the whole job to a **worker** (contributed by the `pipelex-temporal` plugin) and assembles the same canonical report API-side from the worker's result. A per-request `orchestration_mode` override is gated by the same policy as `/start` (`403` when forbidden). The verdict wire is byte-identical across backends. Size in-process `/validate` traffic for the library load; on a worker-dispatched flavor the library work happens worker-side.
 - **Dependencies:** pinned `pipelex` to the published `0.36.0` (`pipelex[mistralai,anthropic,google,google-genai,bedrock,fal]==0.36.0`), replacing the prior git-rev pin (`[tool.uv.sources]` removed). Dropped the `temporal` extra — the base depends on no orchestrator plugin — and dropped the now-redundant direct `mthds` dependency (pulled in transitively by `pipelex`).

## [v0.5.0] - 2026-06-18

### Added
 - **Opt-in Markdown rendering on `/validate`:** `POST /v1/validate` now accepts an optional `render` list of view-format tokens (e.g., `["markdown"]`). When requested, the response includes a `rendered_markdown` field on both valid and invalid arms, matching the local CLI output. Unknown tokens are ignored to keep presentation hints separate from the verdict contract. This is supported end-to-end via a new `--render` flag in `build_postman_query.py` and a `RENDER` variable in `Makefile.local.mk`.
 - **Postman sample bundles:** Added a suite of sample `.mthds` bundles and `.inputs.json` files in `postman/sample-bundles/` covering valid, invalid, and runnable pipeline states.

### Changed
 - **`mthds_sources` migrated to `extra` hook:** `ApiRunner.validate` now passes `mthds_sources` through the generalized `extra: dict | None` extension point, matching the updated `PipelexMTHDSProtocol.validate` signature from `mthds-python 0.5.0`.
 - **`main_pipe` is now optional for validation:** Bundles without a main pipe validate successfully (`is_valid: true`) but return `graph_spec: null`. Documentation and scripts updated accordingly.
 - **OpenAPI Makefile targets depend on `install`:** `openapi-export` and `openapi-check` now depend on `install` instead of `env`, ensuring the schema is generated and validated against a fully synced environment to prevent silent CI drift.
 - **Dependencies:** Bumped `pipelex` to `0.35.0` and added `mthds>=0.5.0` to `pyproject.toml`.

## [v0.4.0] - 2026-06-17

MTHDS Protocol surface alignment (Phase 2): `/validate` (like `/models`) now routes through `ApiRunner` (extending `PipelexMTHDSProtocol`), exactly like `/execute` and `/start`. The runner owns backend selection (in-process vs a single dispatched Temporal activity), the runtime owns the canonical artifact shapes, and the route only adds wire extras — so hosted and local runners answer with identical artifacts.

### Added
 - **Source threading for diagnostics:** Added an optional `mthds_sources` parameter to `POST /v1/validate`, letting clients pass per-file sources parallel to `mthds_contents`. Each source is threaded onto the corresponding `blueprint.source` and onto the structured errors, so cross-file diagnostics map back to their owning file. Additive — sourceless callers are unchanged; a length mismatch against `mthds_contents` is a request-shape 422.
 - **Structured validation errors:** An invalid bundle now returns a non-empty `validation_errors` array on the 200 `InvalidReport`, where each item carries detailed locators (`category`, `message`, `error_type`, `source`, `field_path`, etc.) to map the error back to a specific construct and line. The items are builder-identical to the agent CLI's `validation_errors` (one shared pipelex builder, two surfaces).
 - **Runnability facts:** Added `validated_pipes`, `pending_signatures`, and `is_runnable` to the validation report to communicate the runnability verdict across the HTTP surface.

### Changed
 - **`/validate` is now a 200-diagnostic endpoint:** An invalid bundle is a successfully produced verdict and returns **200 OK** with an `InvalidReport` (`is_valid: false`) instead of a 422. 422/5xx are reserved for no-verdict conditions (malformed request body, `mthds_sources` length mismatch, auth, server faults). The response is a discriminated union keyed on `is_valid`, returning either a `ValidReport` (structural artifacts) or an `InvalidReport` (structured errors). The previous `main_pipe` precondition is dropped: bundles without a main pipe now validate successfully with `graph_spec: null`.
 - **Canonical validation report schema updates:** Renamed `pipelex_bundle_blueprint` to `bundle_blueprint` (the primary blueprint — first file declaring `main_pipe`, else first); `pipe_io_contracts` is now keyed by the namespaced `pipe_ref` (e.g. `domain.code`) instead of the bare pipe code; and within each entry the input/output identifier was renamed from `concept_code` to `concept_ref` (now always the namespaced `concept.concept_ref`). `BuildConceptResponse.concept_code` on `/v1/build/concept` is unaffected — it accepts a bare or qualified code.
 - **`allow_signatures` behavior:** Unimplemented `PipeSignature` declarations no longer reject a bundle. `allow_signatures` now only controls sweep mechanics (whether signature pipes are mock-run and listed in `validated_pipes`); outstanding signatures are reported via `pending_signatures` with `is_runnable: false` on a 200 `ValidReport`.
 - **`/models` returns the protocol `ModelDeck`:** `/models` now routes through `ApiRunner` and returns the canonical `ModelDeck` — the flat `models` list plus this implementation's category-keyed `aliases`/`waterfalls` routing extensions (a flat map would silently drop the same alias name across categories). The `?type=` query is now strictly single-value, matching the protocol arity.
 - **Protocol version from the SDK:** `/version` and the OpenAPI metadata now source `PROTOCOL_VERSION` from `mthds.protocol.protocol`; the `pipelex.pipeline.runner.MTHDS_PROTOCOL_VERSION` alias is gone.
 - **Temporal mode optimization:** The worker now computes all library-dependent artifacts (`pipe_io_contracts`, `pending_signatures`, `graph_spec`, status map, structured errors) within its single library load and ships them on the activity result, so the API side no longer re-acquires a library to build response artifacts.
 - **Dependency & version bumps:** Bumped the API version to `0.4.0` and updated the pinned `pipelex` dependency to track the keyword-only-arguments refactor (`parse_pipe_spec(spec, pipe_type=...)`, keyword-only `Pipelex.make`) and the new structured-error / signatures-as-data contract.
 - **Documentation:** Updated the OpenAPI artifact (`pipelex-api.openapi.yaml`), `pipe-validate.md`, and `error-responses.md` to reflect the 200-diagnostic contract, structured errors, and source threading.

### Removed
 - **`success` wire field:** Dropped the redundant `success` field from the `/validate` and `/models` responses in favor of the canonical `is_valid` discriminant.
 - **Legacy `/models` keys:** Dropped the unused raw `presets` keys (keyed by category) from the `/models` response and removed support for multi-category `?type=` queries.

## [v0.3.0] - 2026-06-17

### Changed — `user_id` is opaque again (path-safe, not UUID-shaped)

The runner no longer requires `user_id` to be a bare UUID. `user_id` is the owner segment of every storage key (`<user_id>/...`), and the runner is a generic execution engine: identity is the deployment's concern (enforced upstream by the gateway/auth layer that injects `X-User-Id`, or by the JWT issuer), not the runner's. The previous UUID-shape check wrongly rejected any non-UUID id — including hosted deployments that use prefixed ids like `user_<uuid>`, which were **silently downgraded to anonymous** and wrote results under `anonymous/...`.

- `USER_ID_UUID_REGEX` is replaced by `is_safe_user_id(value)` in `api/security.py`: the only constraint is that the id be a single, **unambiguous path segment** — path-safe (no `/`, `\`, NUL/control chars, DEL; not `.`/`..`) and free of URI gen-delims (`:`, `?`, `#`, `[`, `]`, `@`). Any other opaque id (`user_<uuid>`, a bare uuid, `user-123`, …) is accepted as-is.
- URI gen-delims are rejected because the id is embedded into a `pipelex-storage://<user_id>/...` URI: a value like `google#abc` is owner `google#abc` by raw split but `google` under a standard URI parser (`urlparse`), so a consumer could resolve a different owner than the one this server authorized.
- Applies to all three sites: the JWT `user_id` claim, the forwarded `X-User-Id` header (`TRUST_FORWARDED_IDENTITY_HEADERS=true`), and `pipelex-storage://` URI parsing (`/resolve-storage-url`).
- This reverses the prior "must be a UUID" constraint. Path-traversal protection is unchanged (it never depended on the UUID shape).

### Fixed — close the `anonymous`-sentinel and malformed-forwarded-id gaps

The opaque-id change above made `anonymous` a path-safe value and left the forwarded-id path failing open. Both are now closed in `api/security.py`:

- **The reserved `anonymous` sentinel can no longer be claimed by an authenticated token.** A JWT with `user_id: "anonymous"` previously passed the path-safety check and bound that exact value — landing the caller's runs in the shared `anonymous/...` namespace while storage/upload routes still treated them as unauthenticated. `verify_jwt` now rejects it with `401 InvalidToken`. The value is centralized as `ANONYMOUS_USER_ID`.
- **A malformed forwarded `X-User-Id` now fails closed.** When `TRUST_FORWARDED_IDENTITY_HEADERS=true` and the proxy forwards a non-empty but path-unsafe id, `no_auth` previously logged and silently downgraded to anonymous; it now rejects the request with `400 BadRequest`. The absent-header and explicit-`anonymous` cases still stay anonymous (the proxy's deliberate "this request is anonymous" signal).
- **`is_safe_user_id` now rejects DEL (`\x7f`).** The unsafe-character class covered C0 controls (`\x00-\x1f`) but let DEL through, contradicting the "no control characters" invariant. DEL is now rejected across all three sites (JWT claim, forwarded header, storage-URI parsing).

## [v0.2.0] - 2026-06-12

### Changed — extension args are this server's own (callback_urls)

- The MTHDS Protocol no longer defines `callback_urls` (or any completion channel) — it is now formally THIS server's extension. The `/start` OpenAPI schema is published from the server's own `PipelexApiStartRequest` model (protocol `StartRequest` + the documented `callback_urls` extension) instead of relying on the protocol model to advertise it. `ApiRunner.start` drops the dead `method_id` compatibility param (the hosted platform handles `method_id` itself and never forwards it) and gains the protocol's generic `extra` slot. SDK clients pass server-specific args via `extra` — e.g. `client.start(..., extra={"callback_urls": [...]})`.

### Breaking Changes — MTHDS Protocol alignment (master plan 05, Phase C1)

This server is now the reference implementation of the **[MTHDS Protocol](https://mthds.ai)** (contract nesting: MTHDS Protocol ⊂ Pipelex API ⊂ Pipelex hosted API). Clients on the new SDKs (`mthds` Python/JS protocol releases) require a pipelex-api image carrying these changes — **the minimum image version for the `/v1` surface is this release**; an older image 404s on every `/v1/*` call.

- **Base path: `/api/v1` → `/v1`, no aliases.** The API router now mounts at `/v1` (SDKs compose `{MTHDS_API_URL}/v1/{endpoint}`). Zero `/api/v1` routes remain.
- **Run routes renamed:** `POST /api/v1/pipeline/execute` → `POST /v1/execute`, `POST /api/v1/pipeline/start` → `POST /v1/start`. `/start` now answers **202 Accepted** (protocol `StartAck`) instead of 200.
- **Wire fields renamed (D1):** request extra `pipeline_run_id` → `pipeline_run_id` (client-supplied run ids on `/start` are still accepted — the protocol allows it and `StartAck.pipeline_run_id` is authoritative); responses serialize `pipeline_run_id` / `state` instead of `pipeline_run_id` / `pipeline_state`. The pipelex runtime internals keep `pipeline_run_id` — only the wire renames.
- **`GET /version` replaces `GET /pipelex_version` + `GET /api_version` (both deleted, no alias).** Returns the protocol `VersionInfo`: `{protocol_version, implementation: "pipelex-api", implementation_version, runtime_version}`. PUBLIC — excluded from auth exactly like `/health` (it's the handshake clients use before they have credentials).
- **Completion-callback payload now carries `pipeline_run_id`.** The webhook POSTed to `callback_urls` carries the protocol `pipeline_run_id` field alongside the runtime's existing `pipeline_run_id`/`status` keys; the `X-Completion-Signature` is `HMAC-SHA256(secret, pipeline_run_id)` (unchanged scheme, renamed input). The `status` → `state` key rename lives in the pipelex runtime's delivery executor and ships with a later pipelex release — receivers should read `pipeline_run_id` + `status` for now.
- **Pipelex pinned to 0.33.0** (`PipelexMTHDSProtocol` — the renamed `PipelexRunner` — with protocol methods `execute`/`start`/`validate`/`models`/`version`; `PipelexRunResult`/`PipelexStartAck` response models).

### Added — MTHDS Protocol alignment

- **Committed OpenAPI artifact + drift gate.** `docs/openapi/pipelex-api.openapi.yaml` is the layer-2 contract, exported from the live app via `make openapi-export` and drift-checked in CI via `make openapi-check` (wired into the lint workflow and `make check`). The five protocol routes are tagged `x-mthds-protocol: true`; `/upload` and `/resolve-storage-url` are documented as NON-CONTRACT in their descriptions (kept in the schema for self-hosters' interactive docs).
- **Protocol conformance suite.** `tests/unit/test_protocol_conformance.py` gates CI on: the five protocol paths under `/v1` (and zero legacy paths), the `RunRequest` anyOf rule (422 on empty body), the public `/version` handshake + shape, client-supplied `pipeline_run_id` acceptance, and the completion-callback E2E — a local in-test HTTP receiver verifies delivery, the `X-Completion-Signature` HMAC, and the payload's `pipeline_run_id`/status fields through the real `DeliveryExecutor` code path (Temporal dispatch faked in-process).

### Changed — `/validate` fast path restored

- **Temporal-enabled `/validate` dispatches one in-process activity again.** The earlier temporary regression (direct in-process `validate_bundle` + `dry_run_pipeline`) is undone now that the pinned pipelex ships `wf_dry_validate` / `act_dry_validate`. On a Temporal-enabled runner, `/validate` runs the whole sweep **+** graph dry-run as ONE `act_dry_validate` activity (a single worker round-trip) instead of dispatching the dry-run pipeline pipe-by-pipe through Temporal (one workflow + activities per pipe) — restoring the fast path first added in PR #12. Direct (Temporal-disabled) mode is unchanged. Same wire contract; the error contract and best-effort-graph semantics are identical across both backends.

### Changed

- **Duplicate `pipeline_run_id` now returns 409 Conflict instead of 500.** `PipelineManagerAlreadyExistsError` — raised when a submission reuses a `pipeline_run_id` that is still registered for an in-flight run — is mapped to 409 via `_ERROR_TYPE_STATUS_OVERRIDES`, so a genuinely concurrent duplicate is a client-visible conflict rather than an opaque internal error. Pairs with the pipelex-side fix that frees a run's registry entry when it completes or fails, making serial resubmission of the same id succeed (previously every resubmission of a used id 500'd until process restart). Documented in [`docs/error-responses.md`](https://github.com/Pipelex/pipelex-api/blob/main/docs/error-responses.md).
- **Error-log disposition is now keyed off the final HTTP status, not the error domain.** A 4xx logs at `warning` (no traceback); a 5xx logs at `error` (with traceback). This keeps API-level 4xx overrides — the new 409 conflict, and the provider-429 passthrough — out of error dashboards instead of paging on a normal client conflict. The previous rule (only `INPUT`-domain → `warning`) left domain-less 4xx errors logging at `error`.
- **Temporal-enabled `/validate` now runs as ONE worker round-trip.** When `temporal.is_enabled` is true, the route dispatches the whole job — validation sweep **+** graph dry-run — as the one-step wrapper workflow `wf_dry_validate` (→ the single in-process `act_dry_validate` activity) via pipelex's `dispatch_dry_validate`, instead of running `validate_bundle` API-side and `dry_run_pipeline` as a top-level worker workflow with a tracing-backend round-trip. The worker traces the graph in memory and returns `{status map, graph_spec}` on the activity result; the route re-parses the blueprints and builds `pipe_io_contracts` from a local load-only library acquisition. The wire contract is unchanged on both backends: same 200 `ValidateResponse` envelope, same best-effort `graph_spec` (null when the graph dry-run fails), same RFC 7807 422 carrying `error_type=ValidationError` for the missing-`main_pipe` precondition and `error_type=ValidateBundleError` for validation failures — both with `error_domain=input` (the structured report crosses the activity boundary and the global handler renders it identically). Direct mode (Temporal disabled) is untouched. Requires a pipelex version that ships `act_dry_validate` (newer than v0.32.1).

### Breaking Changes

- **Every error response is now [RFC 7807 `application/problem+json`](https://github.com/Pipelex/pipelex-api/blob/main/docs/error-responses.md).** Replaces the legacy `{"detail": {"error_type", "message"}}` envelope across pipelex domain errors, validation (422), auth (401/403), payload limits (413), and the catch-all 500. Standard members on the wire: `type` / `title` / `status` / `detail` / `instance`. Extension members: `error_type`, `error_domain`, `retryable`, `request_id`, and — when populated by pipelex — `error_category`, `user_action`, `provider_metadata`, `model`, `provider`. Content-Type is `application/problem+json`. Clients reading the legacy `data.detail.message` must read RFC 7807 `detail` (top-level string) instead.
- **`/validate` failure envelope removed.** A failing validation no longer returns `HTTP 200` with `{success: false, mthds_contents, message}`; it now returns `HTTP 422` (`ValidateBundleError`) with the RFC 7807 envelope. The former 400 "no `main_pipe`" path is also 422 now. **Success path (200 `ValidateResponse`) is unchanged** — same `mthds_contents`, `pipelex_bundle_blueprint`, `graph_spec`, `pipe_io_contracts`, `success: true`, `message` fields. Cross-repo consumers in `pipelex-app` and `mthds-js` updated in companion PRs.
- **`X-Request-ID` is now echoed on every response** (success and error). Inbound `X-Request-ID` is respected; otherwise the server generates a UUID. The same id rides through `JobMetadata.request_id` to every Temporal worker log record.

### Added

- **`ERROR_DISCLOSURE` env var.** `verbose` (default) renders the full `ErrorReport`; `strict` redacts `detail` for non-caller-facing errors and always strips `model` / `provider` / `provider_metadata`. Provenance-gated via pipelex's `_authors_caller_facing_message` ClassVar — `error_domain` no longer drives redaction. Server logs stay verbose regardless of disclosure mode.
- **[`docs/error-responses.md`](https://github.com/Pipelex/pipelex-api/blob/main/docs/error-responses.md)** — public API error-contract page describing the envelope, status-code mapping (`input`→422, `config`/`runtime`→500), the `type` URI namespace, disclosure modes, request correlation, and worked examples. Linked from `docs/pipe-run.md` and `docs/pipe-validate.md`.
- **`allow_signatures` API flag.** Opt-in boolean on `/validate`, `/build/inputs`, `/build/output`, and `/build/runner`. When `true`, the validation sweep tolerates unimplemented `PipeSignature` placeholders (dry-running them by minting a mock) instead of rejecting the bundle. Defaults to `false` (strict).
- **Postman & `curl` bundle runner.** New `postman-run-bundle` Claude skill and `build_postman_query.py` script that turn a local MTHDS bundle into a Postman request, a `curl` command, or a direct API execution. Resolves the bundle exactly like `pipelex run bundle <path>` and targets `/api/v1/pipeline/execute`, `/start`, and `/api/v1/validate`.
- **Bundle testing Make targets.** `make bundle-run`, `bundle-validate`, `bundle-curl`, `bundle-postman`, and `bundle-dry` exercise a bundle against the API from the CLI.
- **Local Pipelex WIP support.** `make run-wip` / `install-wip-pipelex` run the API against a local, editable `pipelex` working tree without hand-editing `pyproject.toml`.

### Changed

- **Adapt to post-#931/#933 pipelex surface.**
  - Phase 6 module relocation: `EnvVarNotFoundError` is now imported from `pipelex.system.exceptions` (was `pipelex.system.environment`). Tests updated; no production code touched the moved import.
  - Acronym-casing fix: pipelex's `pascal_case_to_sentence` now preserves trailing acronym casing (`InvalidJSON` → `Invalid JSON`); the `test_error_uri.py::test_error_type_title` assertion updated.
  - **Native `request_id` wiring at dispatch.** `POST /pipeline/start` now reads the request-scoped `request_id` contextvar and passes it as `request_id=` to `pipeline_run_setup(...)`, so it lands on `JobMetadata.request_id` and rides every worker-side `WorkflowLog` record. No more `webhook.payload["request_id"]` piggyback needed (and `WebhookTarget.payload` would now reject it as a reserved key anyway).
  - **Cross-path consistency regression (T6).** New `tests/unit/test_webhook_recovery.py` pins the invariant: given the same source `ErrorReport`, the classification fields surface identically via the sync HTTP RFC 7807 response and via the webhook `error` payload (composed upstream by `DeliveryExecutor._notify_webhook`).
  - **STRICT-disclosure audit (no code change).** Confirmed `api/problem_document.py` delegates wholesale to `report.to_problem_document(disclosure_mode=...)`, so pipelex's provenance-gated keying flip (Decision D1) flows through untouched. The two `error_domain == INPUT` sites in `api/exception_handlers.py` are log-level switches, not wire-disclosure switches, and remain correct.
- **Shared request validation.** Consolidated the MTHDS payload validation (the `mthds_contents` bound + per-file size guard) and the new `allow_signatures` flag into a shared `MthdsContentsRequest` Pydantic base model that `/validate` and the build routes subclass, so the validation routes can't drift.
- **`/build/inputs` and `/build/output` reuse the validated library.** Both now read the requested pipe from the library `validate_bundle` already opened and left current, instead of opening and loading a second one — less work and memory per request — and scope the dry-run sweep to the requested pipe.
- **Unit tests run with Temporal disabled.** `tests/unit/conftest.py` forces `temporal_enabled=False`, so the suite executes pipelines (including dry-run validation) in-process and hermetically.
- **`pyproject.toml` tooling config.** Set pyright `venvPath` / `venv` and expanded the `exclude` lists to ignore `node_modules`, hidden files, and `.claude/`.

### Fixed

- **Library resource leak in `/validate`, `/build/inputs`, and `/build/output`.** The library `validate_bundle` opens and leaves current on success was never torn down, orphaning a library in the `LibraryManager` on every successful call. Each route now owns that teardown in a `finally`.
- **`/build/runner` returned 500 on a failed dry-run.** A failed dry-run of a caller-submitted bundle now becomes a 422 `ValidateBundleError` (RFC 7807 problem response), matching `/validate`, `/build/inputs`, and `/build/output`. (The bare `DryRunError` carried no `error_domain`, so the global handler had been rendering it as a server fault.)
- **`/build/runner` generated code for a `SKIPPED` pipe.** When the requested pipe was `SKIPPED` during validation (an unresolved cross-package dependency), the endpoint used to emit runner code for a pipeline that can't actually run; it now rejects the request with 422.
- **Makefile `help` output.** `Makefile_basics.mk` no longer overrides the root `help` target, so the local and deployment help sections all compose.

### Known follow-ups (deferred, not in this set of changes)

- Structured logging on `_notify_webhook` (`event=webhook_delivery` / `event=webhook_failure`) — lives in pipelex upstream at `delivery_executor.py`, not in this repo. Tracked for a separate pipelex PR.

## [v0.1.2] - 2026-05-20

### Changed

- **Trimmed `RequestUser` to `user_id` only.** Dropped the `email`, `sub`, and `auth_method` fields. The runner is a generic execution engine — the only piece of identity it consumes is an opaque user id, which it scopes S3 storage keys under (`<user_id>/...`). Anything else (email, OAuth subject, auth method) is metadata the runner has no use for; handlers that need it look it up by `user_id` against the deployment's own user store.
- **JWT auth now requires a `user_id` claim (UUID).** No fallback to the standard `sub` claim, and the value is now validated as a UUID (`^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$`) at the auth boundary. Storage URIs require the owner segment to match the same shape; provider-issued `sub` values like `"google#abc"` (or any non-UUID `user_id`) would otherwise let a caller upload to S3 under a key that `/resolve-storage-url` would later refuse to resolve. Deployments using OAuth JWTs must mint their own `user_id` claim (a UUID for that caller) when issuing tokens.
- **Forwarded identity headers reduced to a single `X-User-Id` (must be a UUID).** With `TRUST_FORWARDED_IDENTITY_HEADERS=true`, only `X-User-Id` is honored and its value is validated against the same UUID shape as JWT `user_id`. Non-UUID values are silently ignored and the request stays anonymous. The previous `X-User-Email`, `X-User-Sub`, and `X-Auth-Method` headers are gone — they were metadata the runner never used.
- Bumped Pipelex to v0.28.0. See changelog here: https://docs.pipelex.com/latest/changelog/

### Fixed

- `mkdocs build --strict` no longer fails on relative links inside the `CONTRIBUTING.md` snippet included into `docs/contributing.md`. Those links are authored to resolve from the repo root on GitHub; mkdocs validation for them is downgraded from `warn` to `info`.

### Security

- **Tightened `pipelex-storage://` owner-segment validation.** `parse_storage_uri` previously accepted any 36-character mix of hex and dashes (`^[a-f0-9-]{36}$`), so values like 36 dashes or `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` could pass through. The check now enforces the canonical UUID positional shape `8-4-4-4-12`, matching the validator newly applied at the auth boundary so the two layers cannot drift.

## [v0.1.1] - 2026-05-07

### Added

- `/release` Claude Code skill (`.claude/skills/release/`) automating the release workflow: version bump in `pyproject.toml`, changelog finalization, `make check`, `make li`, release branch creation, commit, push, and PR.

### Changed

- Bumped Pipelex to v0.27.0. See changelog here: https://docs.pipelex.com/latest/changelog/

## [v0.1.0] - 2026-05-04

### Changed

- **The published `pipelex/pipelex-api` Docker image is now generic.** Temporal is **off** by default, no S3 storage is configured, and no DynamoDB tracing is enabled. Anything environment-specific is now expected to come from a user-supplied `.pipelex/pipelex_override.toml` (or `pipelex_<env>.toml`) mounted into `/root/.pipelex/`. See [`docs/configuration.md`](https://github.com/Pipelex/pipelex-api/blob/main/docs/configuration.md).
- **Removed deployment-specific env configs from the repo.** `pipelex_dev.toml`, `pipelex_staging.toml`, `pipelex_prod.toml`, and `pipelex_service.toml` previously baked one specific deployment's Temporal cluster, S3 buckets, and DynamoDB table names into the public image. They are gone — bring your own via a mounted `.pipelex/` override (see [`docs/configuration.md`](https://github.com/Pipelex/pipelex-api/blob/main/docs/configuration.md)).
- **AWS/ECR deploy targets removed.** `Makefile.deploy.api.mk` now only contains `deploy-docker-hub`. The previous `deploy-api`, `deploy-api-dev`, `deploy-api-staging` targets and their corresponding workflows are gone — they were specific to one deployment's AWS account. CI in this repo now publishes to Docker Hub only on every push to `main`. Self-hosters wire their own deploy from a separate infra-as-code repo.
- **Hardcoded `temporal_enabled=True` removed from `api/main.py`.** Temporal is now controlled entirely by `[temporal] is_enabled` in your config, with no Python-level override.
- **Dockerfile cleans up `/app/.pipelex` after copying it to `/root/.pipelex`** so user-supplied overrides at `/root/.pipelex/*.toml` are not shadowed by a project-level `.pipelex/` inside the image.
- **`.env.example` trimmed** to universally-needed vars only (`PIPELEX_GATEWAY_API_KEY`). Auth, Temporal, and callback-secret vars are now optional / deployment-specific.
- **`COMPLETION_CALLBACK_SECRET` is no longer required at boot.** `api/routes/pipelex/pipeline.py` now reads it lazily inside `_completion_signature()` instead of at module import. The image boots with just `PIPELEX_GATEWAY_API_KEY`; the secret is only required when you actually use `POST /api/v1/pipeline/start` with a `callback_url`. See [`docs/pipe-run.md`](https://github.com/Pipelex/pipelex-api/blob/main/docs/pipe-run.md) → "Async Completion Callbacks".

### Added

- [`docs/configuration.md`](https://github.com/Pipelex/pipelex-api/blob/main/docs/configuration.md) — explains the env vars this Docker image accepts, the Pipelex config layering inside the container, and how to mount your own `.pipelex/` overrides. The actual Pipelex configuration syntax (storage, tracing, inference, Temporal, …) lives at https://docs.pipelex.com.

### Fixed

- Move `Pipelex.make()` from module top-level into a FastAPI `lifespan` handler in `api/main.py`. Importing `api.main` no longer mutates the global Pipelex singleton, which was causing `make t` to fail under `pytest-xdist` once enough unit tests existed for workers to share processes with the e2e import-smoke test.
- Set a placeholder `COMPLETION_CALLBACK_SECRET` in `tests/conftest.py` so test collection succeeds in CI environments where `.env` isn't present. `api/routes/pipelex/pipeline.py` reads this var at import time, which was breaking `make gha-tests` collection as soon as any test transitively imported `api.routes`.

### Security

- `/upload` now rejects unauthenticated and `anonymous` callers with `401 Unauthenticated`, mirroring `/resolve-storage-url`. Previously, anonymous uploads were silently accepted and stored under an `anonymous/assets/…` prefix.

### Changed

- `/upload` returns `400 InvalidBase64` (instead of `500`) when the request body's `data` field isn't valid base64. Genuine storage failures still surface as `500`.
- `UploadRequest` now uses `ConfigDict(extra="forbid")`, so unknown fields produce `422` instead of being silently ignored.
- **`mthds_content` → `mthds_contents`** — Updated `ApiRunner.start_pipeline`, pipeline routes, and build routes to use `mthds_contents: list[str] | None` instead of singular `mthds_content`. Aligns with the updated `RunnerProtocol` in `mthds>=0.2.0`.
- **`bundle_uri` → `bundle_uris`** — Renamed to `bundle_uris: list[str] | None` in `ApiRunner` to match the updated `PipelexRunner` interface.

## [v0.0.12] - 2026-01-15

### Changed

- Bump `pipelex` to `v0.18.0`, the `Chicago` release: See changelog [here](https://docs.pipelex.com/changelog/)

## [v0.0.11] - 2025-12-01

### Added

- `pyjwt` dependency.

## [v0.0.10] - 2025-12-01

### Changed

- Bump `pipelex` to `v0.17.3`: See `Pipelex` changelog [here](https://docs.pipelex.com/changelog/)

### Added

- JWT authentication support.

## [v0.0.9] - 2025-11-26

### Changed

- Bump `pipelex` to `v0.17.1`: See `Pipelex` changelog [here](https://docs.pipelex.com/changelog/)

## [v0.0.8] - 2025-11-04

### Added

- Documentation for the API.

### Changed

- Reverted the `all_blackboxai` routing profile to the pipelex default one.

## [v0.0.7] - 2025-10-29

### Changed

- Hardcoded routing profile `all_blackboxai` for the pipelex hackathon.

## [v0.0.6] - 2025-10-29

### Changed

- More robust library management.

## [v0.0.5] - 2025-10-27

### Fixed

- Updated `Pipelex` dependency to `v0.14.0`.

## [v0.0.4] - 2025-10-26

### Fixed

- Updated telemetry settings.

## [v0.0.3] - 2025-10-25

### Feature

- You can now run directly a pipelex bundle from the API.

### Added

- `Pipelex.make(IntegrationMode.FASTAPI)` to the API

## [v0.0.2] - 2e25-10-22

### Added

- `docker-compose.yml` file

### Changed

- `README.md` Added more precise instructions for local, docker run, and docker compose.

## [v0.0.1] - 2025-10-22

- Initial commit!
