# Keyword-Only Arguments Refactor — Plan & Tracker

Make non-subject function parameters **keyword-only** across the `pipelex/` runtime, so call sites are self-documenting (a dev or SWE agent can read a call and know what each argument means without opening the definition). Build an enforcement guard *first*, then burn down the existing code package-by-package behind it.

This file is the master tracker. **Status: COMPLETE — all phases done (Checkpoint G reached 2026-06-14).** The convention has been promoted to its permanent home at [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md) and summarized as a standing rule in the contributor `CLAUDE.md` / `AGENTS.md`; the `wip/keyword-only-args/` track folder has been retired. This tracker remains as the historical record of the refactor (per-checkpoint cold-start snapshots reference paths as they were at the time). Use the checkboxes to track progress; **do not skip the mandatory checkpoints** — each is a hard stop where the running agent must verify, snapshot context, and hand off cleanly.

## Locked decisions

- **Scope:** this repo only, **source under `pipelex/`** — not `tests/` (tests call internals positionally on purpose; revisit later if desired).
- **Enforcement model:** build a custom AST guard **first**, wire it into the `make check` family, and let it drive the refactor red→green. Not a one-shot cleanup — the guard prevents drift.
- **First (subject) parameter stays flexible:** the shape is `def f(subject, *, opt1, opt2)`. The subject can be passed positionally or by name; everything after the `*` is keyword-only. We do **not** use positional-only `/`.

## The convention (summary — full spec written in Phase 1)

A function/method must mark parameters keyword-only (place a bare `*` before them) **except**:

- **Exception 1 — the subject.** The first non-`self`/`cls` parameter may remain positional-or-keyword when the function name designates it as the thing being acted upon (the Swift `_`-first-label idea), e.g. `parse_blueprint(blueprint, *, strict=...)`, `find_pipe_by_code(code, *, domain=...)`.
- **Exception 2 — small symmetric/ordered tuples.** Functions whose parameters are a short, conventionally-ordered set read *better* positionally; forcing keywords is noise. E.g. `clamp(value, low, high)`, `Point(x, y)`, `replace(text, old, new)`, `lerp(a, b, t)`. These are exempt **entirely** and live on an explicit allowlist (no silent guessing).
- **Single-parameter functions** have nothing to enforce.

**Carve-outs (the guard skips these — we don't control their call convention):**

- Dunder/operator methods (`__init__`, `__eq__`, `__call__`, `__enter__`, …) — invoked positionally by the interpreter.
- Pydantic `@field_validator` / `@model_validator` / `@validator` functions — fixed signatures. (Model *construction* is already keyword-only, so models are not a target. For dataclasses, prefer `@dataclass(kw_only=True)` over a manual `*`.)
- Framework entrypoints called by name/position by the framework: Typer/click commands, FastAPI routes, **pytest fixtures**, and **Temporal** `@activity.defn` / `@workflow.run` / `@workflow.signal` / `@workflow.query` handlers.
- Methods overriding a base/Protocol/ABC signature — must stay Liskov-compatible with the parent. (AST can't resolve the base reliably; see the known limitation below — handled via the escape hatch + pyright.)

**Escape hatch:** a rare legitimate violation can be suppressed with an inline `# kw-only: ignore` comment on the `def` line (greppable, reviewable). Overuse is a smell.

## Why this is mostly a *call-site* refactor (and the main risk)

Adding `*` to a signature is the easy 5%. The moment `def f(a, *, b, c)` exists, every caller passing `b`/`c` positionally **breaks** — at type-check time and runtime. So ~90% of the diff is keywordizing call sites, which is also the actual value. Consequences baked into the plan:

- **pyright/mypy is the oracle.** Per-package loop: apply `*`, run `make agent-check`, fix every flagged call site to keyword form, then run targeted tests. Dynamic calls (`getattr`, `**kwargs` forwarding, `functools.partial`) won't be caught by the type checker — the test suite is the second net.
- **Burn down per-package, not big-bang.** A single cross-cutting change is unreviewable and a merge-conflict magnet (there are in-flight refactor branches). Each wave below is a self-contained working-tree diff the user reviews and pushes before the next phase starts (no PR per wave — see Branch & landing strategy).
- **Public API is downstream-breaking.** Top-level surfaces (`pipelex.py`, `hub.py`, anything imported by `pipelex-api`, `pipelex-worker`, `n8n-nodes-pipelex`, cookbook/starter) changing signature is a breaking change for those consumers. Allowed under our "no backward compatibility" rule, but must be called out in the changelog and handled in the last, most careful wave.

## Branch & landing strategy

- [x] Branch `refactor/Function-calling-1` created (off `refactor/Function-calling`) for this work.
- **No PR per wave/checkpoint.** The agent does **not** commit, stage, or open PRs. Each wave's changes are left **uncommitted and unstaged** in the working tree at its checkpoint. The user reviews the working tree and commits/pushes the changes themselves before cold-starting the next phase.
- Land each wave as a coherent, reviewable unit anyway: keep the working-tree diff scoped to one wave so the user's review and push stay clean.
- [x] Changelog entries go under the `[Unreleased]` section as waves land.

## Tooling approach

- **Guard:** Python `ast`-based `pipelex-dev` CLI command, walking `pipelex/` only (mirrors the existing `check_*_cmd.py` pattern; `--quiet` single-line mode for Make).
- **Baseline file:** the guard reads a committed baseline of *known* existing violations and fails only on **new, non-baselined** ones. This lets it be CI-blocking from day one while we burn down the backlog — each wave deletes its entries from the baseline. (Like a mypy/ruff baseline.) Final state: empty baseline.
- **Migration engine:** pyright/mypy reports broken call sites after each `*` is added. Optional accelerator: a `libcst` codemod to add `*` mechanically — but call-site keywordization stays type-checker-driven, since resolving the callee reliably needs scope/type info.

---

## CHECKPOINT PROTOCOL (read before every checkpoint)

At each `🛑 CHECKPOINT`, the running agent **must stop** and, before ending the session:

1. Run `make agent-check` and `make agent-test` — both must pass. Record the result.
2. Run the guard in report mode and record the **remaining baseline count per package** in `wip/keyword-only-args/state.md`.
3. Update this file's checkboxes and fill in the matching **Cold-start snapshot** block below with: what landed (files changed, left uncommitted in the working tree), current package position, decisions & edge cases hit this session, any deferred items, and the exact next action.
4. Update the doc but **leave everything uncommitted and unstaged** — including these doc updates. Do **not** commit, stage, or open a PR. The user reviews the whole working tree and commits/pushes before the next phase cold-starts. The next session must be able to resume from `wip/keyword-only-args/state.md` + this tracker alone, with zero lost context.

---

## Phase 1 — Build & validate the guard (test-first)

- [x] Create the track folder `wip/keyword-only-args/` with:
  - [x] `README.md` — track index (links convention + state + this tracker, lists the wave ordering).
  - [x] `convention.md` — the **full** canonical rule (corrected post-review to the enforced strict rule + the "all-keyword is allowed/encouraged" clarification).
  - [x] `state.md` — the running cold-start log (per-package baseline counts, decisions log, current position, deferred items, exact commands).
- [x] **Wrote tests first** (`tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd.py`): compliant code, each violation class, each exception, each carve-out, escape hatch, baseline behaviour. 28 tests, green.
- [x] Implemented `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py`:
  - [x] AST walk of `pipelex/`; flags any non-subject positional-or-keyword param not behind a bare `*`.
  - [x] Exception 1 (subject stays positional — a permission, not a requirement; all-keyword also compliant) and Exception 2 (symmetric allowlist).
  - [x] Carve-outs (dunders by name; pydantic validators/serializers; Typer/Temporal/pytest by decorator across the whole stack + Typer call-style `Annotated` detection; `@override`).
  - [x] `# kw-only: ignore` inline suppression.
  - [x] Baseline support: `relpath::qualified_name` keys (no line numbers); fails only on non-baselined violations; `--regen-baseline`; warns + prunes stale entries.
  - [x] Modes: human-readable default, `--report`, `--quiet`/`-q`.
- [x] Registered in the dev CLI; added Makefile target `check-keyword-only` (alias `cko`); added to BOTH the `check` aggregate and `agent-check`.
- [x] Generated the **initial baseline** (812 violations). ⚠️ Not yet committed — see snapshot.
- [x] Produced the **first inventory** (`--report` → `inventory.json`); per-package counts recorded in `state.md`.

### 🛑 CHECKPOINT A — guard exists, tested, baselined, inventory captured

> Natural session boundary: the tooling is a coherent landed unit; the next phase opens the (large) burn-down. Verify per protocol, then snapshot.

**Cold-start snapshot — Checkpoint A reached & verified (2026-05-31):**

- **Guard:** `.venv/bin/pipelex-dev check-keyword-only` (`--report` / `--regen-baseline` / `--quiet`). Makefile `make check-keyword-only` (alias `cko`), wired into both `check` and `agent-check`. Source `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py`; registration `pipelex/cli/dev_cli/_dev_cli.py`; tests `tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd.py`; baseline `wip/keyword-only-args/violations-baseline.txt`; inventory `wip/keyword-only-args/inventory.json`.
- **`make agent-check` + `make agent-test`:** both green. agent-check = pyright 0 errors, mypy 1932 files ok, guard `PASSED (812 known-debt)`; full agent-test exit 0; guard unit tests 28/28.
- **Inventory:** 812 violations baselined; per-package table in [`state.md`](wip/keyword-only-args/state.md) (top: cogt 132, tools 131, cli 109, core 108).
- **Decisions (confirmed with user):** (1) **STRICT** rule — only the subject may be positional, everything else keyword-only; all-keyword (incl. the subject) is always allowed and often preferred. `convention.md` corrected — the spec agent had drifted to a looser "one trailing positional OK" reading that contradicted the code & baseline. (2) Guard runs in **both** `agent-check` and `check`. (3) `@override`-skip (no `@kw_exempt`) — justified by `reportImplicitOverride=true` + `reportIncompatibleMethodOverride=error`. (4) Symmetric allowlist kept to 4 conservative entries.
- **Open / deferred:** Exception-2 whole-function allowlist can't express "directional pair positional + options keyword"; resolve `copy_file` / `has_diff_dirs` / `sync_toml_values` per-function at burn-down (reshape vs a per-entry leading-positional-count guard enhancement). Tracked in `state.md`.
- **Next action:** Commit Phase 1 (guard + docs + Makefile + `_dev_cli.py` + baseline/inventory) on `refactor/Function-calling-1` — decide own-PR vs base-of-Wave-1-PR — then begin Wave 1 (`tools/` first). **Nothing is committed yet.**

---

## Phase 2 — Wave 1: low-risk leaf packages

Order: `tools/` → (`types.py`, `config.py`, `urls.py`, `errors/`, `base_exceptions.py`, `exceptions.py`) → `reporting/` → `observer/` → `tracing/`.

Per-package loop for each: apply `*` per the convention → `make agent-check` → fix flagged call sites to keyword form → run targeted tests → delete the package's baseline entries → `make agent-test`. Leave all changes uncommitted (no per-package commit) — the user reviews and pushes the whole wave at the checkpoint.

- [x] `tools/` — 136 violations cleared.
- [x] root modules: `types.py`, `config.py`, `urls.py`, `errors/`, `base_exceptions.py`, `exceptions.py` — only `errors/` (5) had violations; `types.py`/`config.py`/`urls.py`/`base_exceptions.py`/`exceptions.py` were already compliant. (`config.py`, `hub.py`, `pipelex.py` public-API violations deferred to Wave 5 as planned.)
- [x] `reporting/` — 5 cleared.
- [x] `observer/` — 2 cleared.
- [x] `tracing/` — 6 cleared.
- [x] Changelog under `[Unreleased]` (Changed section); left uncommitted for the user to review and push.

### 🛑 CHECKPOINT B — Wave 1 landed

**Cold-start snapshot — Checkpoint B reached & verified (2026-06-14):**

- **What landed (all uncommitted on `refactor/Function-calling-3`):** Wave 1 converted `tools/` + `errors/` + `reporting/` + `observer/` + `tracing/` to keyword-only — baseline **844 → 690** (154 removed). Working-tree diff: the ~40 source files in those packages (bare `*` after subject), their call sites tree-wide (incl. `tests/` and cross-package callers in `cli/`, `cogt/`, `core/`, `system/`, `libraries/`), the `@override` impl signatures forced by base/Protocol changes (`core/stuffs/*` + `builder/pipe/*` + `builder/*` `rendered_pretty` ×~25; `core/memory/working_memory.py`; `tools/secrets/env_secrets_provider.py`), the guard (`pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py` — new Jinja2 `@pass_context`/`@pass_environment`/`@pass_eval_context` carve-out) + 2 new guard tests, `wip/keyword-only-args/convention.md`, `CHANGELOG.md`, regenerated `violations-baseline.txt` (690) + `inventory.json`, `wip/keyword-only-args/state.md`, and this file.
- **Verification:** `make agent-check` green (pyright 0, mypy 2190 ok, guard PASSED 690 known-debt); full `make agent-test` GREEN; guard unit tests 32/32.
- **Remaining baseline:** 690 — per-package table in [`state.md`](wip/keyword-only-args/state.md). Wave 1 packages fully pruned.
- **Decisions / edge cases this wave:** (1) **Jinja2 filter carve-out** — `@pass_context`/`@pass_environment`/`@pass_eval_context` filters are invoked POSITIONALLY by the engine; added to the guard's framework carve-out, reverted the `*` on `text_format`/`tag`/`with_images`. Found via `make agent-test` (513 e2e failures), NOT agent-check — type checkers are blind to the engine's dynamic call. (2) **Existing-`*` trap** — a function with a `*` can still violate when 2+ positionals precede it; move the `*`, don't skip (six functions mis-skipped then hand-fixed). (3) **Exception-2 directional pairs** (`copy_file`/`has_diff_dirs`/`sync_toml_values`) resolved by reshape (subject positional, rest keyword), not an allowlist extension. (4) Override cascades are deep — fix tree-wide in one pass.
- **Deferred / surprises:** Wave 1's "root modules" had no violations except the public surface (`hub.py`/`pipelex.py`), correctly left for Wave 5. The 513-failure regression (all from one Jinja2 filter on the prompt-render path) is the headline lesson — `make agent-test` is mandatory per wave.
- **Next action:** Begin **Wave 2 / Phase 3** — domain core `core/` → `language/` → `kit/` → `libraries/`. Use the step-by-step recipe now recorded in `state.md` ("Execution recipe that worked for Wave 1"). `core/` (110) is the project's largest call-site diff — give it its own reviewable slice. **Nothing is committed; the user reviews the working tree and pushes before Wave 2 cold-starts.**

---

## Phase 3 — Wave 2: domain core

Order: `core/` → `language/` → `kit/` → `libraries/`. Same per-package loop. `core/` has many call sites — expect the largest call-site diff here; consider handling `core/` as its own reviewable working-tree slice (its own checkpoint) so the user can review and push it on its own.

- [x] `core/` — 110 cleared.
- [x] `language/` — 4 cleared.
- [x] `kit/` — 8 cleared.
- [x] `libraries/` — 28 cleared.
- [x] Changelog under `[Unreleased]` (Changed section); left uncommitted for the user to review and push.

### 🛑 CHECKPOINT C — Wave 2 landed

**Cold-start snapshot — Checkpoint C reached & verified (2026-06-14):**

- **What landed (all uncommitted on `refactor/Function-calling-4`):** Wave 2 converted `core/` + `language/` + `kit/` + `libraries/` to keyword-only — baseline **690 → 540** (150 cleared, the exact Wave 2 target). Working-tree diff (~108 files): the 50 source files in those four packages (bare `*` after subject), their call sites tree-wide (incl. `tests/`), the `@override` impl signatures forced by the now-keyword-only `core/` bases (`pipe_operators/*` ×16, `pipe_controllers/*` ×9, `pipe_signature/*` ×2 — all guard-carved-out, so they don't move the baseline but need the `*` for pyright parity; plus `core/stuffs/*` content impls and the `StructureGenerator` codegen surface), the five `render_with_images` impls aligned to the already-keyword-only `ImageRenderable` Protocol, the two `render_with_images` docs (`docs/under-the-hood/{image-handling-in-llm-prompts,stuffartefact-and-image-rendering}.md`), `CHANGELOG.md`, regenerated `violations-baseline.txt` (540), `wip/keyword-only-args/state.md`, and this file.
- **Verification:** `make agent-check` green (pyright 0, mypy 2190 ok, guard PASSED 540 known-debt); full `make agent-test` GREEN (exit 0).
- **Remaining baseline:** 540 — per-package table in [`state.md`](wip/keyword-only-args/state.md). All four Wave 2 packages fully pruned to 0.
- **Decisions / edge cases this wave:** (1) **Executed via a Workflow** (user request) — guard-driven signature fan-out, then a pyright-driven converge with pyright kept in the main loop and batched fixers fanned out per step. The full rate-limit lesson (a 97-agent in-workflow loop tripped a *server-side* rate limit; mitigation = main-loop-driven loop + ~5-files-per-fixer batching) is recorded in `state.md` → "Workflow execution notes". (2) **Override cascade is the bulk of the cross-package diff** — making `PipeAbstract._validate_*` / `_register_execution_data`, `StuffContent.rendered_markdown(_async)`, `LibraryManagerAbstract` loaders, and `PipeFactoryProtocol` keyword-only forced matching `*` on every `@override` impl in `pipe_operators/`, `pipe_controllers/`, `pipe_signature/`; correct and expected (those packages' own non-override sigs stay Wave 4). (3) **existing-`*` trap recurred** — `LibraryManager._load_address_based_dependency` had a `*` after two positionals; moved it up (call site was already all-keyword).
- **Deferred / surprises:** the `render_with_images` doc examples (invisible to both guard and suite) were the only thing nothing automated caught — fixed by hand. No deferred design tradeoffs this wave.
- **Next action:** Begin **Wave 3 / Phase 4** — inference layer `cogt/` (139) → `plugins/` (50). `plugins/` wraps external LLM SDKs — watch for adapter functions handed to SDK callbacks (carve out / allowlist as needed). Reuse the "Workflow execution notes" recipe in `state.md` (it scales to Wave 3's 189-violation size). **Nothing is committed; the user reviews the working tree and pushes before Wave 3 cold-starts.**

---

## Phase 4 — Wave 3: inference layer

Order: `cogt/` → `plugins/`. `plugins/` wraps external LLM SDKs — watch for adapter functions handed to SDK callbacks (carve out / allowlist as needed). Respect `pipelex/builder/CLAUDE.md` spec-vs-blueprint boundaries if any spec code is touched here.

- [x] `cogt/` — 139 cleared.
- [x] `plugins/` — 50 cleared.
- [x] Changelog under `[Unreleased]` (Changed section); left uncommitted for the user to review and push.

### 🛑 CHECKPOINT D — Wave 3 landed

**Cold-start snapshot — Checkpoint D reached & verified (2026-06-14):**

- **What landed (all uncommitted on `refactor/Function-calling-4`):** Wave 3 converted `cogt/` + `plugins/` to keyword-only — baseline **540 → 351** (189 cleared, the exact Wave 3 target). Working-tree diff (~127 files): the source files in `cogt/` + `plugins/` (bare `*` after subject), their call sites tree-wide (incl. `tests/`, `cli/`, `temporal/`, `system/`), the `@override` impl signatures forced by the now-keyword-only `cogt/` protocols/abstracts (`ContentGeneratorProtocol`, `LLMWorkerAbstract`/`ImgGenWorkerAbstract`/`SearchWorkerAbstract`, `PluginFactoryAbstract`, `InferenceManagerProtocol`, `ModelManagerAbstract`) + the deep `make_extras` cascade (`OpenAICompletionsFactory`/`OpenAIResponsesFactory` bases → `plugins/{blackboxai,openrouter,portkey,gateway}` overrides + the Temporal in-workflow content generator), the dry-mock `_ReportLLMJobFunc` → keyword-only `Protocol` conversion, the `SchemaToModelFactory._restricted_import` carve-out, `CHANGELOG.md`, regenerated `violations-baseline.txt` (351), `wip/keyword-only-args/state.md`, and this file.
- **Verification:** `make agent-check` green (pyright 0, mypy 2190 ok, guard PASSED 351 known-debt); full `make agent-test` GREEN; guard unit tests 32/32.
- **Remaining baseline:** 351 — per-package table in [`state.md`](wip/keyword-only-args/state.md). Both Wave 3 packages fully pruned to 0.
- **Execution:** run as a Workflow (Wave 2 recipe) — a 14-agent file-disjoint signature barrier (189 funcs: 188 added-star, 1 moved-star, zero needs-manual/not-found), then a main-loop-driven pyright converge with an 11-batch fixer fan-out (~5 files each). Converge went 154 → 8 actionable in one pass; the 8 residuals (deep `make_extras` override cascade + 2 missed call sites) hand-fixed. No rate limits (the Wave 2 mitigation held).
- **Decisions / edge cases this wave:** (1) **`_restricted_import` carve-out** — installed as the exec sandbox's `__import__`, so the interpreter calls it positionally; the keyword-only conversion passed agent-check but caused **155 agent-test failures** (every structured-object-gen path, incl. all the Temporal tracing/isolation tests). Reverted to positional + `# kw-only: ignore`. The recurrence of the Wave 1 Jinja2 lesson: framework/interpreter-registered callbacks stay positional, and only `make agent-test` catches them. (2) **`_ReportLLMJobFunc` callback type** — a keyword-only callback contract needs a `Protocol` with keyword-only `__call__`, not a `Callable[[...]]` alias (which can't express keyword-only). (3) **Deep override cascade surfaces level-by-level** — the 6 `make_extras` subclass overrides only appeared in pyright's *second* pass; re-run pyright until genuinely 0.
- **Deferred / surprises:** the plan flagged *plugins SDK* callbacks as the risk; the actual callback casualties were both in `cogt/content_generation/`. No deferred design tradeoffs this wave.
- **Next action:** Begin **Wave 4 / Phase 5** — execution path `pipe_operators/` (40) → `pipe_controllers/` (6) → `pipe_run/` (16) → `pipeline/` (15) → `graph/` (39), plus `runtime_bridge/` (13) and `pipe_signature/` (2). Reuse the Workflow recipe in `state.md`. `pipe_operators/` + `pipe_controllers/` already carry their `@override` `*` from Waves 2–3 — only their own non-override signatures remain. **Nothing is committed; the user reviews the working tree and pushes before Wave 4 cold-starts.**

---

## Phase 5 — Wave 4: execution path

Order: `pipe_operators/` → `pipe_controllers/` → `pipe_run/` → `pipeline/` → `graph/`. Heavily called internally; lean hard on pyright + the integration tests as the net.

- [x] `pipe_operators/` — 40 cleared.
- [x] `pipe_controllers/` — 6 cleared.
- [x] `pipe_run/` — 16 cleared.
- [x] `pipeline/` — 15 cleared.
- [x] `graph/` — 39 cleared. (Plus `runtime_bridge/` 13 and `pipe_signature/` 2, which share these call paths — both cleared.)
- [x] Changelog under `[Unreleased]` (Changed section); left uncommitted for the user to review and push.

### 🛑 CHECKPOINT E — Wave 4 landed

**Cold-start snapshot — Checkpoint E reached & verified (2026-06-14):**

- **What landed (all uncommitted on `refactor/Function-calling-4`):** Wave 4 converted the execution path — `pipe_operators/` + `pipe_controllers/` + `pipe_run/` + `pipeline/` + `graph/` + `runtime_bridge/` + `pipe_signature/` — to keyword-only — baseline **351 → 220** (131 cleared, the exact Wave 4 target). Working-tree diff (~75 files): the source files in those seven packages (bare `*` after subject), their call sites tree-wide (incl. `tests/unit`, `tests/e2e`, `tests/integration`, and **2 `temporal/` caller files** — `temporal_pipe_router.py` + `temporal_pipe_run.py` — call-site fixes into the now-keyword-only execution path, NOT Wave 5 signature work), the `@override` impl signatures forced by the now-keyword-only `PipeController` / `PipeOperator` `_live_run_*` / `_dry_run_*` bases + `GraphTracerProtocol` + `PipeRouterProtocol` / `PipeRunProtocol` (the pipe-operator and pipe-controller subclasses), `CHANGELOG.md`, the regenerated `violations-baseline.txt` (220) + refreshed `inventory.json`, `wip/keyword-only-args/state.md`, the new signature-workflow script `wip/keyword-only-args/workflows/scripts/kw-only-wave4-signatures.js`, and this file.
- **Verification:** `make agent-check` green (pyright 0, mypy 2191 ok, guard PASSED 220 known-debt); full `make agent-test` GREEN (exit 0).
- **Remaining baseline:** 220 — per-package table in [`state.md`](wip/keyword-only-args/state.md). All seven Wave 4 packages fully pruned to 0; only Wave 5 packages remain (`cli` 111, `system` 44, `temporal` 39, `builder` 21, `<root>` public-API 4, plus the separate `test_extras` 1).
- **Execution:** run as a Workflow (Wave 2/3 recipe) — a 10-editor file-disjoint signature barrier over 44 files (131 funcs: 123 added-star, 7 moved-star, 1 needs-manual = `PipeBatch._run_branch`), then a main-loop-driven pyright converge with a 10-batch fixer fan-out (~5 files each) over 174 actionable errors (141 `reportCallIssue` + 33 `reportIncompatibleMethodOverride`) — **cleared to 0 in one pass**, no rate limits, no residual existing-`*` trap.
- **Decisions / edge cases this wave:** (1) **Clean wave — zero new carve-outs.** No framework/interpreter callback casualties (contrast Wave 1 Jinja2, Wave 3 `_restricted_import`); the execution path is heavily called internally + through tests, so pyright + the suite caught everything. (2) **`functools.partial` + nested closure** (`PipeBatch._run_branch`, the lone needs-manual) — resolved by making it keyword-only AND passing the bound arg by keyword in the partial (`partial(fn, subject, kw=val)`); no `# kw-only: ignore` needed, since *we* control the partial call (unlike the framework-positional carve-outs). (3) **Phase A args gotcha** — a large nested `args` object came through empty; switched the signature workflow to read a spec file via `args.specPath` (the saved fixer's `bucketsPath` pattern). All recorded in `state.md`.
- **Deferred / surprises:** none. No deferred design tradeoffs. The override cascade surfaced level-by-level (as Wave 3 warned) but the single batched-fixer pass resolved all levels at once because fixers align each override against its base regardless of which level pyright reported. As in Wave 2, the only thing neither the guard nor the suite caught was stale **doc examples** with positional args — a `grep docs/` for the changed public-ish functions found and fixed three in `docs/under-the-hood/execution-graph-tracing.md` (`make_from_graphspec` / `generate_reactflow_html` / `generate_graph_outputs`).
- **Next action:** Begin **Wave 5 / Phase 6** — framework-sensitive & public API: `builder/` (21) → `temporal/` (39, **carve out** `@activity.defn` / `@workflow.*` entrypoints — already in the guard) → `system/` (44, run `make tb` boot test after) → `cli/` (111, **carve out** Typer commands — already in the guard) → public surface `hub.py` / `config.py` / `pipelex.py` (4, enumerate breaking signatures explicitly in the changelog for downstream `pipelex-api` / `pipelex-worker` / `n8n` / cookbook). Reuse the Workflow recipe + the `kw-only-wave4-signatures.js` script (pass `args.specPath`). **Nothing is committed; the user reviews the working tree and pushes before Wave 5 cold-starts.**

---

## Phase 6 — Wave 5: framework-sensitive & public API (most care, last)

Order: `builder/` → `temporal/` → `system/` → `cli/` → top-level `hub.py`, `config.py`, `pipelex.py`.

- [x] `builder/` — 21 cleared (honored the spec-vs-blueprint layering; these are `operations/` ops + `runner_code`, the authoring-convenience layer).
- [x] `temporal/` — 38 cleared. Activity/workflow/signal/query entrypoints stayed carved out by the guard; only plain helpers touched. **One framework-callback casualty pre-handled:** `codec/codec_server.py::_apply` (aiohttp route handler) carved out `# kw-only: ignore`.
- [x] `system/` — 43 cleared; `make tb` (boot path) green after. **Three callback casualties pre-handled:** `telemetry/exception_capture.py::_exception_handler` (`sys.excepthook`) + the two `telemetry/telemetry_manager.py` PostHog `on_error` callbacks, all carved out.
- [x] `cli/` — 110 cleared; Typer commands stayed carved out by the guard. `serve_until_callback` (a `threading.Thread` target) kept convention-compliant by passing its bound arg via `kwargs=` at the call site (not carved out — we own that call).
- [x] Public API surface: `hub.py` (1) + `pipelex.py` (3) cleared. The breaking public signatures — `Pipelex.make()`, `Pipelex.setup()`, `PipelexHub.setup_config()` (subject positional, all later args keyword-only) — are enumerated in the changelog with the downstream-consumer list. (`config.py` had no violations.) Plus `test_extras`'s lone pytest hookimpl carved out, bringing the baseline to empty.
- [x] Changelog under `[Unreleased]` with the public-API breaking-change note; left uncommitted for the user to review and push.

### 🛑 CHECKPOINT F — Wave 5 landed, codebase clean

**Cold-start snapshot — Checkpoint F reached & verified (2026-06-14):**

- **What landed (all uncommitted on `refactor/Function-calling-4`):** Wave 5 converted the framework-sensitive packages `builder/` + `temporal/` + `system/` + `cli/` + the public surface `hub.py`/`pipelex.py` + the lone `test_extras` pytest hookimpl — baseline **220 → 0**. The burn-down is complete: **every `pipelex/` source package is keyword-only compliant and the guard baseline file is empty.** Working-tree diff (~128 tracked files + 2 new wip scripts): the source files in the Wave 5 packages (bare `*` after subject), their call sites tree-wide (incl. `tests/`), the `@override` impls forced by the now-keyword-only `TelemetryManagerAbstract` (`track_event`, `handle_trace_start`) and other system/cli bases, the six framework-callback carve-outs (`# kw-only: ignore`), the `serve_until_callback` Thread-call fix, five test mock-assertion updates (`test_worker_cli.py` ×2, `test_plxt_passthrough.py` ×2, `test_run_core_execution.py` ×1), `CHANGELOG.md`, the regenerated empty `violations-baseline.txt` + `inventory.json`, the new workflow scripts `wip/keyword-only-args/workflows/scripts/kw-only-wave5-signatures.js` + `kw-only-fix-callsites.js`, `wip/keyword-only-args/state.md`, and this file.
- **Verification:** `make agent-check` green (pyright 0, mypy 2191 ok, guard PASSED against the **empty baseline**); `make tb` (boot path) green; full `make agent-test` GREEN (clean re-run after fixing the 5 mock-assertion mismatches).
- **Baseline is empty — confirmed:** `wc -l wip/keyword-only-args/violations-baseline.txt` → 0; `inventory.json` total 0; `make cko` PASSED.
- **Breaking public-API signature changes (changelog / downstream `pipelex-api`, `pipelex-worker`, `n8n-nodes-pipelex`, cookbook, starter):** `Pipelex.make()`, `Pipelex.setup()`, and `PipelexHub.setup_config()` keep their first parameter positional (`integration_mode` / `config_cls`) and make every later argument keyword-only. Only a caller passing a second-or-later argument positionally breaks (e.g. `Pipelex.make(IntegrationMode.PYTHON, False)` → `Pipelex.make(needs_inference=False)`); the common no-arg / all-keyword calls are unaffected.
- **Decisions / edge cases this wave:** (1) **Six framework-positional carve-outs found PROACTIVELY** by grepping for callback-registration patterns before the fan-out (no agent-test casualty this wave as a result): aiohttp `_apply`, `sys.excepthook` `_exception_handler`, two PostHog `on_error` callbacks, pytest hookimpl `pytest_collection_modifyitems` — all `# kw-only: ignore`. (2) **`serve_until_callback`** (a `threading.Thread` target, pyright-blind) stayed convention-compliant via `kwargs=` at the call site — carve out only when a *framework* does the positional call. (3) **`# kw-only: ignore` must sit after the open paren on the def's first line** — a trailing comment on a long single-line def gets wrapped by `ruff format` off `node.lineno`, silently disabling the carve-out (surfaced as "guard PASSED (3 known-debt)" post-format). (4) **Signature barrier tripped the server-side rate limit** at 14 concurrent editors — fixed by chunking editors into sequential sub-barriers of 4 (peak concurrency ¼); reused for the converge fixers. (5) **`make agent-test` caught 5 pyright-blind mock-assertion mismatches** — the recurring "the suite is the only net for `Any`-typed/dynamic call surfaces" lesson.
- **Next action:** Begin **Phase 7 / Checkpoint G** — flip the guard to hard-block on ANY violation (the empty baseline already makes any new violation fail; remove the baseline scaffolding or keep an empty-baseline-must-stay-empty comment), confirm `check-keyword-only` is in the `make check` aggregate + CI, document the convention as a standing rule in `CLAUDE.md` linking `wip/keyword-only-args/convention.md` (or promote the doc to a permanent home), add the final summary changelog entry, and fold/retire the `wip/keyword-only-args/` track per the wip-docs convention. **Nothing is committed; the user reviews the working tree and pushes before Phase 7 cold-starts.**

---

## Phase 7 — Flip to fully enforced & document

- [x] Confirm the baseline file is empty (no remaining known violations).
- [x] Make the guard hard-block on **any** violation; remove baseline scaffolding (or keep an empty baseline + a comment that it must stay empty). **Chose full removal** — deleted the baseline file, the `BASELINE_PATH` constant, the `load_baseline` / `write_baseline` / `partition_violations` / `_warn_stale_baseline` helpers, and the `--regen-baseline` CLI flag; the guard now fails on ANY violation. Also removed the 2 baseline-behaviour unit tests (which fixed a latent two-`TestClass`-per-module convention break).
- [x] Confirm `check-keyword-only` is in the `make check` aggregate and runs in CI. It was already in `make check` + `make agent-check`; added a dedicated `lint-keyword-only` job to `.github/workflows/lint-check.yml`, wired into the required `Lint (all)` aggregator's `needs` + failure check.
- [x] Document the convention as a standing rule in `CLAUDE.md` (Pipelex coding rules) so new code follows it, linking to the convention doc. **Promoted the convention out of `wip/` to its permanent home** at `docs/contribute/keyword-only-arguments.md` (added to the mkdocs nav under Project). The standing-rule summary was added to the kit rules **source** `pipelex/kit/agent_rules/pipelex_standards.md` (NOT the generated `CLAUDE.md` directly) and regenerated into `CLAUDE.md` + `AGENTS.md` via `make rules`; `make check-rules` confirms they are in sync.
- [x] Final changelog entry under `[Unreleased]` summarizing the refactor + the new guard.
- [x] Fold/retire the `wip/keyword-only-args/` track per the wip-docs convention once the work is done. **Retired the `wip/keyword-only-args/` folder** — convention promoted to `docs/`; the completed-migration scaffolding (baseline / inventory / "next: Phase 7" state log / README / workflow scripts) was removed (its lessons live in these checkpoint snapshots + memory). The one genuinely-open deferred record — the cross-repo lockstep work — was **preserved**, folded to a single self-describing file at the wip root: [`wip/keyword-only-arguments-downstream-consumer-breakage.md`](wip/keyword-only-arguments-downstream-consumer-breakage.md). A `./wip/` folder is intentionally kept.

### 🛑 CHECKPOINT G — fully enforced, documented, done

**Cold-start snapshot — Checkpoint G reached & verified (2026-06-14):**

- **Guard now hard-blocking? CI confirmed?** Yes to both. The baseline scaffolding is fully removed; `pipelex-dev check-keyword-only` collects violations and fails on ANY (no baseline, no `--regen-baseline`). It runs in `make agent-check`, in the `make check` aggregate, and in a new `lint-keyword-only` CI job gated by the required `Lint (all)` status check in `.github/workflows/lint-check.yml`.
- **Convention documented where:** permanent home `docs/contribute/keyword-only-arguments.md` (in the mkdocs nav under Project, "Keyword-Only Arguments"); standing-rule summary in the generated contributor `CLAUDE.md` / `AGENTS.md`, authored in the kit source `pipelex/kit/agent_rules/pipelex_standards.md` and regenerated via `make rules` (verified in sync by `make check-rules`). The guard module docstring and the convention doc both point at the new path; no references to the old `wip/` path remain in source.
- **What landed (all uncommitted on `refactor/Function-calling-4`):** guard rewrite (`pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py` — baseline scaffolding removed, hard-block; docstrings de-baselined) + CLI wrapper (`_dev_cli.py` — dropped `--regen-baseline`) + unit tests (removed the baseline `TestClass`, 32 → 30 tests) + CI (`lint-check.yml` new job) + the promoted convention doc (`docs/contribute/keyword-only-arguments.md`, Rollout→Enforcement section rewritten to current reality) + mkdocs nav + kit rule source + regenerated `CLAUDE.md`/`AGENTS.md` + `CHANGELOG.md` final entry + this tracker; the **retirement** of the `wip/keyword-only-args/` folder (completed-migration scaffolding removed); and the preserved deferred-work record `wip/keyword-only-arguments-downstream-consumer-breakage.md`.
- **Final `make agent-test` result:** GREEN (exit 0, "All tests passed"). The change set is dev-tooling + docs + CI + generated-rules only; no shipped runtime code changed.
- **`make agent-check`:** green — pyright 0, mypy 2191 ok, guard PASSED (no baseline). Guard unit tests 30/30. `make check-rules` PASSED.
- **Anything intentionally left out of scope:** `tests/` call sites remain positional by design (tests call internals positionally on purpose — locked decision #1). The four symmetric-tuple allowlist entries and the framework/interpreter `# kw-only: ignore` carve-outs (aiohttp `_apply`, `sys.excepthook`, PostHog `on_error` ×2, polyfactory `PostGenerated`, `__import__`, pytest hookimpl) are the sanctioned permanent exceptions. TODOS.md itself is left in place as the historical record (it may be deleted now that the work is complete).

---

## Risks & open questions

- **Override detection is imperfect via AST.** A method that overrides a base/Protocol/ABC must keep the parent's call convention; the guard can't resolve the base reliably. Mitigation: pyright/mypy flag LSP-incompatible overrides, plus the `# kw-only: ignore` escape hatch. If false positives are frequent, consider a lightweight `@kw_exempt` marker decorator instead of comments — **decide during Phase 1.**
- **Symmetric allowlist is a judgment call.** Keep it short and explicit; review additions. Erring toward keyword-only is the safe default.
- **Dynamic call sites** (`**kwargs` forwarding, `getattr`, `partial`) escape the type checker — rely on `make agent-test`; if a wave touches a lot of forwarding code, add targeted tests.
- **Merge pressure.** If `refactor/Function-calling`/ECR or other branches are mid-flight, sequence waves to minimize overlap with their hot files; rebase frequently.
- **`tests/` excluded for now** — revisit after the source is clean if we want call-site consistency in tests too.
