# Pipe I/O

Return a method's I/O artifacts — its pipe I/O contracts, its input form and its output form — without validating it.

**Endpoint:** `POST /v1/pipe-io`

The route resolves the closure through the same static core as [`POST /v1/resolve`](codegen.md#resolve), selects a pipe with the [selection chain](#pipe-selection) below, and derives the three artifacts with the builder that [`POST /v1/validate`](pipe-validate.md) and every run already call. It runs **no dry-run sweep**, so a call costs one load and one derivation, where `/v1/validate` mock-runs every pipe of the method. A caller that shows a method, prepares its inputs or generates types for it reads this route; a caller that needs the dry-run verdict or the dry-run graph stays on `/v1/validate`, whose `views` still attach both forms beside the verdict.

It is a **Pipelex API extension**, not an MTHDS Protocol route: it is not tagged `x-mthds-protocol` in the [OpenAPI artifact](openapi/pipelex-api.openapi.yaml). The artifacts it carries are the standard's, under their neutral names — see the MTHDS specification's pages on [pipe I/O contracts, the input-form descriptor and the output-form descriptor](https://mthds.ai).

It speaks the `/v1/validate` verdict discipline: a **produced verdict is always a `200`** discriminated on `is_valid`, and a non-2xx is reserved for a request that produced no verdict.

## Request

The body is the [crate routes' closure selector](codegen.md#selecting-the-closure) plus a pipe selector and two opt-ins:

- `files` (list) **or** `method_ref` (string), exactly one: the closure, as on `/v1/resolve`. Neither or both is a request-shape `422`.
- `pipe_ref` (string, optional): the qualified ref `domain.pipe_code` of the pipe to describe. Omitted, the selection chain below decides.
- `all_pipes` (boolean, default `false`): describe every pipe the closure loads instead of the selected one.
- `include_files` (boolean, default `false`): echo the resolved closure's `.mthds` files on the valid arm.
- `resources` (object, optional): the files the closure's steps read, such as a `PipeDocGen` step's `template_file`, keyed by the path the step names, each in standard base64, as on [`/v1/validate`](pipe-validate.md#sending-the-files-the-steps-read-resources). It accompanies `files` only. A string-loaded step whose template file was not sent makes the closure invalid.

There is no `views` field, because the valid arm always carries all three artifacts. The hosted API also accepts a catalog `method_id`, which the platform resolves into `files[]` before forwarding, so this server never declares it.

```json
{
  "files": [{ "content": "...bundle...", "source": "main.mthds" }],
  "all_pipes": true,
  "include_files": true
}
```

## Pipe selection

The selection chain takes the request's `pipe_ref`; else a fetched package's manifest `main_pipe`; else the closure's own `main_pipe` declaration, when exactly one domain declares one. The chain stops at the first link that is present, so a manifest `main_pipe` the closure does not declare, or declares in several domains, is a failed selection rather than a fall-through to the closure's declarations.

The closure is resolved first, so an invalid closure answers its invalid verdict whatever `pipe_ref` names. For a valid closure these selections are refused with a `422` problem whose `code` names the failure, never the `ValidationError` of a malformed request, so a client tells a selection refusal from a request-shape one by that member:

- `request.pipe_not_found` for a `pipe_ref` that names no pipe of the closure, with the selection as its `pipe` parameter;
- `request.pipe_ambiguous` for a bare code that matches pipes in several domains, with the selection as its `pipe` parameter and the qualified refs to choose from as its `candidates`;
- `request.pipe_unspecified`, without `all_pipes`, for a request with no `pipe_ref` whose closure declares no `main_pipe`, or several, whose qualified refs are then its `candidates`;
- `method.pipe_unresolved` for a manifest `main_pipe` the closure does not declare, the method's own declaration to fix, with the declared selection as its `missing` parameter;
- `method.ref_ambiguous` for a manifest `main_pipe` that matches pipes in several domains of the closure, the method's own declaration to fix, with the declared selection as its `ref` parameter and the qualified refs it matches as its `candidates`.

The problem's `type`, `title`, sentences and step are the code's: a request's selection asks the caller to select a pipe the method declares, and a manifest's asks the method's author to correct the declaration.

An unknown or ambiguous `pipe_ref` answers the code the run routes answer for the same `pipe_code`. A closure declaring no `main_pipe`, or several, has no run-route twin: this route refuses both as the pipe-selector design classifies them, while a run over such a closure today fails with a `500` or runs the first declaration.

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
  "files": [{ "content": "...bundle...", "source": "main.mthds" }]
}
```

- `is_valid` (`true`): the closure parsed, loaded and passed static validation. It does **not** mean a dry run passed; this route runs none.
- `pipe_ref` (string | null): the qualified ref the selection resolved, read off the resolved pipe and never echoed from the request. `null` only under `all_pipes` when nothing resolves.
- `pipe_io_contracts`, `input_form`, `output_form` (objects keyed by qualified `pipe_ref`): the three artifacts, sharing one key set — the resolved `pipe_ref` alone by default, every pipe the closure loads under `all_pipes`.
- `default_pipe_ref` (string | null): the method's own entry pipe, the selection chain without the request's `pipe_ref`. A request that omits `pipe_ref` therefore always answers `pipe_ref == default_pipe_ref`. When the request named a pipe, or asked for `all_pipes`, and the chain finds no entry pipe or several, the field is a stated `null`.
- `pending_signatures` (list of strings) and `is_runnable` (boolean): exactly what they mean on `/v1/validate` — the qualified refs of the pipes still declared as signatures, and `not pending_signatures`. Both come from the loaded library with no dry run, so a method whose dry run would fail is still reported runnable here.
- `files` (list, only with `include_files: true`): the closure in the request's own `files[]` shape. For inline `files` it is the request's files echoed back; for a `method_ref` it is the fetched package's `.mthds` files, each `source` being the file's path relative to the package root. A package's other files are never included. Without `include_files` the field is absent, not empty.

**The artifacts are pinned to `/v1/validate`.** For a closure both routes accept, each artifact map equals the same-named field of `/v1/validate`'s valid arm (requested with `views: ["input_form", "output_form"]`) restricted to the same keys: both routes derive them with the one builder and dump them the same way, keeping null members such as a contract's `item_count: null`. The two routes do not accept exactly the same closures: `/v1/validate` refuses a closure whose dry run fails, which this route accepts; this route refuses an address-based cross-package dependency, which `/v1/validate` loads; and `/v1/validate` by `method_ref` also loads a package's non-`.mthds` files, which this route never reads.

`default_pipe_ref` is **not** `/v1/validate`'s field of the same name. That one is the run default: where several domains declare a `main_pipe`, it names the first declaring blueprint's, because a run would take it, while this route refuses to choose and states `null`.

## Response (invalid verdict)

An invalid closure is the `200` crate verdict `/v1/resolve` gives: `is_valid: false`, the structured `errors[]` and a `message`. It carries no artifacts, no `pipe_ref` or `default_pipe_ref`, no runnability facts and no `files`, whatever the request asked for.

## No verdict

Every non-2xx is RFC 9457 `application/problem+json` (see [Error Responses](error-responses.md)):

- **`422`** for a malformed body, neither or both closure selectors and an over-limit file, all `request.invalid` naming the field, and for the selection refusals above, by their codes.
- **`422` `request.unsupported`** with `params.reason` set to `address_based_dependency` for a closure calling another method by its address, which this route cannot load: the request is what it cannot serve, not the method, so it is no verdict, and the run routes, which fetch such a dependency, run the closure.
- **The `method_ref` fetch outcomes**, exactly as on `/v1/resolve`: `404` `method.not_found` when no package in the fetched repository matches the address, `422` for a reference that does not parse (`request.invalid`) or a package the server cannot accept (`method.ambiguous`, `method.package_invalid`), `502` `method.fetch_failed` when the fetch itself failed, and `422` `request.unsupported` for a registry-form reference. The route reads only a package's `.mthds` files, so the custom-code `501` and the structures `422` of `/v1/validate` and the run routes never arise here.
- **`401`** for authentication, and **`413`** `request.too_large` for a body over the size limit.
- **`500`** when an artifact cannot be derived: a pipe whose input or output JSON Schema cannot be rendered raises `PipeIOContractError`, which answers `500` as it does on `/v1/validate` — a fault of the tool, not a verdict about the method.
