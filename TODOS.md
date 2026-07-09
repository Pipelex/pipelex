# DevEx North Star — Implementation Plan (TODOS)

**Source of truth for the vision:** [`wip/devx/devex-north-star.md`](../wip/devx/devex-north-star.md) (workspace root). This file is the execution tracker: tasks, checkpoints, decisions, and cold-start state. When the two disagree on *what to build*, the north star wins; when they disagree on *current status*, this file wins.

**Working branches (actual, as of Checkpoint A):** pipelex `feature/Devex-codegen` in this worktree (`_codegen/`); mthds `feature/Codegen`; conformance `feature/Codegen`; workspace-root (`docs/specs/` + `wip/devx/`) on `feature/Follow-ups` (which also carries the north-star drafts). Louis pre-created the `feature/Codegen` branches. Phases 0–2 touch: `mthds/`, workspace-root, `conformance/`, `pipelex` (this worktree), then the starters. Phases 3+ fan out to `pipelex-api/`, `mthds-js/`, `pipelex-sdk-js/`, and hosted repos.

## Status block (update at every checkpoint)

- **Current phase:** Phase 1 — **1.1, 1.2, 1.3 DONE + COMMITTED; CHECKPOINT B1 ✅ PASSED 2026-07-09.** Resolver + normalized-crate + encodings + `pipelex resolve` CLI landed with tests; cold `/code-review` triaged (2 fixes applied, 2 high-sev tradeoffs + follow-ups deferred, 1 rejected); D1–D7 SETTLED with Louis; `make agent-check` + `make agent-test` PASS (re-run post-fix).
- **Next action:** Phase 1 continues at **1.4 (emitters)** — `python-structures` (today's presentation over resolved fields), `python-pydantic`, and the new `ts-zod` emitter; then **1.5** (`pipelex codegen` CLI family + `build inputs`/`build structures` re-point), **1.6** (both fixtures), **1.7** (quality gates: pyright in pipelex, tsc in conformance per D7). **Before Checkpoint B, resolve the deferred items in `wip/devx/deferred-checkpoint-b1-items.md`:** B1-1 (Python-backed `structure="<ClassName>"` — **discuss with Louis first**, lean acknowledge-and-disable, NOT introspection), B1-2 (stop flattening native refinement bases — round-trip identity), B1-5 (cross-package fold-in / fixture 1). Cold-start reads that doc.
- **Last checkpoint passed:** **Checkpoint B1** — resolver landed (mid-phase); cold review triaged, decisions D1–D7 settled, gates green, deferrals documented.
- **Last commit(s):** mthds `feature/Codegen` `9104ea6` · workspace-root `feature/Follow-ups` — Checkpoint-A `50772e6`, then **B1 docs commit `5fd7ed1`** (north-star + deferred-checkpoint-{a,b1} docs) · conformance `feature/Codegen` `d42cadb` · pipelex `feature/Devex-codegen` — Checkpoint-A `1a7f9fe42`, **Phase-1 `64c7c155c`** (1.1–1.3), tracker-pin `dd26ad8b4`, then **B1 closeout commit `<pinned below>`** (F4/F5 fixes + test + tracker). **Review diff for the NEXT checkpoint (B) = `dd26ad8b4..<B1-closeout>..HEAD`.** **None pushed.**
- **Open decisions:** D1–D7 **SETTLED** (see Decision log). D8 OPEN (settle at C — `mthds-starter-js` conversion).
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

### 1.4 Emitters

- [ ] `python-structures` emitter: today's `StructureGenerator` Python presentation nearly verbatim, over resolved fields; generated-file header's copy-this-file-to-customize guidance replaced by the extension-file story (subclassing).
- [ ] `python-pydantic` emitter: same minus pipelex imports and the `StructuredContent` base; plus parse/serialize helpers per pipe.
- [ ] `ts-zod` emitter (new): Zod schemas + inferred types, camelCase models with bidirectional wire-name mapping per the 0.2 naming spec, parse/serialize helpers; purity split (pure types file importing only zod + thin binder file for SDK integration).
- [ ] Docstrings/JSDoc in all emitters embed affordances: runnable compact-input example (from `input_renderer`) + each field's wire name.
- [ ] Generated code is never edited: extension-file mechanism designed and documented (Python subclassing, TS declaration merging), surviving regeneration.

### 1.5 `pipelex codegen` CLI family

- [ ] `codegen types --target ts-zod|python-pydantic|python-structures` (concept set); `codegen inputs [--pipe <ref>]` re-surfacing `input_renderer`/`InputShaper` over the selected pipe (compact default, explicit opt-in — Smart Inputs policy unchanged); output-side artifacts fed by `pipe_io_contracts` + `output_renderer`.
- [ ] `pipelex build inputs` / `pipelex build structures` re-pointed to the engine (thin aliases, behavior preserved); agent-CLI mirrors updated (`pipelex/cli/agent_cli/commands/`).
- [ ] Two-axis flags exactly as spec'd; structured verdict output per workspace meta-rule.

### 1.6 Fixtures (vendored into pipelex tests, no cookbook dependency)

- [ ] Local-cache fixture: `extract_generic`-shaped — one bundle with a cross-package ref + ancestor `.mthds/methods/documents/` vendored copy (from `pipelex-cookbook`).
- [ ] Multi-bundle closure fixture: recursive-build style — a pipe whose sub-pipes and concepts spread across sibling bundles (authored fresh; no existing case combines this with the cache).
- [ ] Both fixtures resolve end-to-end through `pipelex resolve` and feed every emitter test.

### 1.7 Quality gates from day one

- [ ] Corpus of representative bundles (seeded from the cookbook) whose emitted artifacts must pass `tsc --strict` and strict pyright (location per D7).
- [ ] Serialize→parse round-trip tests (inputs template → serialize → parse via generated helpers).
- [ ] Golden tests assert compile-and-parse behavior, not byte equality — templates stay free to improve.

### CHECKPOINT B — engine and emitters landed with gates green

- [ ] Full checkpoint protocol executed (repos: `pipelex`, possibly `conformance`; independent `/code-review` fan-out; STOP).
- [ ] Definition of done: all Phase 1 boxes ticked; both fixtures pass every emitter + gate; runtime structures codegen fully absorbed (old standalone path gone, `concept_factory` runtime unchanged); docs (`docs/` in pipelex) describe the engine, the crate, and the extension-file story; `[Unreleased]` changelog entry.

---

## Phase 2 — Trust chain and proof by starters

### 2.1 Trust chain (in `pipelex`)

- [ ] Stamp writer/parser per the 0.2 spec (every generated file self-describes: crate fingerprint, engine version, projection, options, content hash).
- [ ] Lock per D4 (artifact set + hashes).
- [ ] `pipelex codegen check` — offline, pure hashing, no engine/network; plus the documented short-CI-script recipe proving independent implementability.
- [ ] Write-if-changed everywhere (no mtime churn; clean diffs; watch-mode ready).
- [ ] Conformance tests de-skeleton for check/stamp/lock surfaces.

### 2.2 Starters convert (definition-of-done gate for the core DX)

- [ ] `pipelex-starter-python`: delete hand-written models in `piper/examples/*.py`; wire generated python-pydantic client; `codegen check` in its CI; generated smoke test (dry-run with template inputs) included.
- [ ] `pipelex-starter-js`: delete `src/types/*Pipeline.ts`; wire generated ts-zod client; check in CI; generated smoke test.
- [ ] `mthds-starter-js`: same treatment, or explicitly deferred with rationale — decide at Checkpoint C (**D8**).
- [ ] The SDK inversion boundary honored: nothing method-shaped remains hand-written in the starters; SDKs (`@pipelex/sdk`, `mthds`) untouched except plumbing hooks if strictly needed.

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
| D8 | `mthds-starter-js` conversion in Phase 2 or deferred | OPEN (settle at C) | — |

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
