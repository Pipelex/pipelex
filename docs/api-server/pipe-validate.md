# Pipe Validate

Validate MTHDS content by parsing, loading, and dry-running pipes without executing them.

**Endpoint:** `POST /v1/validate`

`/validate` is a **diagnostic endpoint**: any verdict the validator can produce — valid, invalid, or valid-but-not-runnable — rides an HTTP **200**, discriminated in the body on `is_valid`. "Invalid, here are the problems" is the *successful product* of the call, not a transport failure. Non-2xx is reserved for the cases where **no verdict could be produced** (a malformed request body, an `mthds_sources` length mismatch, a method tree that cannot be read, a `method_ref` that could not be resolved, auth, or a server fault).

**Request Body:**

```json
{
  "mthds_contents": ["domain = \"my_domain\"\ndescription = \"My domain\"\nmain_pipe = \"my_pipe\"\n\n[concept.MyResult]\ndescription = \"A result\"\n\n[pipe.my_pipe]\ntype = \"PipeLLM\"\ndescription = \"Process input\"\ninputs = { text = \"native.Text\" }\noutput = \"MyResult\""]
}
```

**Request Fields:**

- `mthds_contents` (list[str], optional): MTHDS contents to validate (always an array, even for a single file). Exactly one of `mthds_contents` / `files` / `method_ref` must be provided
- `files` (object, optional): The method as a map of file entries, the MTHDS standard's method tree, each value the file's text, `{"base64": "…"}` or `{"sha256": "…", "size": n}`, read as on a run — see [Validating a method tree](#validating-a-method-tree). Exactly one of `mthds_contents` / `files` / `method_ref`
- `dependencies` (object, optional): **Pipelex-API extension.** The method packages the method calls by address that the runner cannot fetch, each a map of file entries keyed by its address, as on a [run](pipe-run.md#sending-the-method-packages-the-method-calls). Accompanies `files`
- `method_ref` (string, optional): **Pipelex-API extension.** Validate a published method by address — `github.com/<owner>/<repo>` plus an optional package selector and `@<tag>` — resolved by this server through the same fetch path as a [`method_ref` run](pipe-run.md#running-a-method-by-address-method_ref): the repository is fetched at the tag, the package located by manifest identity, and its tree read from the commit's git objects and validated as a tree sent in `files` is — see [Validating a method tree](#validating-a-method-tree). Exactly one of `mthds_contents` / `files` / `method_ref`; `mthds_sources` cannot accompany it. A package holding Python and a `requirements.txt` has its requirements checked on this server against the packages the deployment's PipeFunc sandbox offers for them before anything is validated, and a requirement the sandbox does not meet, or a line the standard refuses, makes the verdict `is_valid: false` with one item per line, whose `source` is `requirements.txt` and whose `line` is the line's number; a deployment refusing the requirements with its own explanation, no environment it can build holding them, makes it `is_valid: false` with one item on `requirements.txt` and no line
- `read_scope` (string, optional): **Pipelex-API extension.** The scope the validation reads the method under, as a run's `read_scope`, which a multi-tenant host sends for the organization it serves; [a `jwt` caller may send only a scope under its own id](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups), else a `403 ReadScopeForbidden`. A hash entry of `files` resolves in that scope's blob store — see [Sending files by hash](pipe-run.md#sending-files-by-hash) — and the runner hands the scope to its validator, so a validation dispatched to a worker can hand it the method through that store — see [Where validation runs](#where-validation-runs). Omitted, a hash entry resolves in the caller's own id's store, but only a validation carrying it records the tree it read in the blob store, and the validator is handed no scope, so a dry run without one leaves nothing stored
- `allow_signatures` (boolean, optional, default `false`): controls only the **sweep mechanics** for `PipeSignature` placeholders — whether signature pipes are mock-run during the dry-run sweep and therefore listed in `validated_pipes`. It does **not** change the verdict: an unimplemented signature is never a rejection, it is a *runnability fact* reported via `pending_signatures` + `is_runnable` in both modes
- `mthds_sources` (list[str] | null, optional): per-file sources, parallel to `mthds_contents` — see [Sourcing submitted files](#sourcing-submitted-files). When present it must match `mthds_contents` in length (a mismatch is a 422 request error), and it accompanies `mthds_contents` alone, since a tree's files are named by their tree paths
- `resources` (object | null, optional): **Pipelex-API extension.** The files the bundle's steps read, such as a `PipeDocGen` step's `template_file`, as a map from the path the step names to the file's bytes in standard base64 — see [Sending the files the steps read](#sending-the-files-the-steps-read-resources). It accompanies `mthds_contents` or `files`, whose tree each file joins; beside `method_ref` it is a 422
- `render` (list[str], optional, default `[]`): opt-in *rendered text* to attach to the verdict — see [Opt-in extras](#opt-in-extras-render-and-views)
- `views` (list[str], optional, default `[]`): opt-in *structured views* to attach to the verdict — see [Opt-in extras](#opt-in-extras-render-and-views)
- `orchestration_mode` (string | null, optional): per-request backend override for the validation dispatch — see [Where validation runs](#where-validation-runs). Honored only when the deployment allows it; a forbidden override is a 403
- `analytics_groups` (object | null, optional): **Pipelex-API extension.** The groups the caller belongs to, as a mapping of group type to group key, with the same rules as on a run — see [Who the validation is done for](#who-the-validation-is-done-for). A mapping outside those rules is a 422 whose `error_type` is `InvalidAnalyticsGroups`

**Response (the verdict union):**

The 200 body is one of two arms, discriminated on the mandatory `is_valid` field. A consumer pattern-matches `is_valid` to learn the verdict — it never inspects a status code or catches an exception body.

**Valid arm (`is_valid: true`)** — the canonical Pipelex validation report (the exact same artifact shapes `PipelexMTHDSProtocol.validate` returns when the runtime is used locally) plus this server's wire-only extras (`mthds_contents` echo, `message`, `default_pipe_ref`):

```json
{
  "is_valid": true,
  "bundle_blueprint": {
    "domain": "my_domain",
    "description": "My domain",
    "main_pipe": "my_pipe",
    "concept": { "...": "..." },
    "pipe": { "...": "..." }
  },
  "pipe_io_contracts": {
    "my_domain.my_pipe": {
      "inputs": { "text": { "concept_ref": "native.Text", "presence": "plain", "multiplicity": "single", "item_count": null, "json_schema": { "...": "..." } } },
      "output": { "concept_ref": "my_domain.MyResult", "multiplicity": "single", "item_count": null, "optional": false, "json_schema": { "...": "..." } }
    }
  },
  "graph_spec": { "...": "..." },
  "validated_pipes": [
    { "pipe_ref": "my_domain.my_pipe", "status": "SUCCESS" }
  ],
  "pending_signatures": [],
  "is_runnable": true,
  "mthds_contents": ["..."],
  "message": "MTHDS content validated successfully",
  "default_pipe_ref": "my_domain.my_pipe"
}
```

**Response Fields (canonical report — valid arm):**

- `is_valid` (`true`): the discriminant of the valid arm — always `true` on this report
- `bundle_blueprint` (object): the batch's primary blueprint — the first file declaring `main_pipe`, else the first file
- `pipe_io_contracts` (object): per-pipe input/output contracts, keyed by the namespaced `pipe_ref` (`domain.code`). Each input carries its `concept_ref`, `presence`, `multiplicity` (`single` | `variable` | `fixed`), `item_count` and the JSON Schema of its content; the output carries its fully qualified `concept_ref`, `multiplicity`, `item_count`, `optional` and the JSON Schema of its payload. `item_count` is the exact count on `fixed`, always greater than one since `Concept[1]` reads as `single`, and `null` otherwise, so an output declared `Text[3]` reports `"multiplicity": "fixed", "item_count": 3`
- `graph_spec` (object | null): best-effort execution graph of the pipe a selector-less run of this request would execute — the pipe [`default_pipe_ref`](#the-effective-entry-pipe) names — dry-run against the validated library; `null` when no entry pipe is determined or the graph dry-run degrades
- `validated_pipes` (list): per-pipe sweep outcomes — `{pipe_ref, status}` entries with status `SUCCESS` | `FAILURE` | `SKIPPED`
- `warnings` (list): advisory findings that never flip `is_valid`, each with the same shape as a `validation_errors` item, so one parser reads both. Four families, always in this order: the useless-`!` lint (`optional_force_redundant`), the entry-pipe vacuous-presence lint (`input_presence_vacuous`), the intent-hint lints (`hint_unknown_key`, `hint_unknown_intent`, `hint_inapplicable_intent`), and the warnings a `PipeDocGen` step's template check found in its office template file during the dry run (`template_check_warning`, a `dry_run` item carrying `pipe_code`, `domain_code`, `template_file` and `template_location`). Unset locators are `null` on this arm. Empty when there is nothing to report
- `pending_signatures` (list[str]): namespaced refs of pipes still declared as signatures (contract-only pipes — `inputs`/`output` with no `type` and no implementation) in the assembled library — what remains to implement
- `is_runnable` (boolean): `pending_signatures` is empty — whether the validated library is complete enough to run

**Response Fields (wire extras, valid arm only, this server only):**

- `mthds_contents` (list[str]): echo of the validated request contents
- `message` (string): status message
- `default_pipe_ref` (string | null): the qualified `domain.pipe_code` a caller gets by **omitting** the pipe selector — the pipe a selector-less run of this same request would execute. See [The effective entry pipe](#the-effective-entry-pipe) below

**Response Fields (opt-in, present only when requested):**

- `input_form` (object, valid arm only, requires `views: ["input_form"]`): per-pipe input-form descriptors, keyed by the same namespaced `pipe_ref` as `pipe_io_contracts`. Each entry carries an ordered `fields` list describing what a caller must collect to run that pipe — a field's `kind` (drawn from a closed vocabulary), its `name`, whether it is `required`, whether an empty value should `gate` the run, and the per-kind detail (`choices`, `item_count`, `default_value`, nested `concept_ref`, …). It is a **projection of facts the verdict already states**, derived from what the bundle authored rather than from the emitted JSON Schema, so a client can render a run form from the verdict alone
- `output_form` (object, valid arm only, requires `views: ["output_form"]`): per-pipe output-form descriptors, keyed by the same namespaced `pipe_ref` as `pipe_io_contracts`. Each entry carries a single `field`, drawn from the same closed field vocabulary `input_form` uses, describing what that pipe produces — so a caller rendering a result, or registering a tool signature with a return type, reads the output's shape without inferring it from a value. Its JSON Schema is not here: that rides `pipe_io_contracts[…].output.json_schema`, and the pairing is the point — the descriptor states what the output IS, the schema names the property its payload arrives under
- `rendered_markdown` (string, both arms, requires `render: ["markdown"]`): a server-rendered Markdown view of the verdict, produced by the same renderers the local CLI uses

**Invalid arm (`is_valid: false`)** — the per-error diagnostics plus the runnability facts; the structural artifacts (`bundle_blueprint`, `pipe_io_contracts`, `graph_spec`, `validated_pipes`) and `mthds_contents` are **absent**, because they do not exist when load/parse/wiring failed:

```json
{
  "is_valid": false,
  "validation_errors": [
    {
      "category": "blueprint_validation",
      "message": "Value error, Invalid main pipe syntax 'Not A Valid Pipe Code!'. Must be in snake_case.",
      "error_type": "invalid_pipe_code_syntax",
      "domain_code": "broken",
      "source": "broken.mthds"
    }
  ],
  "pending_signatures": [],
  "is_runnable": false,
  "message": "Value error, Invalid main pipe syntax 'Not A Valid Pipe Code!'. Must be in snake_case."
}
```

**Response Fields (invalid arm):**

- `is_valid` (`false`): the discriminant of the invalid arm
- `validation_errors` (list): the structured per-error diagnostics a client maps to per-line problems — built by pipelex's one shared builder, so they are byte-for-byte the same items the agent CLI emits. Each item carries a `category` (the closed set `blueprint_validation` | `pipe_factory` | `pipe_validation` | `dry_run`), a `message`, and the locators the runtime can attribute (`error_type`, `pipe_code` / `concept_code` / `domain_code`, `field_path` / `field_name`, and `source`). Absent locators are omitted, not null. An item may also carry a **`suggested_fix`** — a structured, deterministic repair (`fix_code`, `description`, `safety: safe|unsafe`, and the `ops[]` of semantic TOML patch operations to apply). It is present only when the fix planner derived one from the typed error data; a client that ignores it behaves exactly as before. See [Error Responses → Structured validation errors](error-responses.md#structured-validation-errors) and [→ Suggested fixes](error-responses.md#suggested-fixes) for every field. The array is **never empty on an invalid verdict** (the structured-info invariant is total): a failing dry run becomes one `dry_run` item per failing pipe, located at the innermost pipe that failed (its `pipe_code`, `domain_code` and, when known, `source`), a TOML syntax error carries the `line` and `column` the parser stopped at, and a parse-level failure with no attributable locator (an empty blueprint, an elaborator failure) becomes one `blueprint_validation` residual item carrying the message (no `source`). Every refusal of the bundle while it loads is an item of the verdict, never a no-verdict `5xx`: an unknown model is an `unknown_model` item on the pipe's `model` field (a reference the deck does not define, or a bare handle it serves only as another model type, such as an LLM named in a `PipeImgGen`; [`GET /v1/models/check`](models.md#check-a-model-reference) answers the same question for one reference), a model setting the model it resolves to refuses (a reasoning setting on a model that does not reason, for instance) is an `llm_setting_refused_by_model` item on the field naming the setting, a `PipeFunc` step whose function its method's files do not hold, or do not define as a top-level function marked `@pipe_func()`, is a `pipe_func_function_refused` item on its `function_name` field, and a call into a method package this runtime cannot resolve (not installed and not fetchable, or a fetch that failed) is an `unresolved_package_dependency` item on the first pipe naming the package, whose `missing_pipe_code` is the reference as written, `<address>->domain.code`
- `pending_signatures` (list[str]): best-effort outstanding signatures (empty on the invalid arm, since no library was assembled)
- `is_runnable` (`false`): an invalid bundle is never runnable
- `message` (string): the human-readable verdict summary: the lone item's message when there is one item, `N validation errors (first: <the first item's message>)` when there are several, and the parser's own message for a parse-level failure

## What This Endpoint Does

The route wraps the runtime's protocol `validate`: parse → load → dry-run-sweep every pipe → build the per-pipe IO contracts → best-effort graph of the entry pipe → assemble the canonical report. The runner returns the verdict as a value — the canonical report on the valid arm, or a `BundleValidationFailure` (the refusal's problem with its validation items, a bundle the caller can fix) on the invalid arm — and the route maps the invalid verdict to the 200 invalid arm by matching the returned value, never by catching a transport error. A bundle that declares no `main_pipe`, when no manifest names one either, validates normally and simply carries `graph_spec: null` — there is no main-pipe precondition.

## The effective entry pipe

`default_pipe_ref` states which pipe this request's closure would run if the caller named none. It applies the run routes' own precedence, minus the request selector `/validate` does not have:

1. a `method_ref`'s fetched package manifest (`METHODS.toml`) `main_pipe` — the package author's declared entry pipe, qualified against the closure;
2. otherwise, and when the manifest declares none, the closure's primary blueprint's `main_pipe` (the first file declaring one), qualified by its domain.

It is `null` when no entry pipe is determined — no blueprint declares `main_pipe`, or a manifest names a pipe the closure does not declare, or declares in several domains. In those last two cases a selector-less run by that address would fail to resolve the manifest's pipe too, so the field says nothing rather than naming the closure's pipe, which no such run would execute.

The field exists because the canonical report is **manifest-blind**: `bundle_blueprint` is the batch's primary blueprint, so for a package whose `METHODS.toml` entry differs from — or exists without — a bundle-level `main_pipe`, a consumer deriving the entry pipe from `bundle_blueprint.main_pipe` alone gets the wrong pipe, or none. Reading `default_pipe_ref` is how a client projects an entry signature that matches what [`POST /v1/execute`](pipe-run.md#running-a-method-by-address-method_ref) and `POST /v1/start` actually default to.

The graph follows the same precedence: on a `method_ref` request whose manifest names a `main_pipe`, the route hands that pipe to the runtime as the graph target, so `graph_spec` draws the pipe `default_pipe_ref` names — including for a package whose bundles declare no `main_pipe` at all, whose entry pipe only the manifest states. A manifest `main_pipe` the closure does not resolve leaves both fields `null` rather than graphing the closure's own `main_pipe`, which no run by that address executes. The target travels with the dispatch, so a validation sent to a worker is graphed the same way.

It states the **run** default, which is looser than the [`/pipe-io`](pipe-io.md#pipe-selection) selection chain on one point: a closure whose domains each declare a `main_pipe` cannot be defaulted on `/pipe-io` (a `422`), but `/execute` and `/start` run its first declaring blueprint happily — so this field names that pipe rather than reporting `null`.

The field rides the valid arm only. The invalid arm assembles no library, so there is no entry pipe to name and the field is absent, like the other structural artifacts.

## Opt-in extras (`render` and `views`)

A caller that wants the artifacts without the verdict — to show a method, prepare its inputs or generate types for it — reads [`POST /v1/pipe-io`](pipe-io.md) instead: it returns `pipe_io_contracts`, `input_form` and `output_form` for one pipe or every pipe, equal to this route's for a closure both accept, with no dry-run sweep.

The verdict body is lean by default: a request that sends neither list gets exactly the structured contract described above, byte-identical to a request that omits both fields. This matters because the highest-frequency callers of `/validate` — editor hooks, CI gates, agent loops — read a handful of fields and discard the rest, and should never pay for bytes they throw away.

Two independent opt-in axes attach more:

- **`render`** produces *rendered text*, attached under a mechanical `rendered_<format>` key. The supported token is `markdown`, which attaches `rendered_markdown` on **both** 200 arms — failure text is exactly what a human-facing surface wants.
- **`views`** attaches a *structured* artifact under a **same-named** top-level field. The supported tokens are `input_form` and `output_form`, each attaching a field of its own name on the **valid arm only**: the descriptors derive from a library that was never assembled when load/parse/wiring failed, so they follow `bundle_blueprint`, `pipe_io_contracts` and `graph_spec` into absence on the invalid arm.

Both lists share the same mechanics, and both are deliberately typed as plain `list[str]` rather than closed enums at the request boundary:

- Each token is resolved **independently** against the server's supported set. A known token is honored; an unknown or unsupported one is **silently dropped — never a 422**. A stale token from an older client must not fail the call, and one bad token in a list does not poison the good ones.
- The lists are treated as **sets**: order-insensitive and deduped.
- They are **independent of each other**. A request may carry both, and each resolves its own tokens against its own supported set. A token is unknown to the other list — sending `render: ["input_form"]` attaches nothing at all.
- Neither ever appears on a no-verdict response. No verdict, no view.

Neither axis is part of the verdict contract: a machine consumer branches on the structured fields, and an extra is a presentation or a projection layered on top. That is what keeps adding a token, or changing what one renders, a non-breaking change.

## Sourcing submitted files

The submit path carries bundle text, not file paths, so by default the runtime cannot tell the client which file an error belongs to — `source` comes back `null`. Send `mthds_sources` parallel to `mthds_contents` to fix this: each source is the logical identity of that content (e.g. the file's path relative to the submitted directory), and the runtime threads it onto the corresponding `blueprint.source`. The source then rides back on both arms — `bundle_blueprint.source` on the valid arm, and `validation_errors[].source` on the invalid arm — so a multi-file editor client can map a cross-file diagnostic to the file that owns it. Omit `mthds_sources` (or send `null`) and behavior is exactly as before. The list, when present, must be the same length as `mthds_contents`; a mismatch is a request-shape 422 (it is the caller's wiring bug, caught before the validation sweep runs). A source is a label for diagnostics and nothing more: even one naming a real file on the server is never a directory the server reads from, so a step's template file comes from [`resources`](#sending-the-files-the-steps-read-resources) alone, and an address-based reference is not searched for above it.

## Validating a method tree

A method sent in `files`, or fetched by `method_ref`, is validated whole, as it would run: the runner reads the tree under the standard's rule, writes it into a temporary directory, and validates it as one library directory of the caller's, with the packages it ships in `dependencies` (or, for a `method_ref` package, under its own `.mthds/methods/<name>/`) loaded beside it, so a call into one resolves as on a run. Every bundle is named by its tree path, so `validation_errors[].source` names the owning file, and no item names a path on the server.

- **Python is checked by syntax.** Every `.py` file of the tree is read and compiled, never imported or run, whether or not a step names it: a file that does not parse, or is not UTF-8, makes the verdict `is_valid: false` with an item whose `source` is the file's tree path and whose `line` is the line of the error. A `PipeFunc` step's function is then located in the tree and its form checked statically. As on a run, a tree holding Python is refused with a `403` (`CustomCodeRequiresSandbox`) on a deployment that is not sandbox-hosted.
- **The default pipe and the graph follow the tree's entry pipe.** `default_pipe_ref` is the pipe the protocol's rule names, the `main_pipe` of the root `METHODS.toml` or the one `main_pipe` its bundles declare, and the graph is drawn from it. A tree with no entry pipe validates with `default_pipe_ref: null` and `graph_spec: null`.
- **Refusals of the tree itself produce no verdict**: a key the tree's rule refuses or a malformed entry is a **422** `InvalidMethodFiles`, a hash the runner does not hold a **422** `MissingBlobs`, and a tree past its limits a **422** `MethodTreeTooLarge`, as on a [run](pipe-run.md#sending-a-method-as-a-tree).
- **The `mthds_contents` echo** holds the text of the tree's own bundles.

## Sending the files the steps read (`resources`)

A bundle sent as content has no directory, so a file one of its steps reads from beside the bundle, such as a `PipeDocGen` step's `template_file`, is sent with it in `resources`. The same field, with the same rules, is accepted by [`/v1/execute` and `/v1/start`](pipe-run.md), [`/v1/pipe-io`](pipe-io.md), and [`/v1/resolve` and `/v1/codegen`](codegen.md#selecting-the-method).

```json
{
  "mthds_contents": ["domain = \"invoicing\"\n...\n[pipe.print_invoice]\ntype = \"PipeDocGen\"\n...\nformat = \"docx\"\ntemplate_file = \"templates/invoice.docx\""],
  "resources": {"templates/invoice.docx": "UEsDBBQABgAIAAAAIQ..."}
}
```

- **Each key is the path a step names**, relative to the bundle and written with forward slashes, exactly as in its `template_file`. `.` segments and repeated slashes collapse, so `./templates/invoice.docx` names the same file; every bundle of the request is read as sitting in one directory. An empty or absolute path, a `..` segment, a backslash, a colon, or two keys naming the same file is a **422** `InvalidResourcePath`, refused before any value is decoded. A method sent as a tree may hold the file instead, beside the bundle whose step names it; beside a tree, each key of `resources` joins it at that path from the tree's root, and a file the tree already holds must have the same bytes (see [Pipe Run](pipe-run.md#sending-a-method-as-a-tree)).
- **Each value is the file's bytes** in standard base64 (RFC 4648, with padding). A value that does not decode is a **400** `InvalidBase64`.
- **Beside inline contents, every file must be one a step names.** A file no step of the bundle reads is a **422** problem with the code `request.invalid`, whose operator view's message lists the unnamed paths: a misspelled key fails loudly rather than leaving its step without its file. This is a request error, never an `is_valid: false` verdict. Beside a tree, a file no step names is kept like any other file of the tree.
- **The sizes are bounded**: at most `MAX_RESOURCES_PER_REQUEST` files (32 by default), each at most `MAX_RESOURCE_FILE_KIB` once decoded (5 MiB by default), and at most `MAX_RESOURCES_TOTAL_KIB` across the request (10 MiB by default). A request over any of them is a **413** `PayloadTooLarge`, an oversized file refused on its encoded length before it is decoded. The whole body stays under `MAX_REQUEST_BODY_MIB` as well.
- **The files make one method tree**, with the request's bundles at its root. A run names that tree by its digest, as it names the tree of a method loaded from a directory, and carries none of the files in its payloads, a remote orchestrator's included: the step that reads one reads it from the tree, through the deployment's method file store. Two files colliding in one tree, such as two keys equal once case-folded, are a **422** `BundleResourcePathError`.

The files are checked as files on disk are. An `.html` template file is checked against the step's inputs when the bundle loads, and the document engine's template check runs on an office template file in the validation's dry run, where its errors are validation errors on the step. A step whose `template_file` could not be a key, being empty or absolute, or holding a `..` segment, a backslash, a colon or a NUL character, is refused when its bundle is parsed, whatever the request sends: the verdict's one item is a `blueprint_validation` item located at the step by its `pipe_code` and by `field_path` `pipe.<code>`, whose message names the field without repeating the path. A step whose `template_file` could be a key but was not sent is refused at load, and the verdict's `validation_errors[]` says the file was not supplied with its bundle and names the key it is expected under.

## Where validation runs

Validation is **`orchestration_mode`-aware**, the same way `/start` is: the runner resolves the effective backend (the deployment default plus the optional per-request `orchestration_mode` override) and dispatches through the bundle-validator registry. Validation is inherently blocking, so there is no delivery axis here — only the backend varies. On the orchestrator-agnostic base — and for `orchestration_mode: direct` — the whole job runs **in-process in one library load on the API side**. On an orchestrator flavor whose mode is selected (e.g. `temporal`), the whole job is **dispatched to a worker** instead, and the API side assembles the same canonical report from the worker's result without loading a library. Either way the verdict is byte-identical: the backend changes, the contract does not. A per-request override the deployment forbids is refused with a 403.

The validator is handed the request's `read_scope`, the scope a run of the same request reads under, so a validator that dispatches to a worker can hand it the method's trees through that scope's blob store and the worker read them by digest, as a run's worker reads its method's files under the run's read scope. A tree sent in `files` is already recorded there when the validator is called. A request without a `read_scope` hands the validator none, never the caller's own id, so a dispatched validation stores nothing under a prefix no host lists or erases.

> **Resource note for deployment.** When validation runs in-process (the agnostic base, or `direct` mode), the API server loads the method library to validate, so a deployment that receives large or frequent in-process `/validate` traffic should be sized for that load (memory + CPU for library assembly and the graph dry-run). On a distributed-execution flavor that dispatches validation to a worker, the library work happens worker-side; size the workers accordingly.

The graph is best-effort: a bundle that validates but whose graph dry-run fails still returns 200 on the valid arm with `graph_spec: null`.

## Who the validation is done for

A validation is not a run, but it still emits telemetry: the sweep's `pipe_dry_run` event and every dry run it performs. The route hands the runtime the caller it is working for — the authenticated user, exactly as a run states it (the single-tenant placeholder when the deployment has no user model), and the request's `analytics_groups`, or none — and the runtime attributes that telemetry to them rather than to the deployment's configured identity. The caller travels with the dispatch, so a validation sent to a worker is attributed the same way. How each telemetry stream then treats the caller is the runtime's decision, described with [`analytics_groups` on a run](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups).

## No-verdict (non-2xx) responses

Only conditions where the endpoint could not produce a verdict are non-2xx, rendered as [RFC 9457 problem documents](error-responses.md):

- **422** — a malformed request body, an `mthds_sources` / `mthds_contents` length mismatch, more or fewer than one of `mthds_contents` / `files` / `method_ref`, or a malformed `analytics_groups` (`error_type` `InvalidAnalyticsGroups`) — request-shape errors caught before the runtime.
- **422** on a method tree — a key or entry the tree's rule refuses (`InvalidMethodFiles`), a hash entry the runner does not hold (`MissingBlobs`), or a tree past its limits (`MethodTreeTooLarge`) — see [Validating a method tree](#validating-a-method-tree).
- **422**, **413** and **400** on `resources` — a path that cannot name a file inside the bundle (`InvalidResourcePath`), a file no step names (`request.invalid`), files that cannot make one tree (`request.invalid`, or `security.input_path_refused` for a path the tree rule refuses), a file or a request over its size limit (`PayloadTooLarge`), or a value that is not base64 (`InvalidBase64`) — see [Sending the files the steps read](#sending-the-files-the-steps-read-resources).
- **401 / 403** — unauthenticated / forbidden (including a per-request `orchestration_mode` override the deployment does not allow).
- **`method_ref` resolution failures** — a selector that could not be resolved produced no verdict, so it is never rendered as `is_valid: false`: a malformed reference is a **422** `request.invalid`, a failed fetch a **502** `method.fetch_failed`, no matching package in the repository a **404** `method.not_found`, the sandbox gate on custom Python a **403** `CustomCodeRequiresSandbox`, and the refusal of Python structure classes a **422** `pipelex.deployment.python_structures_refused` — the same statuses and codes as on the run routes (see the [error table](pipe-run.md#running-a-method-by-address-method_ref)).
- **5xx** — a server fault (including a host-wiring programmer error, surfaced as `runtime.unexpected`).

Read it as one rule: a non-2xx on `/validate` always means "the endpoint could not produce a verdict," never "your bundle is bad."
