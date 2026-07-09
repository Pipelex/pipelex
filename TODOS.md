# DevEx North Star — Implementation Plan (TODOS)

**Source of truth for the vision:** [`wip/devx/devex-north-star.md`](../wip/devx/devex-north-star.md) (workspace root). This file is the execution tracker: tasks, checkpoints, decisions, and cold-start state. When the two disagree on *what to build*, the north star wins; when they disagree on *current status*, this file wins.

**Working branch (pipelex):** `feature/Devex-codegen` in this worktree (`_codegen/`). Other repos get sibling branches named `feature/devex-codegen` when first touched. Phases 0–2 touch: `mthds/`, workspace-root repo (`docs/specs/`), `conformance/`, `pipelex` (this worktree), then the starters. Phases 3+ fan out to `pipelex-api/`, `mthds-js/`, `pipelex-sdk-js/`, and hosted repos.

## Status block (update at every checkpoint)

- **Current phase:** Phase 0 — not started.
- **Next action:** start 0.1 — draft `mthds/docs/spec/library-crate.md` (branch `feature/devex-codegen` in `mthds/`), proposing answers to D1/D2/D5/D6 in the Decision log as you go.
- **Last checkpoint passed:** none.
- **Last commit(s):** pipelex `76477238b` (branch point, clean).
- **Open decisions:** see "Decision log" below — all Phase 0 decisions open.
- **Deviations from north star found so far:** (1) The cookbook `extract_generic` case is *single-bundle* with the vendored dependency cache at the cookbook **repo root** (`pipelex-cookbook/.mthds/methods/documents/`), not per-case — the Phase 1 fixture must replicate that shape (bundle + ancestor `.mthds/methods/` cache) and a *separate* multi-bundle fixture must be authored, since no existing case exercises both at once. (2) Today's crate is built from **pre-validation blueprints** (`LibraryCrateFactory.make_from_blueprints`), while the north star requires the normalized crate be "built only from a valid library" — Phase 1 moves normalized-crate emission downstream of library load + validation.

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

- [ ] New formal spec `mthds/docs/spec/library-crate.md`, beside `manifest-format.md` and `lock-format.md`, covering: the three units (bundle / library / pipe) and the resolution rule (resolve a library; project types over its concept set; project runnables per pipe).
- [ ] Closure-assembly rules: working bundles + local method cache (`.mthds/methods/`, ancestor-walk discovery), cross-package refs, alignment with `namespace-resolution.md` and `docs/implementers/package-loading.md` §"Library Assembly" (cross-reference, don't duplicate).
- [ ] Normalization pass, precisely: merge bundles; fully qualify **every** ref (dict keys AND in-body refs: pipe steps, inputs/output concept refs, `refines`); flatten refinement into effective structures; expand native concepts pinned to the spec version; materialize defaults and multiplicity; promote string-described concepts to explicit blueprint form; built only from a *valid* library (the artifact carries the verdict implicitly).
- [ ] Fingerprint definition: SHA-256 over canonical JSON of normalized content; specify exact canonicalization (sorted keys, ascii, sorted refs — today's `compute_fingerprint_from_content` is the seed) and the hash **scope** decision (D2 below).
- [ ] Both encodings: JSON (machine-native, keyed to the published `mthds_schema.json` model) and TOML (human-diffable, directly runnable); canonical serialization rules for each so independent implementations byte-agree.
- [ ] The sufficiency guarantee, stated as a testable contract: a consumer with only a JSON/TOML parser and one normalized crate can emit correct types / render a correct form / register a correct tool — no loader, no namespace resolution, no hardcoded natives.
- [ ] Wire into `mkdocs.yml` nav; add narrative pointer from `docs/packages/` if appropriate; `[Unreleased]` changelog entry.

### 0.2 Spec the codegen surface in `docs/specs/` (workspace-root repo)

- [ ] New spec (proposed: `docs/specs/pipelex-codegen.md`; split later only if it bloats — D3) with front matter (`id:`, `sources:`) and per-surface `> Verified by:` / `<!-- unverified: -->` markers, covering:
  - [ ] **Stamp header format** — fields: source crate fingerprint, engine version, projection, options, generated-content hash; comment syntax per emitted language; self-describing requirement.
  - [ ] **Lock format** — artifact-set manifest with hashes (catches deleted-concept stale files); named "lock" not "manifest"; relationship to `methods.lock` per decision D4.
  - [ ] **Offline check algorithm** — pure hashing, no network / API key / engine; spec'd precisely enough for independent implementation (CLI, SDK, short CI script); exit/verdict semantics.
  - [ ] **CLI surface** — `pipelex resolve` (emit crate, JSON|TOML); `pipelex codegen types|inputs|docs|tools|tests --target <flavor> [--pipe <pipe_ref>]` (two explicit axes, no flat kind×format enum; `--pipe` defaults to `main_pipe`); `codegen check`; `codegen diff`; `build inputs`/`build structures` re-pointing as aliases. Verdict in structured output, never exit code (workspace meta-rule).
  - [ ] **Route envelopes** — codegen + resolve routes on `pipelex-api`: request accepts inline `files[]` (multi-bundle) *or* `method_ref`; response 200 discriminated on `is_valid` exactly like `/v1/validate`; request-shape errors (unknown projection/target) are 422 problem+json; resolution and type/schema projections flagged protocol capabilities (`x-mthds-protocol`), runtime-structures emission stays a Pipelex extension.
  - [ ] **Name-derivation rules** — slug → file/module/type spellings spec'd once for every consumer: TS camelCase with bidirectional wire snake↔camel mapping and wire names documented inline; Python stays snake_case; domain-qualified class naming (existing `make_qualified_structure_class_name` behavior is the seed).
- [ ] Update `docs/specs/command-surface-map.md` with the codegen/resolve chain.
- [ ] Update `docs/specs/README.md` table.

### 0.3 Conformance skeletons (`conformance/` repo)

Skeleton semantics (applies to all of Phase 0): a skeleton module asserts the spec'd envelope but is marked skip/xfail with a reason naming the phase that implements the surface (CLI surfaces → Phase 1, routes → Phase 3, check/stamp/lock → Phase 2); the implementing phase de-skeletons it. At Checkpoint A only `check-spec-links` must be green — no skeleton needs to pass.

- [ ] Skeleton test modules pinning the CLI envelopes: `tests/pipelex/test_resolve*.py`, `tests/pipelex/test_codegen*.py`, each with `pytestmark = pytest.mark.spec(...)` pointing at 0.2 anchors; extend the dir's `test_data.py` CLISpec.
- [ ] Skeleton module pinning the crate shape itself (normalized-crate JSON fixture asserted against the spec's structural promises: flat, fully qualified, no unexpanded natives, fingerprint present and recomputable).
- [ ] Skeleton modules for the route envelopes under `tests/pipelex_api/`.
- [ ] `make check-spec-links` green across the spec↔test pairs.

### 0.4 Decisions to settle before Checkpoint A (record answers in the Decision log)

- [ ] **D1 — crate spec naming**: "library crate" as the standard's term (neutral, no `pipelex_` wire fields) — confirm or rename once, before anything ships.
- [ ] **D2 — fingerprint scope**: today's hash covers concepts+pipes only; domains carry `system_prompt` and `main_pipe` which are semantic. Decide inclusion (proposal: include normalized domain metadata; exclude `source_map`).
- [ ] **D3 — one spec file or split** (CLI/stamps/lock/check vs routes vs naming). Proposal: one file, sectioned.
- [ ] **D4 — lock relationship**: extend `methods.lock` (north star hints "same lock that will later pin remote-dependency SHAs") vs sibling artifact lock. Proposal: one lock file, two sections; spec the codegen section now, dependency section already spec'd.
- [ ] **D5 — string-described concepts**: normalization promotes them to explicit `ConceptBlueprint` form — confirm the promoted shape.
- [ ] **D6 — crate build point**: normalized crate is emitted from the loaded+validated Library (post-`validate_library()`), not from raw blueprints; the existing pre-validation `make_from_blueprints` path stays for Temporal transport until reconciled. Confirm.

### CHECKPOINT A — contracts reviewed and settled before engine code

- [ ] Full checkpoint protocol executed (verify · commit · `/code-review` fan-out per touched repo: `mthds`, workspace-root, `conformance` · TODOS/north-star update · cold-start test · STOP).
- [ ] Definition of done: specs merged-ready on their branches; conformance skeletons exist and `check-spec-links` passes; every D1–D6 decision recorded with rationale.

---

## Phase 1 — Engine and first projections (in `pipelex`, this worktree)

A refactor around existing organs, not a rewrite. Genuinely new code: the normalization pass, the neutral resolved-field layer, the Zod/TS emitter.

### 1.1 Neutral resolved-field layer (extraction from `StructureGenerator`)

- [ ] Extract the semantic mapping (choices→literal, list/dict recursion, concept-ref resolution incl. natives, bare-ref promotion, `refines` base recovery, forward refs for cycles) into a neutral resolved-field model every emitter consumes (proposed home: `pipelex/codegen/resolved_fields.py`; today it emits Python type strings — the extraction makes it return language-neutral resolved fields).
- [ ] Refactor `StructureGenerator` to consume the layer; runtime behavior via `concept_factory.py` unchanged (existing suite is the harness).
- [ ] Delete the dead legacy dict-based path (`_generate_field`, `_get_python_type`, `enum_definitions`).
- [ ] Where the source is imprecise (untyped `list`, structureless concept): resolved field carries an explicit imprecision marker emitters must surface (TODO comment / card caveat), never a guess.

### 1.2 Normalization pass → normalized crate

- [ ] Implement the spec'd normalization (proposed home: `pipelex/libraries/crate_normalization.py`), producing a normalized `LibraryCrate` from a loaded, validated Library (per D6): in-body ref qualification, refinement flattening into effective structures, native expansion pinned to spec version, defaults+multiplicity materialization, string-concept promotion (D5).
- [ ] Fingerprint per D2 scope, reusing the canonical-JSON hashing seed; normalized fingerprint is THE semantic hash downstream.
- [ ] Round-trip guarantee tests: normalized crate loads via `load_from_crate` and validates; normalizing twice is a fixed point (idempotent).

### 1.3 Crate encodings + `pipelex resolve` CLI

- [ ] JSON and TOML encodings per the 0.1 canonical-serialization rules.
- [ ] New `pipelex resolve` command (new family under `pipelex/cli/commands/`): assembles the closure (working bundles + `.mthds/methods/` cache) and emits the normalized crate; format flag per spec.
- [ ] TOML-encoded crate is directly runnable (feed it back to `pipelex run`/`validate` as a bundle set) — test it.

### CHECKPOINT B1 — resolver landed (mid-phase)

- [ ] Full checkpoint protocol executed (repos: `pipelex`; `/code-review` fan-out on the diff since Checkpoint A; update docs; STOP).
- [ ] Definition of done: 1.1–1.3 complete; `pipelex resolve` emits a spec-conformant crate for both fixtures (see 1.7); conformance crate-shape skeleton now passes against real output; gates green.
- [ ] Settle **D7 — where compile gates run**: emitted-TS `tsc --strict` gate needs a node toolchain — proposal: pyright gate on emitted Python lives in pipelex tests; the tsc gate lives in `conformance/` (cross-repo harness already exists). Record the decision.

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
| D1 | Crate spec naming in the standard | OPEN | — |
| D2 | Fingerprint hash scope (domains/system_prompt/main_pipe in or out) | OPEN | — |
| D3 | One codegen spec file vs split | OPEN | proposal: one, sectioned |
| D4 | Codegen lock: extend `methods.lock` vs sibling | OPEN | proposal: one lock, two sections |
| D5 | Promoted shape for string-described concepts | OPEN | — |
| D6 | Normalized crate built post-validation (loaded Library), transport crate path reconciled later | OPEN | — |
| D7 | Where `tsc --strict` / pyright gates run | OPEN (settle at B1) | proposal: pyright in pipelex, tsc in conformance |
| D8 | `mthds-starter-js` conversion in Phase 2 or deferred | OPEN (settle at C) | — |

## Checkpoint notes

*(append-only; one block per checkpoint: what was verified, review findings applied/deferred/rejected, deviations reconciled, SHAs)*
