# DevEx North Star — Implementation Plan (TODOS)

**Source of truth for the vision:** [`wip/devx/devex-north-star.md`](../wip/devx/devex-north-star.md) (workspace root). This file is the execution tracker: tasks, checkpoints, decisions, and cold-start state. When the two disagree on *what to build*, the north star wins; when they disagree on *current status*, this file wins.

**Working branches (actual, as of Checkpoint A):** pipelex `feature/Devex-codegen` in this worktree (`_codegen/`); mthds `feature/Codegen`; conformance `feature/Codegen`; workspace-root (`docs/specs/` + `wip/devx/`) on `feature/Follow-ups` (which also carries the north-star drafts). Louis pre-created the `feature/Codegen` branches. Phases 0–2 touch: `mthds/`, workspace-root, `conformance/`, `pipelex` (this worktree), then the starters. Phases 3+ fan out to `pipelex-api/`, `mthds-js/`, `pipelex-sdk-js/`, and hosted repos.

## Status block (update at every checkpoint)

- **Current phase:** Phase 2 — **2.1 trust chain DONE; CHECKPOINT C1 ✅ PASSED 2026-07-10** (mid-phase, mirrors B1). The codegen trust chain landed in pipelex: **stamp** headers on every generated file (`pipelex/codegen/stamp.py`), a sibling **`codegen.lock`** artifact-set manifest (`lock.py`), an **offline `codegen check`** command (`check.py` + `cli/commands/codegen/check_cmd.py`) — pure hashing, no engine/network, verdict on exit code 0/1/2, drift by category (missing/modified/hand-edited/orphan), and an **idempotent write-if-changed + stale-file-pruning** emission layer (`emission.py`) that `codegen types` now writes through. Verified end-to-end against the real binary. `make agent-check` + full `make agent-test` PASS. Cold Sonnet-5 review triaged (1 Critical UTF-8-crash fixed, orphan-scan scoped, dup suffix-list collapsed, 1 rejected).
- **Next action:** **Phase 2.2 — convert `pipelex-starter-python` as the DX proof** (Louis chose "convert one starter as a proof"; the two JS starters + D8 deferred to post-release). Concretely, in `pipelex-starter-python/` (repo at workspace root, branch `dev`, currently clean): (1) it has `.mthds` methods under `piper/methods/{summarize-pdf,extract-entities,generate-image}/main.mthds` and **hand-written models in `piper/examples/*.py`** (the layer to delete/replace); (2) generate a `python-pydantic` client per method via `pipelex codegen types` (run from THIS worktree's editable pipelex, since the starter only pins `pipelex-sdk`/`pipelex-tools`, NOT the `pipelex` runtime that hosts `codegen`), commit the generated + stamped models + `codegen.lock`; (3) add a `make codegen` (regen, dev action) + `make codegen-check` (offline) target and a generated smoke test (dry-run with template inputs); (4) wire `codegen check` into its CI. **⚠ RELEASE-GATED:** step (4) needs a *published* pipelex that ships `codegen` — none exists yet (0.38.0 has none). So CI wiring either pins an unreleased pipelex (fragile) or ships a standalone offline-check script; **flag for Louis / do the local conversion + commit now, leave CI wiring as the release-gated tail.** Same release-gate as B1-6 (conformance de-gate). **Also still deferred (flagged for Louis):** B1-1 normalization-layer policy for `structure="<ClassName>"`; B1-4 explicit defaults/multiplicity; **B1-5 cross-package fold-in + fixture 1** (Phase-3 pipe-graph); `build structures` re-point (D9); conformance check/stamp/lock de-skeleton (Phase-2 conformance, cross-repo/release-gated, sibling `conformance/` repo — the `test_codegen.py` `codegen check` skeleton de-gates once pipelex ships codegen). See `wip/devx/deferred-checkpoint-b1-items.md`.
- **Last checkpoint passed:** **Checkpoint C1** (mid-Phase-2) — trust chain landed in pipelex; cold review triaged (1 Critical fixed + 3 clean-solid applied + 1 rejected); gates green. Prior: **Checkpoint B** (engine + emitters + CLI). (Next full checkpoint is **C** after 2.2 starter conversion — release-gated in part.)
- **Last commit(s):** mthds `feature/Codegen` — …**B review `7b5573f`** (untouched this phase) · workspace-root `feature/Follow-ups` — …**B deferred-doc `e603a3a`** (untouched this phase) · conformance `feature/Codegen` `d42cadb` (untouched) · pipelex `feature/Devex-codegen` — …**CHECKPOINT-B `a1f73cc46`**, **B review-fix `7e1eb01a5`**, **B SHA-record `d594d2511`**, **Phase 2.1 trust chain `e70c7eebc`**, **C1 review-fix `9d4fc59d6`**. **Review diff already run for C1 = `d594d2511..e70c7eebc`; review diff for the NEXT checkpoint (C) = `9d4fc59d6..HEAD`.** **None pushed.**
- **Open decisions:** D1–D7 **SETTLED**; **D9 PROPOSED** (defer `build structures` engine re-point to Phase 2 starter conversion). **D8 OPEN** (settle at C — `mthds-starter-js` conversion; now leaning DEFER since only `pipelex-starter-python` is converted as the proof).
- **Deviations from north star found so far:** (1) The cookbook `extract_generic` case is *single-bundle* with the vendored dependency cache at the cookbook **repo root** (`pipelex-cookbook/.mthds/methods/documents/`), not per-case — the Phase 1 fixture must replicate that shape (bundle + ancestor `.mthds/methods/` cache) and a *separate* multi-bundle fixture must be authored, since no existing case exercises both at once. (2) Today's crate is built from **pre-validation blueprints** (`LibraryCrateFactory.make_from_blueprints`), while the north star requires the normalized crate be "built only from a valid library" — Phase 1 moves normalized-crate emission downstream of library load + validation (settled as D6). (3) **Two dependency caches exist** and the sibling standard specs only documented the global one (`~/.mthds/packages/{address}/{version}/`); the north star + pipelex use the project-local `.mthds/methods/<name>/` — the crate spec now documents both (Checkpoint-A review fix). (4) `codegen.lock` is a **sibling** to `methods.lock`, not an extension (D4 SETTLED) — diverges from the plan's initial "one lock, two sections." (5) **[B1 review]** normalization currently leaves two shapes lossy for the sufficiency/round-trip guarantees — Python-backed `structure="<ClassName>"` concepts (B1-1) and native-refinement flattening (B1-2); both deferred with Louis' steer to before Checkpoint B.

## Cold-start protocol

A fresh session resumes by reading, in order: (1) this file top to bottom, (2) `wip/devx/devex-north-star.md`, (3) the "Ground map" table below to avoid re-exploring, (4) the current phase's task list. Do not re-derive settled decisions — they are in the Decision log with rationale.

- **Decision authority:** the agent never silently locks in a D-decision. It records a PROPOSED answer with rationale in the Decision log and keeps working on everything not blocked by it; PROPOSED becomes SETTLED only when Louis confirms at (or before) the checkpoint stop. If a task hard-depends on an unsettled decision, build to the proposal and flag it in the checkpoint notes.
- **This file is the tracker — commit it** with every checkpoint commit on the pipelex branch so cold-start state survives sessions and machines (it is currently the branch's first change).
- **Branches/PRs:** pipelex feature PRs target `dev` per repo convention; other repos target their default branch. Commit at checkpoints; never push or open PRs unless Louis asks.

## Ground map (existing organs — verified 2026-07-09, don't re-explore)

| Organ | Where | Notes |
| --- | --- | --- |
| `LibraryCrate` | `pipelex/libraries/library_crate.py` | Fields: `concepts`, `pipes`, `domains`, `source_map`, `fingerprint`. SHA-256 fingerprint over sorted concepts+pipes JSON (`compute_fingerprint_from_content`); **excludes** `domains`/`source_map`. |
| `LibraryCrateFactory` | `pipelex/libraries/library_crate_factory.py` | `make_from_blueprints`. Only normalization today = ref qualification of dict *keys*; string-described concepts kept verbatim; no refinement flattening / native expansion / defaults materialization; concept-ref validation deliberately deferred to the loader. |
| Crate consumers | `library_manager.py` (`get_crate` :257, `load_from_crate` :425), `pipeline/execution_seams.py:278`, `runtime_bridge/payloads.py` | Fingerprint-idempotent load; Temporal shipping via `library_crate_dump` (JSON only; no TOML, no CLI emitter today). |
| Closure / local cache | `pipelex/libraries/library_manager.py` | `MTHDS_METHODS_DIRNAME=".mthds/methods"` :59, `_find_methods_dirs_from_blueprints` :62 (walks ancestors), `_load_address_based_dependencies` :1142, per-dep isolated child libraries :981. Manifest logic from external `mthds.package`. |
| `StructureGenerator` | `pipelex/core/concepts/structure_generation/generator.py` | `generate_from_structure_blueprint` → (module source, compiled class). Semantic mapping: choices→Literal, list/dict recursion, native resolution, bare-ref promotion via `local_domain`, refines base recovery, forward refs. Validation gate: `validate_generated_code` (ast→compile→exec→MRO check). **Dead legacy dict path:** `_generate_field` :507, `_get_python_type` :557, `enum_definitions` :72 — no callers, delete in Phase 1. |
| StructureGenerator consumers | `pipelex/core/concepts/concept_factory.py` (runtime, 3 sites), `pipelex/cli/commands/build/structures_cmd.py` (CLI) | Runtime materialization must keep working unchanged through the extraction. |
| Input/output renderers | `pipelex/core/pipes/inputs/input_renderer.py`, `pipelex/core/pipes/output/output_renderer.py`, `pipelex/core/memory/input_shaper.py` | Compact/explicit templates, JSON+TOML; Smart Inputs semantics. Reused as-is per north star. |
| Pipe IO contracts | `pipelex/pipeline/pipe_io_contracts.py` | `PipeIOContract`/`build_pipe_io_contracts`, keyed by `pipe_ref`. |
| CLI | main `pipelex/cli/_cli.py`; `build` family `pipelex/cli/commands/build/`; agent CLI `pipelex/cli/agent_cli/`; dev CLI `pipelex/cli/dev_cli/` | **No `resolve` or `codegen` command exists anywhere** — clean namespace. |
| Validate route (envelope model) | `pipelex-api/api/routes/pipelex/validate.py` | 200 + `is_valid` discriminated union; request `mthds_contents[]` + `mthds_sources[]` + lenient `render[]`; RFC 7807 for no-verdict. Codegen routes copy this pattern. |
| Existing build routes | `pipelex-api/api/routes/pipelex/build/` (`inputs`, `output`, `runner`) + `agent/` (`concept`, `pipe-spec`) | To be re-pointed at the engine in Phase 3. |
| Specs home | workspace-root `docs/specs/` (front matter `id:` + `sources:`; `> Verified by:` blockquotes; `<!-- unverified: reason -->`) | Conventions documented in `docs/specs/README.md`; update `command-surface-map.md` when adding surfaces. |
| Conformance | `conformance/tests/<target>/` with `pytestmark = pytest.mark.spec("docs/specs/<file>.md#<anchor>")`; per-dir `test_data.py` CLISpec; `make check-spec-links` | Gate is part of its `make agent-check`/`ci-check`. |
| MTHDS standard specs | `mthds/docs/spec/` (`manifest-format.md`, `lock-format.md`, `mthds-format.md`, `namespace-resolution.md`, `protocol.md`) + `docs/implementers/package-loading.md` ("Library Assembly") | No "library crate" concept exists there yet — Phase 0 adds it. Nav in `mkdocs.yml`. |
| Superseded design docs (mine for mechanics, not direction) | `wip/devx/pipelex-core-codegen-design.md` (vocabulary, target tokens, stamp fields, `CodegenResult` envelope), `wip/devx/track-d-design.md` (route envelope, TS naming rules, type-mapping table, purity split: pure types file + thin binder) | North star supersedes on conflicts. |
| Starters (Phase 2 targets) | `pipelex-starter-python/piper/examples/*.py` (hand-written models + `parse()`), `pipelex-starter-js/src/types/*Pipeline.ts`, `mthds-starter-js/src/types/*.ts` | These hand-written layers are what Phase 2 deletes and regenerates. |
| Cookbook fixture source | `pipelex-cookbook/examples/b_basics/document_extract/extract_generic/bundle.mthds` (cross-package ref at line 11) + repo-root `.mthds/methods/documents/` (`documents.mthds` + `METHODS.toml`) | Vendor a copy into pipelex test fixtures — tests must not depend on the cookbook checkout. |

## Standing gates (every phase, before every checkpoint)

- pipelex (this worktree): `make agent-check` then `make agent-test`.
- conformance: `make check-spec-links` (and its test suite when conformance tests were touched).
- Other repos: their own repo-local check/test targets when touched.
- Docs: every repo touched gets its `docs/` updated in the same change; changelogs use `[Unreleased]`; no hardcoded counts; no hard-wrapped markdown.

## Checkpoint protocol (MANDATORY — the agent stops here, no exceptions)

At each checkpoint below, the agent must complete ALL of the following and then **end the session turn — do not begin the next phase in the same run**:

1. **Verify** — run every standing gate in every repo touched during the phase; confirm the phase's definition-of-done bullets; fix or explicitly defer anything red.
2. **Commit** — one or more clean commits per repo (no push unless the user asked); record SHAs in the Status block.
3. **Fan out `/code-review`** — spawn one **Sonnet-5** sub-agent per repo touched in the phase, running the `/code-review` skill. **No inherited context:** each reviewer receives ONLY a pointer to the changes (repo path + `git diff <base-SHA>..<head-SHA>` range, or the working-tree files) and the instruction to review at high effort with an eye against over-engineering — never the plan, the north star, the rationale, or this session's conclusions. Triage findings: apply clean-solid fixes; genuine design tradeoffs are captured as deferred-item docs under `wip/devx/` (workspace) rather than reflexively applied; rejected findings get one line of why in the checkpoint notes.
4. **Update for cold start** — refresh this file's Status block, tick completed checkboxes, append to the Decision log and Checkpoint notes, reconcile any deviation into the later phases' task lists, and update `wip/devx/devex-north-star.md` per its own checkpoint protocol (completed work, decisions, deviations, open questions).
5. **Cold-start test** — re-read this file as if fresh: could a new session continue without asking anything the file should answer? If not, fix the file before stopping.

---

## Phase 0 — Contract (specs + conformance skeletons before any engine code)

Contract-first: nothing in Phase 1 starts until Checkpoint A passes.

### 0.1 Spec the normalized library crate in the MTHDS standard (`mthds/` repo)

- [x] New formal spec `mthds/docs/spec/library-crate.md`, beside `manifest-format.md` and `lock-format.md`, covering: the three units (bundle / library / pipe) and the resolution rule (resolve a library; project types over its concept set; project runnables per pipe).
- [x] Closure-assembly rules: working bundles + local method cache (`.mthds/methods/`, ancestor-walk discovery), cross-package refs, alignment with `namespace-resolution.md` and `docs/implementers/package-loading.md` §"Library Assembly" (cross-reference, don't duplicate).
- [x] Normalization pass, precisely: merge bundles; fully qualify **every** ref (dict keys AND in-body refs: pipe steps, inputs/output concept refs, `refines`); flatten refinement into effective structures; expand native concepts pinned to the spec version; materialize defaults and multiplicity; promote string-described concepts to explicit blueprint form; built only from a *valid* library (the artifact carries the verdict implicitly).
- [x] Fingerprint definition: SHA-256 over canonical JSON of normalized content; specify exact canonicalization (sorted keys, ascii, sorted refs — today's `compute_fingerprint_from_content` is the seed) and the hash **scope** decision (D2 below).
- [x] Both encodings: JSON (machine-native, keyed to the published `mthds_schema.json` model) and TOML (human-diffable, directly runnable); canonical serialization rules for each so independent implementations byte-agree.
- [x] The sufficiency guarantee, stated as a testable contract: a consumer with only a JSON/TOML parser and one normalized crate can emit correct types / render a correct form / register a correct tool — no loader, no namespace resolution, no hardcoded natives.
- [x] Wire into `mkdocs.yml` nav; add narrative pointer from `docs/packages/` if appropriate; `[Unreleased]` changelog entry.

### 0.2 Spec the codegen surface in `docs/specs/` (workspace-root repo)

- [x] New spec (proposed: `docs/specs/pipelex-codegen.md`; split later only if it bloats — D3) with front matter (`id:`, `sources:`) and per-surface `> Verified by:` / `<!-- unverified: -->` markers, covering:
  - [x] **Stamp header format** — fields: source crate fingerprint, engine version, projection, options, generated-content hash; comment syntax per emitted language; self-describing requirement.
  - [x] **Lock format** — artifact-set manifest with hashes (catches deleted-concept stale files); named "lock" not "manifest"; relationship to `methods.lock` per decision D4.
  - [x] **Offline check algorithm** — pure hashing, no network / API key / engine; spec'd precisely enough for independent implementation (CLI, SDK, short CI script); exit/verdict semantics.
  - [x] **CLI surface** — `pipelex resolve` (emit crate, JSON|TOML); `pipelex codegen types|inputs|docs|tools|tests --target <flavor> [--pipe <pipe_ref>]` (two explicit axes, no flat kind×format enum; `--pipe` defaults to `main_pipe`); `codegen check`; `codegen diff`; `build inputs`/`build structures` re-pointing as aliases. Verdict in structured output, never exit code (workspace meta-rule).
  - [x] **Route envelopes** — codegen + resolve routes on `pipelex-api`: request accepts inline `files[]` (multi-bundle) *or* `method_ref`; response 200 discriminated on `is_valid` exactly like `/v1/validate`; request-shape errors (unknown projection/target) are 422 problem+json; resolution and type/schema projections flagged protocol capabilities (`x-mthds-protocol`), runtime-structures emission stays a Pipelex extension.
  - [x] **Name-derivation rules** — slug → file/module/type spellings spec'd once for every consumer: TS camelCase with bidirectional wire snake↔camel mapping and wire names documented inline; Python stays snake_case; domain-qualified class naming (existing `make_qualified_structure_class_name` behavior is the seed).
- [x] Update `docs/specs/command-surface-map.md` with the codegen/resolve chain.
- [x] Update `docs/specs/README.md` table.

### 0.3 Conformance skeletons (`conformance/` repo)

Skeleton semantics (applies to all of Phase 0): a skeleton module asserts the spec'd envelope but is marked skip/xfail with a reason naming the phase that implements the surface (CLI surfaces → Phase 1, routes → Phase 3, check/stamp/lock → Phase 2); the implementing phase de-skeletons it. At Checkpoint A only `check-spec-links` must be green — no skeleton needs to pass.

- [x] Skeleton test modules pinning the CLI envelopes: `tests/pipelex/test_resolve*.py`, `tests/pipelex/test_codegen*.py`, each with `pytestmark = pytest.mark.spec(...)` pointing at 0.2 anchors; extend the dir's `test_data.py` CLISpec.
- [x] Skeleton module pinning the crate shape itself (normalized-crate JSON fixture asserted against the spec's structural promises: flat, fully qualified, no unexpanded natives, fingerprint present and recomputable).
- [x] Skeleton modules for the route envelopes under `tests/pipelex_api/`.
- [x] `make check-spec-links` green across the spec↔test pairs.

### 0.4 Decisions to settle before Checkpoint A (record answers in the Decision log)

- [x] **D1 — crate spec naming**: "library crate" as the standard's term (neutral, no `pipelex_` wire fields) — confirm or rename once, before anything ships.
- [x] **D2 — fingerprint scope**: today's hash covers concepts+pipes only; domains carry `system_prompt` and `main_pipe` which are semantic. Decide inclusion (proposal: include normalized domain metadata; exclude `source_map`).
- [x] **D3 — one spec file or split** (CLI/stamps/lock/check vs routes vs naming). Proposal: one file, sectioned.
- [x] **D4 — lock relationship**: extend `methods.lock` (north star hints "same lock that will later pin remote-dependency SHAs") vs sibling artifact lock. Proposal: one lock file, two sections; spec the codegen section now, dependency section already spec'd.
- [x] **D5 — string-described concepts**: normalization promotes them to explicit `ConceptBlueprint` form — confirm the promoted shape.
- [x] **D6 — crate build point**: normalized crate is emitted from the loaded+validated Library (post-`validate_library()`), not from raw blueprints; the existing pre-validation `make_from_blueprints` path stays for Temporal transport until reconciled. Confirm.

### CHECKPOINT A — contracts reviewed and settled before engine code

- [x] Full checkpoint protocol executed (verify · commit · `/code-review` fan-out per touched repo: `mthds`, workspace-root, `conformance` · TODOS/north-star update · cold-start test · STOP).
- [x] Definition of done: specs merged-ready on their branches; conformance skeletons exist and `check-spec-links` passes; every D1–D6 decision recorded with rationale.

---

## Phase 1 — Engine and first projections (in `pipelex`, this worktree)

A refactor around existing organs, not a rewrite. Genuinely new code: the normalization pass, the neutral resolved-field layer, the Zod/TS emitter.

### 1.1 Neutral resolved-field layer (extraction from `StructureGenerator`) — ✅ DONE

- [x] Extract the semantic mapping (choices→literal, list/dict recursion, concept-ref resolution incl. natives, bare-ref promotion, `refines` base recovery, forward refs for cycles) into a neutral resolved-field model every emitter consumes → `pipelex/codegen/resolved_fields.py` (`ResolvedField`/`ResolvedType`/`ResolvedTypeKind`, `resolve_structure_fields`).
- [x] Refactor `StructureGenerator` to consume the layer; runtime behavior via `concept_factory.py` unchanged (existing suite is the harness — byte-identical output, 307 tests green).
- [x] Delete the dead legacy dict-based path (`_generate_field`, `_get_python_type`, `enum_definitions`).
- [x] Where the source is imprecise (untyped `list`, structureless concept): resolved field carries an explicit imprecision marker (`ANY` + `imprecise`/`imprecision_reason`) emitters must surface, never a guess.

### 1.2 Normalization pass → normalized crate — ✅ DONE

- [x] Implement the spec'd normalization → `pipelex/libraries/crate_normalization.py` (`normalize_crate`), producing a normalized `LibraryCrate` from a loaded, validated Library (per D6): in-body ref qualification (multiplicity markers preserved), refinement flattening into effective structures, native expansion (`pipelex/codegen/native_expansion.py`, faithful-or-structureless via introspection, pinned to `mthds_version`), string-concept promotion (D5). `CrateNormalizationError` in `pipelex/libraries/exceptions.py`.
- [x] Fingerprint per D2 scope → `LibraryCrate.compute_normalized_fingerprint` (concepts+pipes+domains, per-object `source` stripped, canonical JSON ≈ JCS); `compute_fingerprint_from_content` kept for the transport crate (D6/D-A2).
- [x] Round-trip guarantee tests: normalized crate loads via `load_from_crate` and validates (integration); normalizing twice is a fixed point (unit idempotence test). **Loader change:** `_load_concepts_from_crate` now skips `native.*` entries (pre-registered natives would collide — this is the D-A1/D6 round-trip enabler).

### 1.3 Crate encodings + `pipelex resolve` CLI — ✅ DONE

- [x] JSON and TOML encodings → `pipelex/codegen/crate_encoding.py` (`encode_crate_json/toml`, `encode_crate`, `CrateEncoding`); top-level maps key-sorted, nested field order preserved, inline `source` + `pipe_category` dropped (non-semantic), TOML dotted qualified refs quoted (tomlkit).
- [x] New `pipelex resolve [PATH]... [-f json|toml] [-L DIR]...` command → `pipelex/cli/commands/resolve_cmd.py`, registered in `pipelex/cli/_cli.py` (`_CORE_COMMAND_ORDER` + `app.command`). Flow: `make_pipelex_for_cli → load_libraries_and_activate → get_crate → normalize_crate(mthds_version=MTHDS_STANDARD_VERSION) → encode`. Exit codes 0 resolved / 1 invalid library / 2 empty-closure|not-found.
- [x] TOML-encoded crate is directly runnable (parse → `LibraryCrate` → `load_from_crate` into a live library) — proven in `test_resolve_flow.py`.

  Tests added: `tests/unit/pipelex/libraries/test_crate_normalization.py`, `tests/integration/pipelex/libraries/test_crate_normalization_round_trip.py`, `tests/unit/pipelex/codegen/test_crate_encoding.py`, `tests/integration/pipelex/codegen/test_resolve_flow.py` (multi-bundle closure = fixture 2 shape), `tests/unit/pipelex/cli/test_resolve_exit_codes.py`.

### CHECKPOINT B1 — resolver landed (mid-phase) — ✅ PASSED 2026-07-09

Code for 1.1–1.3 written + committed on `feature/Devex-codegen`; gates green; cold `/code-review` fan-out triaged; decisions settled with Louis; deferrals documented.

- [x] Full checkpoint protocol executed (repos: `pipelex`; `/code-review` fan-out on `1a7f9fe42..HEAD` — cold Sonnet-5, no plan/north-star context, anti-over-engineering; triage → 2 clean-solid fixes applied + 1 test, 2 high-sev design tradeoffs + follow-ups deferred to `wip/devx/deferred-checkpoint-b1-items.md`, 1 finding rejected; docs updated; STOP).
- [x] Definition of done: **1.1–1.3 complete ✅** and gates green ✅ (`make agent-check` + `make agent-test`, re-run post-fix); `pipelex resolve` emits a spec-conformant crate for the **multi-bundle fixture (fixture 2) ✅** — **fixture 1 (`extract_generic` cross-package) DEFERRED** (B1-5: `get_crate` returns only root-package content; single-package closures fully normalize; fold-in is additive); **conformance crate-shape skeleton de-gate DEFERRED** (B1-6: conformance repo not in this worktree — release-gated cross-repo step).
- [x] **D7 SETTLED** (Louis): pyright gate on emitted Python lives in pipelex tests; `tsc --strict` gate on emitted TS lives in `conformance/` (cross-repo harness already has a node toolchain). Recorded in the Decision log.

### 1.4 Emitters — types projection DONE (`002ec98a4`); per-pipe helpers moved to 1.5

**Scope seam (deliberate, flagged):** 1.4 delivered the full **`types` projection** (concept set → typed models) for all three targets — the headline of the phase. The **per-pipe** bullets below (parse/serialize helpers, the ts binder file, the runnable compact-input example) are moved to **1.5**, where the pipe-selection + `input_renderer`/`pipe_io_contracts` plumbing they require actually lives. The ts-zod **purity split** is honored: 1.4 ships the pure types file (imports only zod); the binder file lands in 1.5.

- [x] `python-structures` emitter: runtime `StructuredContent` classes over the resolved layers → `pipelex/codegen/emitters/python_structures.py`; extension-file header replaces the copy-this-file guidance. Native refs map to runtime content classes; natives not re-emitted.
- [x] `python-pydantic` emitter: plain `BaseModel`, no pipelex imports, natives emitted uniformly (self-contained) → `python_pydantic.py`. **Parse/serialize helpers per pipe → moved to 1.5.**
- [x] `ts-zod` emitter (new): pure types file — zod schemas + inferred types, camelCase keys with `@wire` JSDoc, `z.lazy` concept refs → `ts_zod.py`. **Parse/serialize helpers + thin binder file → moved to 1.5.**
- [x] Each field's **wire name** embedded (ts `@wire` JSDoc; Python names are already wire-native). **Runnable compact-input example (from `input_renderer`) → moved to 1.5** (per-pipe).
- [x] Generated code is never edited: extension-file mechanism (Python subclassing, TS declaration merging) documented in every generated header + `docs/under-the-hood/codegen-projections.md`.
- [x] **B1-3 floor:** imprecision markers surfaced — inline `# imprecise:` (Python) / `@imprecise` JSDoc (ts), never a silent `Any`/`z.any()`. **B1-1 floor:** a `structure="<ClassName>"` / structureless concept is surfaced opaque, never silently emitted.

**New code:** neutral `resolved_concepts.py` (crate concept → `ResolvedConcept`: collision-aware class naming, refinement base, native flag, structureless/opaque markers) + `resolved_fields.iter_imprecision_reasons` walker + `emitters/` package (`naming`, `target`, `python_common`, the three emitters, `types_emitter` dispatch). Tests: `tests/unit/pipelex/codegen/{test_naming,test_resolved_concepts,test_python_structures_emitter,test_python_pydantic_emitter,test_ts_zod_emitter}.py` (+ `conftest.py`); Python output is compile+exec-validated (real classes built), ts is structural (tsc gate is conformance's per D7).

**Divergences from today's `build structures` (deliberate, documented — reconcile at Phase-2 starter conversion):** (a) **naming** — emitters use the spec's *bare-when-unique, domain-qualified-on-collision* rule (`Report`, and `alpha__Result`/`AlphaResult` only on collision), whereas `build structures` always qualifies; cross-refs within a generated set stay consistent, and runtime-embedding reconciliation (does `concept_factory` need the always-qualified name?) is a Phase-2 concern. (b) **structureless honesty** — a structureless concept is surfaced as *imprecision/opaque*, not guessed as `TextContent` the way `build structures` defaults; matches D5 + the north-star "surface imprecision, never guess".

### 1.5 `pipelex codegen` CLI family (+ per-pipe emitter helpers moved from 1.4)

- [x] `codegen types --target ts-zod|python-pydantic|python-structures` (concept set) — thin wiring over `emit_types` (`pipelex/cli/commands/codegen/types_cmd.py`), writing `EmittedFile`s under `--output`; `codegen inputs [--pipe <ref>]` re-surfacing `input_renderer` over the selected pipe (compact default, `--explicit` opt-in — Smart Inputs policy unchanged), `--pipe` defaulting to the closure's `main_pipe` (`inputs_cmd.py`). Shared crate loader (`crate_loading.py`) centralizes the resolve/validate exit-code contract; `resolve_cmd` refactored onto it.
- [x] **Per-pipe emitter helpers:** the **ts binder file** (`binder.ts`, generic deep snake↔camel wire mapping + `parse<T>`/`serialize<T>` per concept over the pure `types.ts`) completes the purity split. **The parse/serialize "per pipe" helpers are subsumed by the concept-set-wide binder** (a pipe's IO types are concepts, so its output-parser / input-serializer is the binder pair for those types) — documented reasoning. `python-pydantic` parse/serialize are the **native** `model_validate`/`model_dump` (wire == snake python names, no binder needed). The **runnable compact-input example** is delivered by `codegen inputs` itself (the canonical runnable template) rather than duplicated into type-file docstrings, which are concept-set-wide (not pipe-scoped).
- [x] `pipelex build inputs` shares the same `input_renderer` engine as `codegen inputs` (behavior preserved — they can't diverge). **`pipelex build structures` re-point DEFERRED to Phase 2** (D9: its always-qualified per-file output diverges from the bare-when-unique single-file engine; re-pointing would silently change output). **Agent-CLI codegen mirrors = Phase 3** (the plan's "Agent CLI passthrough" line) — no agent-CLI change needed at 1.5 since `build inputs`/`structures` behavior is unchanged.
- [x] Two-axis flags exactly as spec'd (`kind` command × `--target`); structured verdict rides the resolve exit codes; success stream = written-file list.

### 1.6 Fixtures (vendored into pipelex tests, no cookbook dependency)

- [~] Local-cache / cross-package fixture (`extract_generic`-shaped): **DEFERRED with B1-5** (reframed) — its cross-package ref is a *pipe* ref and its concept surface is all-native, so the Phase-1 types/inputs projections don't need cross-package concept fold-in; a hermetic cross-package fixture needs the address-based installed-method machinery (`methods.lock` + cache + address mapping). See `wip/devx/deferred-checkpoint-b1-items.md` B1-5.
- [x] Multi-bundle closure fixture: the single-package, cross-file `MAIN_MTHDS`/`STEPS_MTHDS` closure in `tests/integration/pipelex/codegen/test_resolve_flow.py` (authored fresh; recursive-build style).
- [x] The multi-bundle fixture resolves end-to-end through the resolver (`get_crate` → `normalize_crate`) and **feeds every emitter** (`test_multi_bundle_closure_feeds_every_emitter`: all three targets emit, the Python execs into real classes).

### 1.7 Quality gates from day one

- [x] Strict-pyright gate on emitted Python (D7): `test_emitted_python_typechecks.py` projects a rich crate (every `ResolvedType` kind + literal-default + optional + native + refines-native) and runs `pyright --strict` over the generated `structures.py`/`models.py`, asserting 0 errors. **`tsc --strict` on emitted TS lives in `conformance/` (D7) — release-gated cross-repo, like B1-6** (no node/zod toolchain in this worktree; the ts binder has a structural unit test here).
- [x] Serialize→parse round-trip: `test_serialize_parse_round_trip` (python-pydantic `model_dump` → `model_validate` reproduces the value). The ts binder round-trip is conformance's (needs a zod runtime).
- [x] Golden tests assert **compile-and-parse behavior, not byte equality** — every emitter test execs the generated Python into real classes (`load_generated_module` / the e2e + pyright tests), so templates stay free to improve.

### CHECKPOINT B — engine and emitters landed with gates green

- [ ] Full checkpoint protocol executed (repos: `pipelex`, possibly `conformance`; independent `/code-review` fan-out; STOP).
- [ ] Definition of done: all Phase 1 boxes ticked; both fixtures pass every emitter + gate; runtime structures codegen fully absorbed (old standalone path gone, `concept_factory` runtime unchanged); docs (`docs/` in pipelex) describe the engine, the crate, and the extension-file story; `[Unreleased]` changelog entry.

---

## Phase 2 — Trust chain and proof by starters

### 2.1 Trust chain (in `pipelex`) — ✅ DONE (`e70c7eebc`, review-fixed `9d4fc59d6`)

- [x] Stamp writer/parser per the 0.2 spec → `pipelex/codegen/stamp.py` (`CodegenStamp`, `apply_stamp`/`parse_stamped`, fenced `>>> … >>>` block in the target's comment syntax; content hash over the body below the stamp; `CodegenKind` axis added to `emitters/target.py`). Records crate fingerprint, engine version, projection (`kind / target [/ pipe_ref]`), options, content hash.
- [x] Lock per D4 → `pipelex/codegen/lock.py` (`codegen.lock`, human-diffable TOML, artifact path + body hash + crate fingerprint + engine version; artifacts sorted by path).
- [x] `pipelex codegen check` → `pipelex/codegen/check.py` + `cli/commands/codegen/check_cmd.py` — offline, pure hashing, **no engine boot / network / API key**; drift categories missing/modified/hand-edited/orphan; verdict on exit code 0 current · 1 drift · 2 no-lock (mirrors resolve/validate). (The "short-CI-script recipe" = the offline algorithm is documented in `docs/under-the-hood/codegen-projections.md` and the spec; a literal standalone script is the starter's release-gated tail.)
- [x] Write-if-changed everywhere → `pipelex/codegen/emission.py` (`write_stamped_projection`: stamp → write-if-changed → prune de-listed stamped files → rewrite lock). `codegen types` re-pointed onto it. Idempotent, prunes only files still carrying our stamp (never touches hand-authored files).
- [~] Conformance tests de-skeleton for check/stamp/lock surfaces → **DEFERRED (cross-repo / release-gated, like B1-6)**: the skeletons live in the sibling `conformance/` repo (not this worktree) and de-gate once a published pipelex ships `codegen`. Pipelex-side coverage is complete (`tests/unit/pipelex/codegen/test_{stamp,lock,check,emission}.py` + `tests/unit/pipelex/cli/test_codegen_check_cli.py`).

### CHECKPOINT C1 — trust chain landed (mid-phase) — ✅ PASSED 2026-07-10

Code for 2.1 written + committed on `feature/Devex-codegen`; gates green; cold `/code-review` fan-out triaged; end-to-end verified against the real binary. Full checkpoint protocol executed (repos: `pipelex`; STOP for context clear before 2.2). See the Checkpoint C1 note at the bottom.

### 2.2 Starters convert (definition-of-done gate for the core DX) — Louis: convert ONE (`pipelex-starter-python`) as the proof

- [ ] `pipelex-starter-python` (**the chosen proof**): delete hand-written models in `piper/examples/*.py`; generate + commit a `python-pydantic` client per method (methods at `piper/methods/*/main.mthds`) via `pipelex codegen types` (run from THIS editable pipelex worktree — the starter doesn't pin the `pipelex` runtime); `make codegen` (regen) + `make codegen-check` (offline) targets; generated smoke test (dry-run with template inputs). **⚠ CI `codegen check` wiring = RELEASE-GATED** (needs a published pipelex shipping `codegen`); do the conversion + commit now, leave live-CI wiring as the tail (or ship a standalone check script). Flag for Louis.
- [ ] `pipelex-starter-js`: **DEFERRED to post-release** (Louis chose the single-starter proof). Would delete `src/types/*Pipeline.ts`; wire generated ts-zod client; check in CI; smoke test.
- [ ] `mthds-starter-js`: **DEFERRED (D8 → lean defer)** — decide formally at Checkpoint C.
- [ ] The SDK inversion boundary honored in the converted starter: nothing method-shaped remains hand-written; SDKs (`pipelex-sdk`) untouched except plumbing hooks if strictly needed.

### CHECKPOINT C — starters converted and gated

- [ ] Full checkpoint protocol executed (repos: `pipelex`, both starters, `conformance`; independent `/code-review` fan-out per repo; STOP).
- [ ] Definition of done: starters build and run on generated code only; their CI runs the offline check; **envelope deviations discovered during 1–2 reconciled back into the Phase 0 specs** (spec + conformance updated in the same change, `check-spec-links` green); D8 recorded.

---

## Phase 3 — Every surface, one authority

Detail to be firmed at Checkpoint C reconciliation; current task shape:

- [ ] **API routes** on `pipelex-api`: resolve + codegen routes per the 0.2 envelope spec (inline `files[]` | `method_ref`; 200 + `is_valid`; 422 problem+json for request shape; protocol-capability flags); existing `/v1/build/*` routes re-pointed at the engine; de-skeleton `tests/pipelex_api/` conformance modules.
- [ ] **Agent CLI passthrough**: `pipelex-agent` codegen commands (Markdown/JSON two-stream per the agent-CLI output conventions) and `mthds-agent` passthrough per `command-surface-map.md`.
- [ ] **MCP projection**: every installed method (exported pipe) exposed as a generated typed MCP tool; install-time skill + generated Markdown method card (purpose, IO, runnable example) + input templates; per `docs/specs/pipelex-mcp.md` conventions.
- [ ] **Webapp form + n8n**: form spec projection consumed by `pipelex-app`; `n8n-nodes-pipelex` parameters re-pointed at the crate (public-API surface only — no layer crossing).

### CHECKPOINT D — agent experience end-to-end

- [ ] Full checkpoint protocol executed (`/code-review` fan-out per touched repo; STOP).
- [ ] Definition of done: an agent can discover, understand, run, and modify a method through generated affordances only — demonstrated live; cold-start pass.

---

## Phase 4 — Methods as products

- [ ] Content-addressed artifact hosting on the Hub, keyed by (crate fingerprint, engine version, projection, options) — registry as cache in front of the engine.
- [ ] Typed-package install (TS + Python) wrapping the exported entry pipe from `METHODS.toml` `exports`/`main_pipe`.
- [ ] Generated method pages (plain-language card, IO tables, runnable example, OpenAPI view) — nothing hand-written on the page.
- [ ] `codegen diff` — semantic diff of two crates → interface changelog; breaking-change badges; generated release notes.
- [ ] Run-time schema handshake: clients send build-against crate fingerprint per run request; server compares and warns/rejects; wired through the run protocol and both SDKs.

### CHECKPOINT E — publish-to-install loop demonstrated on a real method

- [ ] Full checkpoint protocol executed; cold-start pass; STOP.

---

## Phase 5 — Frontier (each item independently schedulable after E)

- [ ] Remote-dependency fetching: clone `github.com/...` methods into the cache, lock-pinned SHAs — slots in before resolution, nothing downstream of the crate changes.
- [ ] Watch mode + LSP-live types in `vscode-pipelex` (the signature demo: cross-bundle concept edit reddens the TS app in the same second).
- [ ] Per-method OpenAPI projection.
- [ ] `codegen lift` for pydantic (one-shot deterministic import, never a sync).
- [ ] Third-party generator story: the normalized crate (JSON) documented and evangelized as public emitter input.

---

## Decision log

Statuses: OPEN (no proposal yet) → PROPOSED (agent's answer + rationale recorded, work may build on it) → SETTLED (confirmed by Louis at a checkpoint stop). Only SETTLED decisions are immune to re-litigation.

| # | Decision | Status | Answer / rationale |
| --- | --- | --- | --- |
| D1 | Crate spec naming in the standard | SETTLED | **"library crate"** is the standard's term; the resolved-and-explicit form is the **"normalized library crate"** (short: "crate"). Wire/field names stay neutral — `concepts`, `pipes`, `domains`, `source_map`, `fingerprint` — no `pipelex_` prefix (matches the runtime `LibraryCrate` model and the brand rule: the artifact belongs to the standard). "Authored form" names the concise multi-bundle style. |
| D2 | Fingerprint hash scope (domains/system_prompt/main_pipe in or out) | SETTLED | **Widen** to `{concepts, pipes, domains}`: the normalized fingerprint is SHA-256 over canonical JSON of concepts + pipes + per-domain `{code, description, system_prompt, main_pipe}`. **Exclude** each domain's `source` and the top-level `source_map` (pure provenance — hashing file paths would make the fingerprint unstable under relocation). Rationale: `system_prompt` and `main_pipe` are execution semantics and `description` surfaces in doc/card projections, so a change to them *is* a meaning change that must invalidate downstream artifacts; today's concepts+pipes-only seed (`compute_fingerprint_from_content`) is widened in Phase 1. No back-compat concern (Temporal not shipped — see `project_temporal_not_shipped`). |
| D3 | One codegen spec file vs split | SETTLED | **One file**, `docs/specs/pipelex-codegen.md`, sectioned (stamp · lock · check · CLI · routes · naming · crate-shape contract). Split only if it bloats past readability. |
| D4 | Codegen lock: extend `methods.lock` vs sibling | SETTLED (Louis confirmed the sibling; ⚠ diverges from plan's initial "one lock, two sections") | **Sibling lock** (`codegen.lock`), a Pipelex-codegen artifact spec'd in `docs/specs/pipelex-codegen.md` — **not** an extension of the standard's `methods.lock`. Rationale: `methods.lock` is *standard-owned*, pins *remote dependencies* (version/hash/source) of an MTHDS **package**, and lives beside `METHODS.toml`; the codegen lock is *Pipelex-owned*, records the *generated-artifact set* (files + content hashes) in a **consumer project** that is often not an MTHDS package at all (a pure TS/Python app has no `METHODS.toml`/`methods.lock`). Different owner, location, content, lifecycle, and context-of-existence — folding Pipelex-codegen artifact hashes into the standard's lock would cross the brand/ownership boundary. The north star's "same lock that will later pin remote-dependency SHAs" is reconciled as a *possible future convergence* in the in-repo-package case, not a Phase-0 unification. **Flagged for Louis at Checkpoint A** — the one place I depart from the plan's stated proposal. |
| D5 | Promoted shape for string-described concepts | SETTLED | A string-described concept `R = "<text>"` promotes to `ConceptBlueprint(description="<text>")` with `structure` and `refines` both absent — a faithful, minimal promotion (the string form is exactly shorthand for a description-only concept). It stays **structureless**; whether a structureless concept is opaque or implicitly `Text`-like is a resolution/emission detail the projection surfaces as *imprecision* (a caveat / TODO), never a normalization-time guess. `source` carries over from `source_map`. |
| D6 | Normalized crate built post-validation (loaded Library), transport crate path reconciled later | SETTLED | **Accept.** The normalized crate is emitted from the loaded **and validated** Library (post-`validate_library()`), so the artifact carries the validation verdict implicitly ("built only from a valid library"). The existing pre-validation `LibraryCrateFactory.make_from_blueprints` transport path stays for Temporal until reconciled (Phase 1+). |
| D7 | Where `tsc --strict` / pyright gates run | SETTLED | **Pyright in pipelex, tsc in conformance** (Louis, B1). The pyright gate on emitted Python lives in pipelex tests (toolchain already present); the `tsc --strict` gate on emitted TS lives in `conformance/`, the cross-repo harness that already carries a node toolchain. Split by toolchain availability. |
| D8 | `mthds-starter-js` conversion in Phase 2 or deferred | OPEN (settle at C), leaning DEFER | Louis chose "convert one starter as a proof" (`pipelex-starter-python`) at Checkpoint C1, so both JS starters (`pipelex-starter-js`, `mthds-starter-js`) are deferred to post-release by default; confirm the formal D8 defer at Checkpoint C. |
| D10 | ts-zod field keys: camelCase (with a wire-mapping binder) or wire-native snake_case | PROPOSED (wire-native) | **Wire-native snake_case.** The Checkpoint-B cold review found (confirmed) that a camelCase-keyed schema + a *generic* deep snake↔camel remapping binder **silently corrupts arbitrary keys** inside any `z.record()` / `z.unknown()` value — e.g. `parseJSON` over `native.JSON`'s `json_obj` map renames the caller's actual data keys, because a blind key remap can't tell a schema-declared field key from data. Emitting keys wire-native (the crate's snake_case names verbatim) makes a schema validate the wire directly, removes the remap layer entirely, and collapses the binder to a correct `Schema.parse`. Cost: the inferred TS types carry snake_case keys (departs from a camelCase-TS convention). If camelCase ergonomics are later wanted they must ride a **schema-aware** transform (walk the Zod shape, remap only `ZodObject` keys), never a generic key remap — a deliberate, conformance-tested future task, not a Phase-1 default. **Flag for Louis at Checkpoint B.** The `docs/specs/pipelex-codegen.md` "Name derivation rules" (workspace root) still says camelCase — reconcile there when D10 settles. |
| D9 | Re-point `pipelex build structures` onto the codegen engine now, or defer | PROPOSED (defer to Phase 2) | **Defer.** `build structures` emits **one file per concept** with **always-domain-qualified** class names + module-path wiring; the `types --target python-structures` engine emits a **single `structures.py`** with the spec's **bare-when-unique** naming. Re-pointing now would silently change `build structures`' output shape and names — violating the 1.5 "behavior preserved" requirement — and the naming reconciliation touches `concept_factory` runtime embedding, already deferred to Phase-2 starter conversion by the 1.4 divergence note. So `codegen types` is the canonical engine surface; `build structures` keeps its generator until Phase 2. `build inputs` needs no such deferral — it already renders through the same `input_renderer` engine as `codegen inputs`. Flag for Louis at Checkpoint B. |

## Checkpoint notes

*(append-only; one block per checkpoint: what was verified, review findings applied/deferred/rejected, deviations reconciled, SHAs)*

### CHECKPOINT A — 2026-07-09 — contracts reviewed and settled before engine code

**Branches (user pre-created fresh ones):** mthds `feature/Codegen`, conformance `feature/Codegen`, workspace-root docs/specs on `feature/Follow-ups` (holds the north-star drafts too), pipelex `feature/Devex-codegen`.

**Delivered.** 0.1 `mthds/docs/spec/library-crate.md` (+ mkdocs nav ×2 + `[Unreleased]` changelog). 0.2 `docs/specs/pipelex-codegen.md` + `command-surface-map.md` (Codegen/resolve section + Go-deeper row) + README table row. 0.3 four skip-gated conformance skeletons (`tests/pipelex/test_resolve.py`, `test_codegen.py`, `test_crate_shape.py`; `tests/pipelex_api/test_codegen_routes.py`) each pinning a `pipelex-codegen.md` anchor with a matching `> Verified by:`; `test_data.py` documents the forthcoming resolve/codegen subcommands without adding them to the live `--help` CLISpec. 0.4 D1–D6 recorded PROPOSED with rationale.

**Verified (gates green).** conformance `make agent-check` = ruff + pyright (0) + mypy (0) + check-spec-links (OK) + fixture-drift (OK); the 11 skeleton tests collect and skip with phase-named reasons. mthds `mkdocs build --strict` builds (new page in nav, all cross-refs resolve). **pipelex source untouched in Phase 0** (only `TODOS.md`, a markdown tracker) — so its `agent-test` was not run; it runs for real in Phase 1.

**`/code-review` fan-out** — one cold Sonnet-5 reviewer per touched repo (mthds b1f60c1, workspace-root 3458516, conformance 02ce7eb), no inherited plan/north-star context, high effort, anti-over-engineering. Triage:

- **Applied (clean-solid), mthds** (fix commit `9104ea6`): added a Specification-Status note flagging the normalization pass / TOML encoding / full fingerprint scope as the forward contract (the spec read as present-tense reality for behavior `LibraryCrate` does not yet do); fingerprint canonicalization now defers to **RFC 8785 (JCS)** (the old "no insignificant whitespace" wording didn't match the reference `json.dumps` and left numeric formatting open — a real cross-impl byte-agreement gap); resolved the native-concept self-contradiction by **materializing referenced natives into `concepts`** + adding an `mthds_version` stamp member; distinguished the project-local `.mthds/methods/<name>/` cache from the global `~/.mthds/packages/…` VCS cache (was silently inconsistent with sibling specs); documented dual provenance (`source_map` + per-object `source`, both excluded from the hash); stated the domain-metadata conflict rule; required TOML dotted-key quoting; softened the TOML "directly runnable" claim to name the loader accommodation.
- **Applied (clean-solid), workspace-root** (fix commit `50772e6`): corrected the **false claim** that `/v1/build/*` already share the 200+`is_valid` discipline (they return bare JSON / a retired `success` bool + 422 — re-pointing is a breaking change, now labelled so); reconciled phase tags (`codegen check` = Phase 2, `codegen diff` = Phase 4, not Phase 1) and narrowed the CLI `> Verified by:` to only the Phase-1 surface the skeleton covers; fixed the `build output`/`build runner` re-point asymmetry; corrected the `InputShaper` description (it hydrates caller inputs, doesn't render templates) + added its source path; "Owner repo"→"Owner repos".
- **Applied (clean-solid), conformance** (fix commit `d42cadb`): the toml/json fingerprint test now actually parses both and asserts equality (was asserting nothing); `test_crate_shape` + `test_codegen` now **seed a bundle** (were running against an empty `tmp_path`, making assertions vacuous or exit-2); crate-shape assertions strengthened (string-concept promotion + `native.Text` materialization); dropped the `codegen check`/`diff` test from the Phase-1 module (wrong phase); noted de-skeletoning must add the hermetic env fixtures.
- **Deferred** → `wip/devx/deferred-checkpoint-a-items.md`: **D-A1** whether the TOML crate is genuinely loadable as a bundle set and what loader accommodation `load_from_crate` needs (Phase 1 design question); **D-A2** whether Phase 1 widens the transport-crate fingerprint alongside the normalized one (D6 says the transport path stays until reconciled).
- **Rejected (one line each):** "cut the TOML encoding as over-engineering" — TOML is a deliberate north-star requirement (human-diffable, committable crates for semantic diffing), not speculative; kept with the forward-contract disclaimer. "D4 is asserted as settled but the log says open" — intentional: PROPOSED decisions are built-to and flagged for Louis (this is the flag); the lock section already carries an `<!-- unverified -->` noting D4 is a decision. Minor nits not applied: native-list ordering (aligned anyway), `main_pipe` overloaded-term sentence (left — the units table already disambiguates), route-skeleton inline `_BUNDLE` vs shared fixture (acceptable for a Phase-3 skeleton).

**For Louis (confirm/override at or before Phase 1):** D1–D6 PROPOSED → SETTLED, especially **D4** (sibling `codegen.lock` vs the plan's "one lock, two sections"). Nothing pushed; no PRs opened.

### CHECKPOINT B1 — 2026-07-09 — resolver landed (mid-phase)

**Verified.** pipelex `make agent-check` (ruff + pyright 0 + mypy 0 + check-keyword-only + plxt) and `make agent-test` (full suite) both PASS, re-run after the fixes below. Only `pipelex/` was touched this phase (conformance/mthds/workspace-root docs unchanged except the north-star + deferred docs, which carry no gate beyond markdown). Working tree clean.

**Decisions settled with Louis (all now SETTLED in the Decision log):** D1 (naming), D2 (fingerprint scope), D3 (one spec file), D4 (**sibling `codegen.lock`** — Louis confirmed the divergence from the plan's "one lock, two sections"), D5 (string-concept promotion), D6 (post-validation crate build), **D7 (pyright in pipelex, tsc in conformance)**.

**`/code-review` fan-out** — one cold Sonnet-5 reviewer on `1a7f9fe42..HEAD` (the Phase-1 code commit + tracker), no inherited plan/north-star context, high effort, anti-over-engineering. Reviewer independently confirmed the `generator.py` refactor preserves runtime behavior (traced every branch + re-ran the affected suites) and the dead-path deletion is clean. Triage:

- **Applied (clean-solid), pipelex** (this B1 closeout commit): **F5** — `resolve_cmd` now catches `PipeLibraryError` alongside `LibraryLoadingError` (a `LibraryError` sibling, not a subclass), so a duplicate-pipe-across-bundles conflict maps to the documented exit 1 instead of an uncaught traceback; `CrateNormalizationError` (internal invariant) is deliberately left to surface. Added `test_pipe_conflict_is_negative_verdict_exit_1`. **F4** — `crate_normalization.py` module docstring now discloses the deferred normalization steps (spec step 5 = defaults/multiplicity materialization; cross-package fold-in), mirroring the standard spec's own "Specification Status" callout, instead of reading as a complete 5-step pass.
- **Deferred** → `wip/devx/deferred-checkpoint-b1-items.md` (**Louis: defer both high-sev to before Checkpoint B**): **B1-1** Python-backed `structure="<ClassName>"` concepts emit an opaque name into the "self-contained" crate — **Louis' steer: MTHDS is the single source of truth, so do NOT reverse-engineer Python classes (introspection is off the table); discuss with vision, lean toward acknowledge-and-disable**; **B1-2** flattening a concept that refines a native drops the native base class on crate round-trip (recommend: don't flatten native bases, keep `refines: native.X`, reconcile spec step 3); **B1-3** imprecision markers are write-only until the 1.4 emitters surface them; **B1-4** explicit defaults/multiplicity materialization (spec step 5); **B1-5** cross-package fold-in / fixture 1; **B1-6** conformance crate-shape de-gate (cross-repo, release-gated); **B1-7** the same CLI error-handling gap still exists in `validate` (pre-existing, not introduced). D-A1 + D-A2 (Checkpoint A) reconciled as **RESOLVED by Phase 1** (loader accepts the flat crate shape; only the normalized fingerprint widened).
- **Rejected (one line):** the reviewer's "restore the loud crash on malformed `item_type`/`value_type`" (Finding 3a) — the resolved-field layer's `ANY` + imprecision-marker is the *intended* 1.1 design ("never a guess"); the old crash was incidental uncompilable output, not a designed validation. Superseded, not a regression.

**Nothing pushed; no PRs opened.**

### CHECKPOINT B — 2026-07-10 — engine + emitters landed with gates green

**Delivered (Phase 1.5–1.7).** The `pipelex codegen` command family (`types --target …`, `inputs [--pipe …]`) over the landed `emit_types`/`input_renderer` engine; a shared crate-loading helper (`crate_loading.py`) that centralizes the resolve/validate exit-code contract (`resolve_cmd` refactored onto it). The ts-zod purity split completed with a `binder.ts` (typed `parse<T>`/`serialize<T>` per concept). **B1-2 resolved** (native-backed refinement bases keep `refines`, round-trip preserved; mthds spec step 3 reconciled). Quality gates: strict-pyright-on-emitted-Python (D7), python serialize→parse round-trip, resolve→emit e2e over the multi-bundle fixture (fixture 2, feeds every emitter). Docs: `docs/under-the-hood/codegen-projections.md` (CLI + binder + refinement) + `[Unreleased]` changelog.

**Verified (gates green).** pipelex `make agent-check` (ruff + pyright 0 + mypy 0 + check-keyword-only + plxt) and full `make agent-test` both PASS; mthds `mkdocs build --strict` builds. Touched repos: pipelex (`feature/Devex-codegen`), mthds (`feature/Codegen`, spec step-3 prose), workspace-root (`feature/Follow-ups`, deferred doc — WIP tracking, no gate).

**`/code-review` fan-out** — one cold Sonnet-5 reviewer per code-touched repo (pipelex on `db8458ea5..a1f73cc46`; mthds on `9104ea6..c077af9`), no inherited plan/north-star context, high effort, anti-over-engineering. (Workspace-root's only change is the WIP deferred doc — not code-reviewed.) Triage:

- **Applied (clean-solid), pipelex — Finding 1 (Critical, confirmed):** the ts binder's generic deep `mapKeysDeep` snake↔camel transform **silently corrupted arbitrary keys** inside any `z.record()`/`z.unknown()` value (reviewer reproduced it on `native.JSON`'s `json_obj` map — `parseJSON` renamed the caller's real data keys). **Fix (D10): emit wire-native snake_case zod keys** — the schema validates the wire directly, the remap layer is deleted, and the binder collapses to a correct `Schema.parse`. Net *reduction* in generated-code complexity; the corruption class is impossible now. Tests updated (keys are snake, binder has no `mapKeysDeep`); doc + D10 flag added.
- **Applied (clean-solid), pipelex — Finding 2 (coverage gap):** B1-2's new native-backed branch had no direct normalization-layer test (the only refines-native fixture used structureless `Image`, which the *old* code already handled). Added `test_refinement_with_structured_native_base_keeps_refines` (a `refines Text` concept keeps `refines == native.Text`, structure `None`) + `test_multi_hop_native_backed_chain_keeps_refines` (C→B→native) + a ts-zod `test_refines_native_renders_a_lazy_base_schema`.
- **Applied (clean-solid), mthds — Findings 1+2:** the Sufficiency-Guarantee recap ("refinement is flattened — no chain-walking needed") contradicted the new native exception → reworded to "structured refinement is flattened; native-backed refinement resolves via a single in-crate `native.<Code>` lookup." Tightened the "MAY be retained for provenance" clause (it implied a `refines`+`structure` state the concept model forbids) to say a flattened concept carries `structure` and no `refines`, provenance living in the source map.
- **Rejected / not-applied (one line each):** reviewer's minor `toCamel`/`toSnake` double-underscore-asymmetry nit — moot, the whole remap layer was deleted. mthds reviewer's run-on-sentence readability nit on the new step-3 paragraph — left; it is correct and the density is acceptable.

**For Louis (confirm/override at or before Phase 2):** **D9** (defer `build structures` engine re-point to Phase 2 — behavior-preservation impossible vs. the divergent naming) and **D10** (ts-zod wire-native snake keys vs. camelCase-with-schema-aware-binder — driven by the confirmed corruption finding). **B1-1** normalization-layer policy (Python-class-backed concepts — emitter floor done; hard-error-vs-disable + single-source-of-truth discussion still pending). **B1-5** cross-package fold-in reframed as a Phase-3 pipe-graph item (the canonical cross-package ref-naming/collision scheme is the decision to make when it lands).

**Nothing pushed; no PRs opened.**

### CHECKPOINT C1 — 2026-07-10 — codegen trust chain landed (mid-Phase-2)

**Delivered (Phase 2.1).** The full codegen trust chain in pipelex: **stamp** headers (`pipelex/codegen/stamp.py` — `CodegenStamp`, `apply_stamp`/`parse_stamped`, `STAMPABLE_SUFFIXES`, `comment_prefix_for`; fenced `>>> pipelex-codegen-stamp >>>` block, content hash over the body below it, `CodegenKind` axis added to `emitters/target.py`); a sibling **`codegen.lock`** (`lock.py` — TOML, path+body-hash+crate-fingerprint+engine-version, sorted); the **offline `codegen check`** (`check.py` + `cli/commands/codegen/check_cmd.py` — pure hashing, no engine/network/API-key, drift categories missing/modified/hand-edited/orphan, exit 0/1/2); the **idempotent write-if-changed + stale-file-pruning** emission layer (`emission.py`), which `codegen types` now writes through. Docs: new "trust chain" section in `docs/under-the-hood/codegen-projections.md`; `[Unreleased]` changelog (+ fixed a stale pre-D10 camelCase-binder line in the existing codegen entry). Input templates (`codegen inputs`) deliberately NOT stamped/locked (user-editable scaffolds).

**Verified (gates green).** pipelex `make agent-check` (ruff + pyright 0 + mypy 0 + kw-only + plxt) and full `make agent-test` PASS. **End-to-end against the real binary** (`.venv/bin/pipelex`): `codegen types --target python-pydantic` → stamped `models.py` + `codegen.lock`; re-run → "Unchanged" (write-if-changed); hand-edit → `check` exit 1 (`hand-edited`); clean → exit 0; no-lock dir → exit 2; python→ts target switch in the same dir → stale `models.py` pruned + tree stays clean. Only `pipelex/` touched this checkpoint.

**`/code-review` fan-out** — one cold Sonnet-5 reviewer on `d594d2511..e70c7eebc` (the Phase 2.1 commit), no inherited plan/north-star context, high effort, anti-over-engineering. Triage (fixes in `9d4fc59d6`):

- **Applied (Critical, confirmed) — F1:** `codegen check` crashed with a raw `UnicodeDecodeError` on any non-UTF-8 file — the exact drift it exists to catch (a mangled hand-edit) and any incidental non-UTF-8 file the orphan scan read. Fix: a non-UTF-8 *tracked* artifact → reported `hand-edited`; a non-UTF-8 *stray* file → skipped; a non-UTF-8 `codegen.lock` → clean `CodegenLockError` (read moved inside the guarded block; `UnicodeDecodeError` is a `ValueError` subclass). Tests added.
- **Applied (Important) — F2:** the orphan scan did an unrestricted `root.rglob("*")`; a `codegen check` at a project root read every file under `.venv`/`node_modules`/etc. Fix: `_iter_stampable_files` prunes well-known vendor/VCS/cache dirs. Tests added (vendor pruning + nested-orphan still detected).
- **Applied (clean-solid) — F3:** two duplicate stampable-suffix lists collapsed to one source of truth (`STAMPABLE_SUFFIXES` exported from `stamp.py`, derived in `check.py`).
- **Rejected (one line) — F4:** `pipe_ref` plumbed through the stamp but unused today — kept: the stamp format is *spec'd* (`docs/specs/pipelex-codegen.md`) to carry `pipe_ref` for per-pipe artifacts; it is cheap, round-trip tested, and populated when per-pipe artifacts get stamped in a later phase (not speculative — a documented optional field).
- **What checked out clean (reviewer's own words):** stamp round-trip + tamper detection sound; `_prune_delisted` never deletes a file that doesn't carry our stamp (even against a path-traversal lock entry); write ordering idempotent across interrupted runs.

**Deviation surfaced (flag for Louis).** Phase 2.2's DoD "starter CI runs the offline check" is **release-gated**: the starters pin `pipelex-sdk`/`pipelex-tools`, NOT the `pipelex` runtime that hosts `codegen`, and no published pipelex ships `codegen` (0.38.0 has none). Louis chose **"convert one starter as a proof"** → convert `pipelex-starter-python` now (generate + commit the client + smoke test + make targets against this editable pipelex), leave live-CI wiring as the release-gated tail; defer both JS starters + D8. Reconciled into the 2.2 task list above.

**Nothing pushed; no PRs opened.**
