# Codegen Projections

Codegen turns one **normalized library crate** — the flat, fully-qualified, self-contained, fingerprinted snapshot of a resolved library (see [`pipelex resolve`](../tools/cli/build/structures.md) and the [Library Crate Format](https://mthds.ai)) — into typed, documented artifacts for each consumer. The crate is the single authority: codegen never re-derives meaning from raw bundles and never calls a model.

This page describes the projection engine in `pipelex/codegen/` and the contract it implements: deterministic projections off the crate, stamped generated files, a sibling `codegen.lock`, and an offline drift check whose verdict rides the exit code.

## Two resolved layers, then emitters

The engine reads the crate through two neutral, language-agnostic layers, so every emitter consumes the same resolved shape rather than re-deriving the semantic mapping:

- **Resolved fields** (`pipelex/codegen/resolved_fields.py`) — one structure field becomes a `ResolvedType` tree (`text`/`number`/`concept`/`list`/`dict`/`literal`/…). Inline `choices` become a literal; a bare concept ref is promoted to its domain; natives are flagged. Where the source under-specifies a shape — a `list` with no `item_type`, a `concept` field with no ref — the resolved type is `ANY` carrying an explicit **imprecision marker** (never a guess).
- **Resolved concepts** (`pipelex/codegen/resolved_concepts.py`) — one crate concept becomes a `ResolvedConcept`: its type name inputs (domain, code, collision flag), its description, its refinement base, and either its resolved fields, or a structureless/opaque marker. Class naming is decided here once: a concept code that is unique across the crate stays bare (`Report`); a code that collides across domains is domain-qualified so a definition and every reference agree.

An emitter then walks the `ResolvedLibrary` and renders text. Emitters live in `pipelex/codegen/emitters/`, dispatched by `emit_types(crate, target=...)`.

## Targets

The `types` projection ranges over the crate's concept set (one type per qualified concept). Three targets ship today:

- **`python-structures`** — Pipelex runtime `StructuredContent` subclasses (the runtime idiom, the successor to `pipelex build structures`). Native references map to the runtime content classes (`TextContent`, …); native concepts themselves are not re-emitted.
- **`python-pydantic`** — plain `pydantic.BaseModel` types with no Pipelex imports. Every concept is emitted uniformly, including the materialized natives, so the module depends only on `pydantic` and the standard library.
- **`ts-zod`** — a pure TypeScript + Zod types file (`types.ts`, imports only `zod`) plus a `binder.ts` companion. `types.ts` holds Zod schemas and their inferred types; type names are the concept codes; **field keys are the crate's snake_case wire names verbatim**. Concept references use `z.lazy(() => XSchema)` so declaration order is irrelevant and cycles are handled.

### The ts-zod types file and its binder

`types.ts` stays dependency-free and portable (only `zod`). Its object keys are **wire-native** (snake_case), so a schema validates a wire payload *directly*. `binder.ts` is the thin companion exposing one typed `parse<Name>` / `serialize<Name>` pair per concept — each a direct `Schema.parse`, with no key-remapping layer. A pipe's IO types are concepts, so a pipe's output parser / input serializer is just the binder pair for those concept types — the binder is the concept-set-wide realization of the per-pipe parse/serialize helpers.

Wire-native keys (D10) are a deliberate correctness choice: a camelCase-keyed schema would need a binder that remaps keys, and a *generic* deep remap cannot tell a schema-declared field key from arbitrary data inside a `z.record()` / `z.unknown()` value (e.g. `native.JSON`'s `json_obj` map) — so it would silently rename the caller's actual data. Keeping keys wire-native removes that hazard entirely; if camelCase ergonomics are wanted later, they must ride a *schema-aware* transform, not a blind key remap.

For **`python-pydantic`**, no key mapping is ever needed either: wire names are already snake_case Python names, so parse/serialize are the native `Model.model_validate(data)` / `model.model_dump(mode="json")`.

### Refinement and native bases

A concept that refines another keeps its `refines` link when the base is **native-backed** (the refinement chain bottoms out at a native such as `Text` or `Number`), because the native is materialized into the crate and the base carries real runtime behavior; the emitter then renders inheritance (`class Summary(TextContent)` / `class Summary(Text)` / `z.lazy(() => TextSchema)`), which round-trips to the correct base class. A concept that refines an **in-crate structured** base has that base's effective structure flattened in during normalization.

Native materialization itself is faithful-or-absent per native: a content-class field maps when it has an unambiguous blueprint form — primitives, dicts, lists, references to other natives, and nested non-native models, which serialize as JSON objects and therefore map to a `dict` blueprint with unspecified value types (declared imprecision the emitters surface, e.g. `native.JSON`'s `json_obj` map). A field with no honest blueprint form at all (for example, a non-optional union) leaves the whole native structureless rather than guessing a partial shape.

## The CLI surface

Two command families drive the engine:

- **`pipelex resolve [PATH]… [-f json|toml] [-L DIR]…`** — assembles the closure (working bundles + the local `.mthds/methods/` cache), requires it to be **valid**, and emits the normalized crate to stdout. The verdict rides the exit code, mirroring the bare `validate` group: `0` resolved, `1` the library is invalid (a negative verdict — no crate), `2` no verdict (empty closure / not found).
- **`pipelex codegen <kind> …`** — the two-axis projection family (`kind` × `--target`):
    - `pipelex codegen types --target ts-zod|python-pydantic|python-structures [-o DIR] [PATH]… [-L DIR]…` — projects the crate's concept set for a target and writes each emitted file under the output directory.
    - `pipelex codegen inputs [--pipe <ref>] [-f json|toml] [--explicit] [-o FILE] [PATH]… [-L DIR]…` — projects a runnable inputs template for one pipe (Smart Inputs light shape by default, `--explicit` for the envelope), selected by qualified `--pipe` and defaulting to the closure's declared `main_pipe`.

Both codegen commands load and normalize the crate through the same shared helper the resolver uses (`pipelex/cli/commands/crate_loading.py`), so they share the resolve/validate exit-code contract.

The **agent CLI mirrors** the family for machine consumers: `pipelex-agent codegen types --target <flavor>` runs the same engine and emission layer but presents through the agent CLI's two-stream envelopes (`--format markdown|json` on stdout for success, `--error-format` on stderr for errors — markdown default), and `pipelex-agent codegen check` is the same offline drift check with the verdict as a structured envelope: up-to-date is a success envelope, drift is a `CodegenDriftError` error envelope enumerating `drifts[]` by category (exit `1`), and a missing/unreadable lock is a no-verdict error (exit `2`). There is no `pipelex-agent codegen inputs` — the existing `pipelex-agent inputs` group already surfaces that projection. The legacy `build` family rides the same engine: `pipelex build inputs` renders through the same `input_renderer` engine as `codegen inputs` (they cannot diverge), and `pipelex build structures` is a thin alias of `codegen types --target python-structures` (the old always-qualified per-file generator is gone — the alias emits the single stamped `structures.py` + `codegen.lock`, bare-when-unique names). `pipelex build runner` emits its `structures/` scaffold through the same projection and spells the script's imports and example inputs with the emitted class names (`from structures.structures import …`), so the script and the module always agree.

## The trust chain: stamps, lock, and the offline check

Drift — generated code that no longer matches the method it was generated from — is the tax every codegen system eventually charges. The engine refuses to pay it. Every file `pipelex codegen types` writes carries a machine-parseable **stamp** header, the artifact set is recorded in a sibling **`codegen.lock`**, and `pipelex codegen check` verifies both — entirely offline.

### Stamps

`pipelex/codegen/stamp.py` prepends a fenced comment block (in the target's comment syntax — `#` for Python, `//` for TypeScript) to each generated file:

```python
# >>> pipelex-codegen-stamp >>>
# crate_fingerprint: 1336e999…293f46
# engine_version: 0.38.0
# projection: types / python-pydantic
# options: {}
# content_hash: 1d074a49…6f42e4
# <<< pipelex-codegen-stamp <<<
```

The `crate_fingerprint` is the crate's semantic hash, so reformatting or commenting a `.mthds` file never changes a stamp — only a change to the method's effective type surface does. The `content_hash` is a SHA-256 over the body **below** the stamp, so a lone file can testify that it has not been hand-edited, without the engine, the network, or the lock.

### Lock

`pipelex/codegen/lock.py` writes `codegen.lock` (human-diffable TOML) recording each generated artifact's path and body hash, plus the crate fingerprint and engine version the set was built against. The lock catches the one drift class per-file stamps cannot: a deleted concept whose stale generated file lingers on disk. It is a Pipelex-owned artifact, distinct from the standard's `methods.lock` (which pins remote dependency versions).

### Offline check

`pipelex codegen check [DIR]` (`pipelex/codegen/check.py`) is pure hashing — **no engine, no network, no API key** — so any client (this CLI, an SDK, a short CI script) implements it identically. It reports drift by category:

- **missing** — an artifact in the lock is absent on disk;
- **modified** — a file's body no longer matches its locked hash;
- **hand-edited** — a file's stamp is stripped or its recorded content hash no longer matches the body;
- **orphan** — a stamped generated file on disk that the lock does not track.

The verdict rides the exit code (mirroring `resolve` / `validate`): `0` current, `1` drift present, `2` no lock found. Regeneration against the engine is a **dev action**; the offline check is the **CI action** — so template improvements never redden a consumer's CI.

### Idempotent emission

`pipelex/codegen/emission.py` ties it together in two layers. `build_stamped_projection` is the **pure** core: it stamps each emitted body and assembles the matching `codegen.lock` content — no filesystem access — so it is the single source of truth for what a projection *is* on disk. `write_stamped_projection` rides it to materialize locally: it writes each file only when its content changed (write-if-changed — no mtime churn, clean diffs, watch-mode friendly), removes any previously-tracked stamped file that dropped out of the set, and rewrites the lock. Only files the tool itself stamped are ever removed, so a hand-authored file sharing the output directory is never touched. `codegen inputs` applies the same write-if-changed rule to its single (unstamped) template file, so a full regeneration pass over a committed consumer is a true no-op when everything is current.

## Serving the engine over HTTP

The same engine backs the `pipelex-api` routes (`POST /v1/resolve`, `POST /v1/codegen`, and the re-pointed `/v1/build/*` — the route envelopes are documented in `pipelex-api`'s `docs/codegen.md`). Two host-facing cores make that possible without any CLI plumbing:

- **`pipelex.pipeline.resolve_bundle.resolve_crate_from_contents`** resolves **in-memory** MTHDS contents (strings, with optional per-content sources) into the normalized crate. It mirrors `validate_bundle`'s in-memory arm — the same `translate_to_validate_bundle_error` cascade, so an invalid library raises the one shared `ValidateBundleError` and a resolve verdict cannot drift from a validate verdict — and the same **loaded-on-success contract**: the library is left loaded and current for the host to read live pipes from, and the host owns its teardown. Resolution is static (no dry-run sweep), matching `pipelex resolve`.
- **`build_stamped_projection`** (above) gives the host the stamped artifact set plus the lock as pure content. A client that writes the served files and lock verbatim reproduces a local run byte-for-byte — the offline `codegen check` passes on the written tree exactly as it would locally. There is deliberately no server-side check route: the check is offline by design.

## Surfacing imprecision, never guessing

A deterministic tool that guesses is a liability. Where a resolved type carries an imprecision marker, the emitter surfaces it rather than inventing a shape:

- Python emitters append an inline `# imprecise: <reason>` comment on the field.
- The ts-zod emitter emits `z.unknown()` plus a JSDoc `@imprecise <reason>` tag.

Two concept-level cases are surfaced the same honest way:

- A **structureless** concept (no structure, no refinement) projects as an opaque type (an empty model / `z.unknown()`) with the imprecision stated in its docstring.
- A **Python-class-backed** concept (`structure = "<ClassName>"`, whose shape lives only in hand-written Python, not in MTHDS) is surfaced as opaque — the bare class name is never silently emitted into a portable crate.

Opaque is always **pass-through, never lossy**: the ts-zod `z.unknown()` hands the wire object through verbatim, and the Python emitters set `model_config = ConfigDict(extra="allow")` on opaque classes so `model_validate` keeps every field (pydantic's default `extra="ignore"` would silently strip the content). The owner of a Python-class-backed concept recovers the typed object by validating with their own class (`MyLegacyClass.model_validate(payload)`); every other consumer gets the honest untyped object.

## The extension-file story

Generated code is never edited — hand edits are overwritten on regeneration, and the trust chain treats them as drift. Customization lives in **sibling extension files** that survive regeneration, and each generated file's header says so:

- **Python** — subclass the generated type from a sibling module:

    ```python
    # my_types_ext.py
    from .structures import Report

    class MyReport(Report):
        ...
    ```

- **TypeScript** — augment the generated type from a sibling module via declaration merging.

Every generated file carries an `AUTOGENERATED — DO NOT EDIT` header naming its projection and pointing at this mechanism.
