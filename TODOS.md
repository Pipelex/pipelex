# PR recap — DevEx codegen: the normalized library crate and its projections

This file is a reviewer's guide to this PR (`feature/Devex-codegen` → `dev`). It summarizes what the branch delivers, the design decisions behind shapes a reviewer might otherwise flag, and the verification already performed. The full execution history (checkpoints, review fan-outs, triage records) lives in this file's git history on the branch; the deferred continuation of the track is documented at the workspace root under `wip/codegen/`.

## What this PR delivers

**One authority, many projections.** A resolved, validated MTHDS library is snapshotted into a **normalized library crate** — flat, fully qualified, natives materialized, refinement flattened, fingerprinted — and every developer-facing artifact is a deterministic projection off that crate: typed models (Python/TS), runnable input templates, runner scaffolds, and (served from `pipelex-api`, in a companion branch) HTTP responses. Generated files carry a self-describing stamp, are tracked in a sibling `codegen.lock`, and are verifiable **offline** by pure hashing.

The crate format is spec'd in the MTHDS standard (`mthds` repo: `docs/spec/library-crate.md`); the pipelex surfaces are spec'd at the workspace root (`docs/specs/pipelex-codegen.md`) with conformance skeletons/tests in the `conformance` repo. Contract-first: the specs and skeletons were written and reviewed before the engine code.

## Component map (where to look in the diff)

- **`pipelex/codegen/`** — the engine. `resolved_fields.py` / `resolved_concepts.py` (neutral resolved layers every emitter consumes; imprecision is explicit, never guessed), `emitters/` (`python_structures`, `python_pydantic`, `ts_zod` + `naming`, `target`, `types_emitter` dispatch), `crate_encoding.py` (canonical JSON/TOML), `stamp.py` / `lock.py` / `check.py` / `emission.py` (the trust chain: stamped headers, `codegen.lock`, offline drift check, idempotent write-if-changed emission with stale-file pruning), `native_expansion.py` (retained as a consistency probe only — see pinned natives below).
- **`pipelex/libraries/crate_normalization.py`** + `LibraryCrate.compute_normalized_fingerprint` — the normalization pass (post-validation, D6) and the widened fingerprint (concepts + pipes + domain metadata, provenance excluded; canonical JSON ≈ RFC 8785). The loader skips `native.*` crate entries so a normalized crate round-trips through `load_from_crate`.
- **`pipelex/core/concepts/native/pinned_blueprints.py`** — natives materialize by lookup into the standard's pinned per-version definitions, never by runtime reflection (cross-implementation fingerprint byte-agreement). A parametrized test proves each pinned blueprint still matches its runtime content class.
- **New native surface** — `native.Time` (`TimeContent`), the `time` structure-field type through the whole chain (blueprint enum → resolved fields → all three emitters → `StructureGenerator`), `ImageContent` flattened to paired `width`/`height` (breaking wire), `native.Date` pinned with real structure (wire unchanged).
- **CLI** — `pipelex resolve` (crate to stdout, JSON/TOML), the `pipelex codegen types|inputs|check` family, shared `crate_loading.py` (one resolve/validate exit-code contract: 0 resolved · 1 invalid library · 2 no-verdict), and the D9 re-point: `build structures` is a thin alias of `codegen types --target python-structures`, `build runner` scaffolds through the same projection with the emitted class spellings. The legacy per-file structures generator and the concepts-only loading family are deleted.
- **Agent CLI** — `pipelex-agent codegen types|check` mirrors the family through the two-stream envelopes (markdown/JSON); drift is a structured `CodegenDriftError` with `drifts[]` (exit 1), a missing/unreadable lock is no-verdict (exit 2). Deliberately no `codegen inputs` mirror (`pipelex-agent inputs` already surfaces that projection).
- **`pipelex/pipeline/resolve_bundle.py`** + `emission.build_stamped_projection` — host-facing engine cores for the HTTP routes (`pipelex-api` companion branch): in-memory resolve with `validate_bundle`'s verdict vocabulary and loaded-on-success lifecycle; a pure stamping core so HTTP-served artifacts are byte-identical to locally written ones (pinned by a direct parity test).
- **`StructureGenerator`** — refactored to consume the resolved-field layer; runtime materialization via `concept_factory` is byte-for-byte unchanged (the existing suite was the harness). Dead legacy dict-based paths deleted.
- **Docs** — `docs/under-the-hood/codegen-projections.md` (engine, trust chain, extension-file story, HTTP serving), plus native/inputs doc updates. `CHANGELOG.md` `[Unreleased]` covers everything user-visible.

## Breaking changes (intentional, changelogged — no-backward-compat policy)

- `pipelex build structures` output shape: one stamped `structures.py` + `codegen.lock`, bare-when-unique class names, declared imprecision instead of the old silent `TextContent` guess; `--force` gone; concepts-only loading API removed.
- `pipelex build runner` structures directory rides the same projection; the script imports emitted class spellings.
- `ImageContent` wire shape: `size` → paired `width`/`height` (both-or-neither validator).
- `Time` joins the reserved native codes; the former blanket bare-time input rejection (`InputsTimeOnlyNotSupportedError`) is removed — a top-level TOML time maps to `TimeContent`.

## Design decisions a reviewer might otherwise flag

- **Imprecision over guessing (D5/B1-3):** a structureless or Python-class-backed concept emits an explicit opaque/imprecise marker (`# imprecise:` / `@imprecise`, `extra="allow"` pass-through classes), never a fabricated shape. This is the spec'd behavior, not missing handling.
- **ts-zod keys are wire-native snake_case (D10):** a cold review empirically confirmed that a generic deep snake↔camel remap silently corrupts caller data keys inside `z.record()`/`z.unknown()` values, so the schema validates the wire directly and the remap layer does not exist. camelCase ergonomics, if ever wanted, must be a schema-aware transform.
- **Sibling `codegen.lock`, not an extension of `methods.lock` (D4):** different owner (Pipelex vs standard), location, content, and lifecycle — consumer projects often aren't MTHDS packages at all.
- **Verdicts are structural, exit codes/HTTP statuses are presentation** (workspace meta-rule): machine consumers branch on `is_valid`/error envelopes, never on exit codes.
- **`pipe_ref` is plumbed through the stamp but unused today:** the stamp format is spec'd to carry it for the per-pipe projection kinds that arrive in later phases; it is cheap and round-trip tested — not speculative dead code.
- **Loaded-on-success contract:** `resolve_crate_from_contents` (like `validate_bundle`) leaves the library loaded + current on success and the host owns teardown — the HTTP routes read live pipes from it before their `finally`. Teardown conservation is pinned by tests on both repos.
- **`native_expansion.py` reflection retained:** consistency probe only (pinned blueprint ↔ runtime class); materialization is the pinned lookup.

## Verification record

- Gates at every checkpoint and after the final dev merge: `make agent-check` (ruff, pyright 0, mypy 0, kw-only, plxt) + **full** `make agent-test`.
- Emitted-code quality gates in-tree: `pyright --strict` over generated Python (D7), serialize→parse round-trips, resolve→emit e2e over a multi-bundle closure fixture feeding every emitter; golden tests assert compile-and-parse behavior, not byte equality.
- Live binary proofs at each stage: stamp/lock/check drift loop (hand-edit → exit 1 → regen heals → byte-identical), alias re-point, agent-CLI envelopes and exit codes.
- **Proof by starter** (`pipelex-starter-python`, companion branch): hand-written models deleted, committed generated clients, offline smoke tests — the conversion caught and fixed real engine bugs (model-spec-less boot, structureless `Image`, non-deterministic template placeholders).
- Independent cold `/code-review` fan-outs (one reviewer per touched repo, diff-pointer only, no plan context) ran at every checkpoint; all confirmed findings were fixed in-branch (e.g. the ts-binder key-corruption Critical, the non-UTF-8 `codegen check` crash, the `time` exec-globals `NameError`) and design tradeoffs were recorded as deferred docs rather than reflexively applied.

## Cross-repo companions (separate branches, not in this PR)

`pipelex-api` `feature/Codegen` (routes `POST /v1/resolve` + `POST /v1/codegen`, breaking `/v1/build/*` migration — deploy gated on this release), `mthds` `feature/Codegen` (library-crate + native-concepts specs), `conformance` `feature/Codegen` (route conformance live; CLI skeletons release-gated), workspace-root `feature/Follow-ups` (`docs/specs/pipelex-codegen.md`), `mthds-js` `feature/Codegen` (agent passthrough stubs), `pipelex-starter-python` `feature/Codegen` (the converted starter). Post-release coordination lives in `wip/codegen/release-wave.md` at the workspace root.

## Deferred (documented, not in this PR)

The remaining Phase 3 stretches (MCP projection; webapp form + n8n), Phase 4 (methods as products), and Phase 5 (frontier) are deferred by decision (2026-07-11) and documented one-file-per-concern under the workspace root's `wip/codegen/`.
