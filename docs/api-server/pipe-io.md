# Pipe I/O

Return a method's I/O artifacts — its pipe I/O contracts, its input form and its output form — without validating it.

**Endpoint:** `POST /v1/pipe-io`

The route resolves the closure through the same static core as [`POST /v1/resolve`](codegen.md#resolve), selects a pipe with the [selection chain](#pipe-selection) below, and derives the three artifacts with the builder that [`POST /v1/validate`](pipe-validate.md) and every run already call. It runs **no dry-run sweep**, so a call costs one load and one derivation, where `/v1/validate` mock-runs every pipe of the method. A caller that shows a method, prepares its inputs or generates types for it reads this route; a caller that needs the dry-run verdict or the dry-run graph stays on `/v1/validate`, whose `views` still attach both forms beside the verdict.

It is a **Pipelex API extension**, not an MTHDS Protocol route: it is not tagged `x-mthds-protocol` in the [OpenAPI artifact](openapi/pipelex-api.openapi.yaml). The artifacts it carries are the standard's, under their neutral names — see the MTHDS specification's pages on [pipe I/O contracts, the input-form descriptor and the output-form descriptor](https://mthds.ai).

It speaks the `/v1/validate` verdict discipline: a **produced verdict is always a `200`** discriminated on `is_valid`, and a non-2xx is reserved for a request that produced no verdict.

## Request

The body names the method as the [crate routes](codegen.md#selecting-the-method) do, a method tree read exactly as [`/v1/validate`](pipe-validate.md#validating-a-method-tree) and the run routes read it, plus a pipe selector and two opt-ins:

- `files` (object) **or** `method_ref` (string), exactly one: the method, as on `/v1/resolve`. `files` is the MTHDS protocol's map of file entries, each key a tree path and each value the file's text, `{"base64": "…"}` or `{"sha256": "…", "size": n}`; `method_ref` an address-form reference to a published package, whose whole tree is fetched. Neither or both is a request-shape `422`.
- `dependencies` (object, optional): the method packages the method calls by address, each a map of file entries keyed by its address, as on a [run](pipe-run.md#sending-the-method-packages-the-method-calls). It accompanies `files` only.
- `pipe_ref` (string, optional): the qualified ref `domain.pipe_code` of the pipe to describe. Omitted, the selection chain below decides.
- `all_pipes` (boolean, default `false`): describe every pipe the closure loads instead of the selected one.
- `include_files` (boolean, default `false`): echo the text of the method's own `.mthds` bundles on the valid arm.
- `resources` (object, optional): files the method's steps read, such as a `PipeDocGen` step's `template_file`, keyed by the path from the tree's root, each in standard base64, joining the tree as on [`/v1/validate`](pipe-validate.md#sending-the-files-the-steps-read-resources). It accompanies `files` only. A step whose template file the tree does not hold makes the method invalid.
- `read_scope` (string, optional): **Pipelex-API extension.** The scope the request reads the method under, as on `/v1/validate`: a hash entry of `files` resolves in that scope's blob store, and only a request carrying it records the tree it read there; [a `jwt` caller may send only a scope under its own id](pipe-run.md#host-supplied-run-context-storage_scope-and-analytics_groups), else a `403 ReadScopeForbidden`.

There is no `views` field, because the valid arm always carries all three artifacts. The hosted API also accepts a catalog `method_id`, which the platform resolves into the method's `files` before forwarding, so this server never declares it.

```json
{
  "files": {
    "METHODS.toml": "...manifest...",
    "main.mthds": "...bundle...",
    "templates/invoice.docx": { "base64": "UEsDBBQABgAIAAAAIQ..." }
  },
  "all_pipes": true,
  "include_files": true
}
```

The tree's refusals produce no verdict, as on `/v1/validate`: an `InvalidMethodFiles`, `MissingBlobs`, `MethodTreeTooLarge` or `InvalidBundle` `422`, and the custom-Python policy's `403`s (see [No verdict](#no-verdict)).

## Pipe selection

The selection chain takes the request's `pipe_ref`; else the `main_pipe` of the `METHODS.toml` at the tree's root, whether the tree was fetched by `method_ref` or sent in `files`; else the closure's own `main_pipe` declaration, when exactly one domain declares one. A root `METHODS.toml` the route cannot read as a manifest, being no UTF-8 text or no valid manifest, is a `422 MethodEntryError` when the request names no pipe. A request naming its pipe in `pipe_ref` never reads the manifest to select it, so there a manifest the route cannot read refuses nothing and only leaves `default_pipe_ref` a stated `null`. The chain stops at the first link that is present, so a manifest `main_pipe` the closure does not declare, or declares in several domains, is a failed selection rather than a fall-through to the closure's declarations.

The closure is resolved first, so an invalid closure answers its invalid verdict whatever `pipe_ref` names. For a valid closure these selections are refused with an input `422` `problem+json`. Its `error_type` is the pipelex entry-lookup class that names the failure, never the `ValidationError` of a malformed request, so a client tells a selection refusal from a request-shape one by that field:

- `EntryPipeNotFoundError` for a `pipe_ref` that names no pipe of the closure, for a manifest `main_pipe` the closure does not declare, and, without `all_pipes`, for a request with no `pipe_ref` whose closure declares no `main_pipe`;
- `EntryPipeAmbiguousError` for a bare code that matches pipes in several domains, whether the request or the manifest spelled it, and, without `all_pipes`, for a request with no `pipe_ref` whose closure declares several `main_pipe`s.

The `detail` says which case it is and, for an ambiguity, names the qualified refs to choose from; the candidates are in the `detail` alone, with no structured list, as on the run routes. The problem's `code` tells the cases apart, and its `type` and `title` are the code's: `request.pipe_not_found` for a `pipe_ref` that names no pipe, `request.pipe_ambiguous` for an ambiguous one or a closure declaring several `main_pipe`s, `request.pipe_unspecified` for a request with no `pipe_ref` over a closure declaring none, and `method.pipe_unresolved` for a manifest `main_pipe` the closure does not declare or matches ambiguously. Its `user_action` is the class's too, advising a check of the pipe code, except for a request with no `pipe_ref` whose closure declares no `main_pipe` or several, where it asks for a `pipe_ref` instead.

An unknown or ambiguous `pipe_ref` answers the `error_type` the run routes answer for the same `pipe_code`. A closure declaring no `main_pipe`, or several, has no run-route twin: this route refuses both as the pipe-selector design classifies them, while a run over such a closure today fails with a `500` or runs the first declaration.

A bare `pipe_ref` that matches one pipe (`echo` where `smoke.echo` is meant) is still resolved today, and the valid arm reports the qualified ref.

**With `all_pipes: true` the route never refuses for want of an entry pipe**, so a method that declares no entry pipe, or several, is still describable. The valid arm's `pipe_ref` is then the requested ref (an unknown one is still a `422`), else the chain's answer, else `null`.

## Response (valid verdict)

```json
{
  "is_valid": true,
  "pipe_ref": "smoke.echo",
  "pipe_io_contracts": { "smoke.echo": { "inputs": { "…": {} }, "output": { "…": {} } } },
  "input_form": { "smoke.echo": { "fields": [ { "kind": "prose", "name": "text", "…": "…" } ] } },
  "output_form": { "smoke.echo": { "field": { "kind": "prose", "name": "output", "…": "…" } } },
  "default_pipe_ref": "smoke.echo",
  "pending_signatures": [],
  "is_runnable": true,
  "files": { "main.mthds": "...bundle..." }
}
```

- `is_valid` (`true`): the closure parsed, loaded and passed static validation. It does **not** mean a dry run passed; this route runs none.
- `pipe_ref` (string | null): the qualified ref the selection resolved, read off the resolved pipe and never echoed from the request. `null` only under `all_pipes` when nothing resolves.
- `pipe_io_contracts`, `input_form`, `output_form` (objects keyed by qualified `pipe_ref`): the three artifacts, sharing one key set — the resolved `pipe_ref` alone by default, every pipe the closure loads under `all_pipes`.
- `default_pipe_ref` (string | null): the method's own entry pipe, the selection chain without the request's `pipe_ref`. A request that omits `pipe_ref` therefore always answers `pipe_ref == default_pipe_ref`. When the request named a pipe, or asked for `all_pipes`, and the chain finds no entry pipe or several, the field is a stated `null`, as it is when the request named a pipe and the root `METHODS.toml` cannot be read.
- `pending_signatures` (list of strings) and `is_runnable` (boolean): exactly what they mean on `/v1/validate` — the qualified refs of the pipes still declared as signatures, and `not pending_signatures`. Both come from the loaded library with no dry run, so a method whose dry run would fail is still reported runnable here.
- `files` (object, only with `include_files: true`): the text of each `.mthds` bundle of the method's own tree, keyed by its tree path. For a tree sent in `files`, it is the request's bundles, whatever entry form carried them; for a `method_ref`, the fetched package's bundles, each keyed by its path from the package root. The tree's other files and the bundles of its dependencies are never included. Without `include_files` the field is absent, not empty.

**The artifacts are pinned to `/v1/validate`.** For a closure both routes accept, each artifact map equals the same-named field of `/v1/validate`'s valid arm (requested with `views: ["input_form", "output_form"]`) restricted to the same keys: both routes derive them with the one builder and dump them the same way, keeping null members such as a contract's `item_count: null`. Both routes read the same tree, but they do not accept exactly the same methods: this route loads a package the method calls by its address only from what was shipped with it (see [Resolve & Codegen](codegen.md#selecting-the-method)), where `/v1/validate` also looks among the methods installed on the runner and fetches one on a miss; `/v1/validate` refuses a method whose dry run fails, which this route accepts, and checks the tree's Python by syntax and a `method_ref` package's `requirements.txt`, which this route does not; this route refuses a root `METHODS.toml` it cannot read when the request names no pipe, since its selection chain then reads the manifest, where `/v1/validate` still answers a verdict.

`default_pipe_ref` is **not** `/v1/validate`'s field of the same name. That one is the run default: where several domains declare a `main_pipe`, it names the first declaring blueprint's, because a run would take it, while this route refuses to choose and states `null`.

## Response (invalid verdict)

An invalid closure is the `200` crate verdict `/v1/resolve` gives: `is_valid: false`, the structured `validation_errors[]` and a `message`. A call into a package nothing shipped is one, its `unresolved_package_dependency` item naming the package as `address-based dependency '<address>'`. It carries no artifacts, no `pipe_ref` or `default_pipe_ref`, no runnability facts and no `files`, whatever the request asked for.

## No verdict

Every non-2xx is RFC 7807 `application/problem+json` (see [Error Responses](error-responses.md)):

- **`422`** for a malformed body or neither or both method selectors, `ValidationError`; for a tree the runner cannot read, `InvalidMethodFiles`, `MissingBlobs`, `MethodTreeTooLarge` or `InvalidBundle`, as on [`/v1/resolve`](codegen.md#selecting-the-method); for an unreadable root manifest on a request naming no pipe, `MethodEntryError`; and for the selection refusals above, `EntryPipeNotFoundError` or `EntryPipeAmbiguousError`.
- **The `method_ref` fetch outcomes**, exactly as on `/v1/resolve`: `404` `MethodPackageNotFoundError` when no package in the fetched repository matches the address, `422` for a reference that does not parse or a fetch the server cannot accept, and `501` `MethodRefNotSupported` for a registry-form reference.
- **`403`** for the custom-Python policy of `/v1/validate` and the run routes, whose tree the route loads: `CustomCodeRequiresSandbox` for a tree holding a `.py` file on a deployment that is not sandbox-hosted, where loading the library would import each `.py` declaring a structure class and run its module-level code in the server's process, and `MethodStructuresRefusedError` for one whose Python declares a structure class.
- **`401` / `403`** for authentication, and **`413`** for a body over the size limit.
- **`500`** when an artifact cannot be derived: a pipe whose input or output JSON Schema cannot be rendered raises `PipeIOContractError`, which answers `500` as it does on `/v1/validate` — a fault of the tool, not a verdict about the method.
