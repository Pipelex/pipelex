# Codegen Projections

Codegen turns one **normalized library crate** — the flat, fully-qualified, self-contained, fingerprinted snapshot of a resolved library (see [`pipelex resolve`](../tools/cli/build/structures.md) and the [Library Crate Format](https://mthds.ai)) — into typed, documented artifacts for each consumer. The crate is the single authority: codegen never re-derives meaning from raw bundles and never calls a model.

This page describes the projection engine in `pipelex/codegen/` and the contract it implements: deterministic projections off the crate, stamped generated files, a sibling `codegen.lock`, and an offline drift check whose verdict rides the exit code.

## Two resolved layers, then emitters

The engine reads the crate through two neutral, language-agnostic layers, so every emitter consumes the same resolved shape rather than re-deriving the semantic mapping:

- **Resolved fields** (`pipelex/core/concepts/resolved_fields.py`) — one structure field becomes a `ResolvedType` tree (`text`/`number`/`concept`/`list`/`dict`/`literal`/…). Inline `choices` become a literal; a bare concept ref is promoted to its domain; natives are flagged. Where the source under-specifies a shape — a `list` with no `item_type`, a `concept` field with no ref — the resolved type is `ANY` carrying an explicit **imprecision marker** (never a guess).
- **Resolved concepts** (`pipelex/codegen/resolved_concepts.py`) — one crate concept becomes a `ResolvedConcept`: its type name inputs (domain, code, collision flag), its description, its refinement base, and either its resolved fields, or a structureless/opaque marker. Class naming is decided here once: a concept code that is unique across the crate stays bare (`Report`); a code that collides across domains is domain-qualified so a definition and every reference agree.

An emitter then walks the `ResolvedLibrary` and renders text. Emitters live in `pipelex/codegen/emitters/`, dispatched by `emit_types(crate, target=...)`.

## Targets

The `types` projection ranges over the crate's concept set (one type per qualified concept). Three targets ship today:

- **`python-structures`** — Pipelex runtime `StuffContent` subclasses (the runtime idiom, the successor to `pipelex build structures`). Native references map to the runtime content classes (`TextContent`, …); native concepts themselves are not re-emitted. Each concept lands on the same content class the runtime would resolve it to: a structured concept on `StructuredContent`, a concept refining a native on that native's content class, a structureless one on `TextContent`.
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

The header itself is read strictly, because the content hash covers only what is *below* it. Every line between the fences must carry the file's comment prefix, so a line injected into the block — an uncommented statement sitting inside a header that says `DO NOT EDIT`, or a blank line — makes the stamp unparseable, which the offline check reports as **hand-edited**. What counts as a line there is deliberately wider than `\n`: the reader breaks wherever Python's `str.splitlines()` breaks, U+2028 and U+2029 included, because those two terminate a `//` comment in JavaScript. A TypeScript artifact whose header carried one raw would be a single commented line to a narrower reader and two lines to the engine running it — executable text inside the header, on a file the check would still call current, since the hash covers only the body. The second implementation of the check splits on the same set, so both readers reach the same verdict. The `options` value must be conformant JSON: Python's non-standard `NaN` / `Infinity` / `-Infinity` literals are refused, since the stamp header is a cross-language interchange format and a stamp only one language can read is not a valid stamp. None of this is a signature — there is no MAC anywhere, and the real defence against a malicious edit is diff review; the rule exists so a file that claims to be pristine cannot quietly carry code that was edited in.

In the other direction the header is deliberately tolerant: a *commented* `key: value` line the reader does not recognise is ignored rather than rejected, so the stamp can gain a field without breaking readers built against an earlier shape.

### Lock

`pipelex/codegen/lock.py` writes `codegen.lock` (human-diffable TOML) recording each generated artifact's path and body hash, plus the crate fingerprint and engine version the set was built against. The lock catches the one drift class per-file stamps cannot: a deleted concept whose stale generated file lingers on disk. It is a Pipelex-owned artifact, distinct from the standard's `methods.lock` (which pins remote dependency versions).

Every lock opens with `lock_version`, and the format has a written evolution policy — because the lock is read by implementations we do not ship, and it validates strictly: an unknown key is a hard no-verdict error, not a drift. That strictness is right *within* a version and unworkable across versions, so any change to the lock's key set or to the meaning of an existing key bumps the version, and a reader refuses a version it does not know with a message naming which side to upgrade. The version is read **before** the key set is validated, so a lock from a newer codegen is diagnosed by its version rather than by whichever new key it happens to carry first — otherwise the strict-key rejection would fire on a key the writer was entitled to add and report something the reader cannot act on. A lock with no `lock_version` key is version 1 by definition (the field was introduced *as* version 1), so nothing already on disk needs migrating; the next regeneration simply rewrites the lock with the key present. Regeneration over a lock it cannot read replaces it rather than failing, exactly as it does over a corrupt one: the run has already rewritten every artifact with this engine, so adopting this engine's lock version is the coherent outcome, and anything the newer engine had emitted surfaces as an orphan on the next check instead of being silently pruned. The **stamp** header needs no equivalent, since it is additive in the other direction — an unrecognised commented field is ignored rather than rejected.

### Offline check

`pipelex codegen check [DIR]` (`pipelex/codegen/check.py`) is pure hashing — **no engine, no network, no API key** — so any client (this CLI, an SDK, a short CI script) implements it identically. It reports drift by category:

- **missing** — an artifact in the lock is absent on disk;
- **modified** — a file's body no longer matches its locked hash;
- **hand-edited** — a file's stamp is stripped or its recorded content hash no longer matches the body;
- **orphan** — a stamped generated file on disk that the lock does not track.

The order of that report is part of the contract, not an implementation detail, so a second implementation can be compared to this one line by line: every locked-artifact drift comes first, ordered by the full relative path compared as a plain string, and then every orphan, ordered by that same rule. One locked path yields at most one drift, and **hand-edited** outranks **modified** when a file is both self-inconsistent and off its locked hash.

The verdict rides the exit code (mirroring `resolve` / `validate`): `0` current, `1` drift present, `2` no lock found. Regeneration against the engine is a **dev action**; the offline check is the **CI action** — so template improvements never redden a consumer's CI.

### Idempotent emission

`pipelex/codegen/emission.py` ties it together in two layers. `build_stamped_projection` is the **pure** core: it stamps each emitted body and assembles the matching `codegen.lock` content — no filesystem access — so it is the single source of truth for what a projection *is* on disk. `write_stamped_projection` rides it to materialize locally: it writes each file only when its content changed (write-if-changed — no mtime churn, clean diffs, watch-mode friendly), removes any previously-tracked stamped file that dropped out of the set, and rewrites the lock. Only files the tool itself stamped are ever removed, so a hand-authored file sharing the output directory is never touched. `codegen inputs` applies the same write-if-changed rule to its single (unstamped) template file, so a full regeneration pass over a committed consumer is a true no-op when everything is current. Every artifact is written with LF line endings whatever the platform, because Python would otherwise translate each newline to the host's convention: the same projection emitted on Windows and on Linux would land as different bytes while both recorded the same content hash, and a team mixing the two would watch the generated tree churn in version control with no change of content. Byte-identical regeneration is a promise across machines, not only within one. Ownership governs overwriting as well as removal, but the two tests are not the same one, and the overwrite test is the stricter: pruning asks only whether a file still carries our stamp markers, while overwriting demands a header that actually parses. The overwrite test runs before the first byte is written, so a refused run leaves the tree exactly as it found it: the writer declines any destination already holding a file it cannot prove it owns — one neither tracked by the lock nor parseable as stamped. That is where the strict header gate has a visible edge. A stamped file **the lock does not track** still scans as stamped, so the check calls it an **orphan** and advises "remove or regenerate" — but a tampered header no longer *parses*, so regeneration cannot prove it owns the file and declines to reclaim it; removing it is the half of that advice that always applies. A **lock-tracked** file whose header was tampered with is the other case entirely: the lock is the ownership proof, so the check reports it as **hand-edited** and regeneration overwrites it. The writer is deliberately unwilling to clobber a file that may hold real work.

### Lint-clean by construction

A stamp's `content_hash` is a raw SHA-256 over the body bytes. So if the emitted code is not already what your formatter wants, the first `ruff check --fix` / `ruff format` (or `prettier --write`) over your tree rewrites those bytes and `pipelex codegen check` reports the file as **hand-edited** — accusing you of the one thing you did not do.

The emitters therefore emit exactly what the formatter would write. Generated Python uses builtin generics (`list[str]`, `dict[str, int]`), `X | None` over `Optional[X]`, double-quoted `Literal` members, and isort-grouped imports — merged, sorted, and, past the width threshold below, already wrapped into the parenthesized magic-trailing-comma form ruff itself would produce; generated TypeScript matches Prettier's blank-line and import-wrapping behavior. Running your formatter over a generated tree is a no-op, and the stamp stays valid.

**You should not need to exclude generated paths from your linter.** If you carry such an exclusion from an older version, drop it.

Every import is registered by whoever writes the name it imports, never seeded up front. That matters for crate shapes which use fewer of them than you would expect: a method declaring only structureless concepts emits no `Field(...)` at all, and one whose concepts all refine a native never reaches the runtime root base. An import left unused is an `F401` — a fix ruff applies automatically, so the line would simply vanish and take the stamp with it.

A projection with nothing to emit for a target is its **header alone** — no imports, no trailing blank lines. That case is ordinary rather than degenerate: `python-structures` skips native concepts, since they already exist in the runtime, so a method that declares no concepts of its own leaves that target with no class to write. The header is inert under any formatter, whereas an import block with nothing left to use it is an unused-import finding sitting above a collapsible blank-line run — both of which a formatter would rewrite, breaking the stamp.

#### Line width, which is your setting and not ours

A description or choice list is authored text with no length bound, so a generated line can exceed whatever `line-length` you lint at — and your formatter would then wrap the call, rewriting the bytes.

Because we cannot know your width, anything too long is emitted **already wrapped, with a trailing comma**. That comma is load-bearing: Black and ruff both read it as a deliberate choice to keep the construct exploded, and will not rejoin it at any width. Short lines stay on one line, so ordinary artifacts read exactly as before.

The threshold is 88 columns — ruff's own default, chosen because it is the *tightest* width you are likely to use, and only the tightest threshold is safe. If you lint Python at **fewer than 88 columns**, short generated lines can still be rewrapped; either raise `line-length` for the generated path or keep an exclusion there.

`E501` is the one finding that can survive on a generated file, on a line holding a single long string literal — an authored description or choice value. There is no wrapped form: breaking a string would alter the author's text. It has no automatic fix, so it never changes bytes and never breaks a stamp, and it is not in ruff's default rule set, so most consumers never see it.

#### Docstrings

A concept description becomes the generated class's docstring, rendered the way a human writes one: summary on the first line, continuation lines indented to the class body, closing delimiter on its own line. That shape is not cosmetic — it is the only one that `ruff format` and the pydocstyle rules both leave alone. Rendered flat, a multi-line description trips `D207`/`D209` and edge whitespace trips `D210`, all of which ruff fixes automatically, rewriting the bytes.

So `__doc__` carries the class-body indentation, exactly as a hand-written docstring does. What holds exactly is the value you actually read:

```python
inspect.getdoc(GeneratedClass) == inspect.cleandoc(authored_description)
```

Exact bytes survive wherever they are consumed programmatically rather than read as prose — `Field(description=...)` keeps the description verbatim, and so does the crate.

#### TypeScript assumes Prettier's defaults

The `ts-zod` target is emitted to match Prettier's **default** configuration: 80-column print width, double quotes, semicolons. A long concept name or choice list is pre-wrapped the way Prettier would wrap it, for the same reason the Python side pre-explodes long calls.

If your Prettier config changes `printWidth`, `singleQuote`, or `semi`, the generated files will not match it, and `prettier --write` will rewrite them. Either run codegen output through your own Prettier before stamping, or keep an exclusion for the generated path.

One ruff setting is required, because it cannot be fixed in the emitted bytes:

```toml
[tool.ruff.lint.flake8-type-checking]
runtime-evaluated-base-classes = [
  "pydantic.BaseModel",
  "pipelex.core.stuffs.structured_content.StructuredContent",
]
```

Without it, `TC003` asks you to move `from datetime import date` into an `if TYPE_CHECKING:` block. Applying that **breaks** the generated models — pydantic resolves annotations at runtime to build validators, so the import must stay at runtime. The setting tells ruff these classes are runtime-evaluated, and the finding goes away.

The remaining findings are artifacts of *how* you lint, not of file content. None of them has an automatically-applied fix, so none can change bytes:

- `INP001` ("implicit namespace package") fires when you point ruff at a bare directory with no `__init__.py`. Add one, or lint the package that contains it.
- `E501` on a single long string literal, as described above.
- `D301` ("use `r\"\"\"`") on the rare description that carries both `\"\"\"` and `'''`, or a control character — the only inputs with no verbatim rendering, which therefore have to be escaped. Ruff classes that fix as *unsafe*, so `ruff check --fix` leaves it alone.
- Import grouping for the `python-structures` target assumes `pipelex` is a third-party dependency — which it is in your tree. The Pipelex repo itself, where `pipelex` is first-party, is the one place ruff wants the opposite order; no generated artifact is committed there, so the consumer's grouping is the one the emitter targets.

## Serving the engine over HTTP

The same engine backs the `pipelex-api` routes (`POST /v1/resolve`, `POST /v1/codegen`, and the re-pointed `/v1/build/*` — the route envelopes are documented in `pipelex-api`'s `docs/codegen.md`). Two host-facing cores make that possible without any CLI plumbing:

- **`pipelex.pipeline.resolve_bundle.resolve_crate_from_contents`** resolves **in-memory** MTHDS contents (strings, with optional per-content sources) into the normalized crate. It mirrors `validate_bundle`'s in-memory arm — the same `translate_to_validate_bundle_error` cascade, so an invalid library raises the one shared `ValidateBundleError` and a resolve verdict cannot drift from a validate verdict — and the same **loaded-on-success contract**: the library is left loaded and current for the host to read live pipes from, and the host owns its teardown. Resolution is static (no dry-run sweep), matching `pipelex resolve`.
- **`build_stamped_projection`** (above) gives the host the stamped artifact set plus the lock as pure content. A client that writes the served files and lock verbatim reproduces a local run byte-for-byte — the offline `codegen check` passes on the written tree exactly as it would locally. There is deliberately no server-side check route: the check is offline by design.

## Surfacing imprecision, never guessing

A deterministic tool that guesses is a liability. Where a resolved type carries an imprecision marker, the emitter surfaces it rather than inventing a shape:

- Python emitters append an inline `# imprecise: <reason>` comment on the field.
- The ts-zod emitter emits `z.unknown()` plus a JSDoc `@imprecise <reason>` tag.

Two concept-level cases are surfaced the same honest way:

- A **structureless** concept (no structure, no refinement) projects as an opaque type — an empty model for `python-pydantic`, `z.unknown()` for ts-zod — with the imprecision stated in its docstring. Its *base class* is not a guess, though: `python-structures` emits it on `TextContent`, because that is what the runtime resolves the same declaration to — "describe it in prose and get text back" is what a structureless concept means to an author, and the interpreter's text-vs-object dispatch reads the base class to decide which call to make. A projection that emitted the root base instead would answer that question differently from the runtime for the same authored concept, silently. That inherited `text` field is what makes this target's structureless class the one exception to the pass-through rule below.
- A **Python-class-backed** concept (`structure = "<ClassName>"`, whose shape lives only in hand-written Python, not in MTHDS) is surfaced as opaque — the bare class name is never silently emitted into a portable crate. This is the one opaque shape that keeps the root base: its content class genuinely is not visible to the crate, so promoting it to `TextContent` would be the guess the rule above forbids.

Opaque is **pass-through, never lossy**: the ts-zod `z.unknown()` hands the wire object through verbatim, and the Python emitters set `model_config = ConfigDict(extra="allow")` on opaque classes so `model_validate` keeps every field (pydantic's default `extra="ignore"` would silently strip the content). The owner of a Python-class-backed concept recovers the typed object by validating with their own class (`MyLegacyClass.model_validate(payload)`); every other consumer gets the honest untyped object.

The one exception is the shape described above: a **structureless** concept on `python-structures` inherits `TextContent.text`, which is required, so an object-shaped payload raises instead of landing in `extra`. That is not a regression against the runtime — the class `ConceptFactory` builds for the same declaration is a `TextContent` subclass too, so it rejects the same payload. Matching the runtime is the point; a projection that accepted a payload the runtime refuses would be the more expensive lie. Consumers who want the old permissive behaviour are describing a concept that is not structureless, and should give it a structure.

## The extension-file story

Generated code is never edited — hand edits are overwritten on regeneration, and the trust chain treats them as drift. Customization lives in **sibling extension files** that survive regeneration, and each generated file's header says so:

- **Python** — subclass the generated type from a sibling module:

    ```python
    # my_types_ext.py
    from .structures import Report


    class MyReport(Report): ...
    ```

- **TypeScript** — augment the generated type from a sibling module via declaration merging.

Every generated file carries an `AUTOGENERATED — DO NOT EDIT` header naming its projection and pointing at this mechanism.
