# Codegen Projections

Codegen turns one **normalized library crate** — the flat, fully-qualified, self-contained, fingerprinted snapshot of a resolved library (see [`pipelex resolve`](../tools/cli/build/structures.md) and the [Library Crate Format](https://mthds.ai)) — into typed, documented artifacts for each consumer. The crate is the single authority: codegen never re-derives meaning from raw bundles and never calls a model.

This page describes the projection engine in `pipelex/codegen/`. The formal contract lives in `docs/specs/pipelex-codegen.md` (workspace root).

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

## The CLI surface

Two command families drive the engine (formal contract: `docs/specs/pipelex-codegen.md`, workspace root):

- **`pipelex resolve [PATH]… [-f json|toml] [-L DIR]…`** — assembles the closure (working bundles + the local `.mthds/methods/` cache), requires it to be **valid**, and emits the normalized crate to stdout. The verdict rides the exit code, mirroring the bare `validate` group: `0` resolved, `1` the library is invalid (a negative verdict — no crate), `2` no verdict (empty closure / not found).
- **`pipelex codegen <kind> …`** — the two-axis projection family (`kind` × `--target`):
    - `pipelex codegen types --target ts-zod|python-pydantic|python-structures [-o DIR] [PATH]… [-L DIR]…` — projects the crate's concept set for a target and writes each emitted file under the output directory.
    - `pipelex codegen inputs [--pipe <ref>] [-f json|toml] [--explicit] [-o FILE] [PATH]… [-L DIR]…` — projects a runnable inputs template for one pipe (Smart Inputs light shape by default, `--explicit` for the envelope), selected by qualified `--pipe` and defaulting to the closure's declared `main_pipe`.

Both codegen commands load and normalize the crate through the same shared helper the resolver uses (`pipelex/cli/commands/crate_loading.py`), so they share the resolve/validate exit-code contract. `pipelex build inputs` renders through the same `input_renderer` engine, so it and `codegen inputs` never diverge; `pipelex build structures` still uses its own always-qualified per-file generator (re-pointing it onto the bare-when-unique engine is a Phase-2 naming reconciliation, deferred so its output does not change silently).

## Surfacing imprecision, never guessing

A deterministic tool that guesses is a liability. Where a resolved type carries an imprecision marker, the emitter surfaces it rather than inventing a shape:

- Python emitters append an inline `# imprecise: <reason>` comment on the field.
- The ts-zod emitter emits `z.unknown()` plus a JSDoc `@imprecise <reason>` tag.

Two concept-level cases are surfaced the same honest way:

- A **structureless** concept (no structure, no refinement) projects as an opaque type (an empty model / `z.unknown()`) with the imprecision stated in its docstring.
- A **Python-class-backed** concept (`structure = "<ClassName>"`, whose shape lives only in hand-written Python, not in MTHDS) is surfaced as opaque — the bare class name is never silently emitted into a portable crate.

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
