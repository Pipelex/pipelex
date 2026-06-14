# Keyword-Only Arguments Refactor — Plan & Tracker

Make non-subject function parameters **keyword-only** across the `pipelex/` runtime, so call sites are self-documenting (a dev or SWE agent can read a call and know what each argument means without opening the definition). Build an enforcement guard *first*, then burn down the existing code package-by-package behind it.

This file is the master tracker. Detailed convention spec and the running cold-start state live under `wip/keyword-only-args/` (created in Phase 1). Use the checkboxes to track progress; **do not skip the mandatory checkpoints** — each is a hard stop where the running agent must verify, snapshot context, and hand off cleanly.

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
- [ ] Changelog entries go under the `[Unreleased]` section as waves land.

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

- [ ] `core/`
- [ ] `language/`
- [ ] `kit/`
- [ ] `libraries/`
- [ ] Changelog under `[Unreleased]`; leave the wave uncommitted for the user to review and push.

### 🛑 CHECKPOINT C — Wave 2 landed

**Cold-start snapshot (fill in at checkpoint):**

- What landed this wave (files changed, left uncommitted in the working tree):
- Remaining baseline count (link to `state.md`):
- Decisions / edge cases this wave:
- Deferred / surprises:
- Next action:

---

## Phase 4 — Wave 3: inference layer

Order: `cogt/` → `plugins/`. `plugins/` wraps external LLM SDKs — watch for adapter functions handed to SDK callbacks (carve out / allowlist as needed). Respect `pipelex/builder/CLAUDE.md` spec-vs-blueprint boundaries if any spec code is touched here.

- [ ] `cogt/`
- [ ] `plugins/`
- [ ] Changelog under `[Unreleased]`; leave the wave uncommitted for the user to review and push.

### 🛑 CHECKPOINT D — Wave 3 landed

**Cold-start snapshot (fill in at checkpoint):**

- What landed this wave (files changed, left uncommitted in the working tree):
- Remaining baseline count (link to `state.md`):
- Decisions / edge cases this wave (esp. plugin/SDK callback signatures):
- Deferred / surprises:
- Next action:

---

## Phase 5 — Wave 4: execution path

Order: `pipe_operators/` → `pipe_controllers/` → `pipe_run/` → `pipeline/` → `graph/`. Heavily called internally; lean hard on pyright + the integration tests as the net.

- [ ] `pipe_operators/`
- [ ] `pipe_controllers/`
- [ ] `pipe_run/`
- [ ] `pipeline/`
- [ ] `graph/`
- [ ] Changelog under `[Unreleased]`; leave the wave uncommitted for the user to review and push.

### 🛑 CHECKPOINT E — Wave 4 landed

**Cold-start snapshot (fill in at checkpoint):**

- What landed this wave (files changed, left uncommitted in the working tree):
- Remaining baseline count (link to `state.md`):
- Decisions / edge cases this wave:
- Deferred / surprises:
- Next action:

---

## Phase 6 — Wave 5: framework-sensitive & public API (most care, last)

Order: `builder/` → `temporal/` → `system/` → `cli/` → top-level `hub.py`, `config.py`, `pipelex.py`.

- [ ] `builder/` — honor `pipelex/builder/CLAUDE.md` spec-vs-blueprint layering; decide which layer each new keyword-only rule belongs to.
- [ ] `temporal/` — **carve out** activity/workflow/signal/query entrypoints (framework-called); only touch plain helpers. Cross-check with the temporal e2e validation before merging.
- [ ] `system/` — `ConfigModel` / boot path; run `make tb` (boot test) after, since config loading is signature-sensitive.
- [ ] `cli/` — **carve out** Typer command functions; only touch plain helpers.
- [ ] Public API surface: `hub.py`, `config.py`, `pipelex.py` — these break downstream consumers (`pipelex-api`, `pipelex-worker`, `n8n-nodes-pipelex`, cookbook/starter). Enumerate the changed public signatures and call them out explicitly in the changelog.
- [ ] Changelog under `[Unreleased]` with a clear breaking-change note for public signatures; leave the wave uncommitted for the user to review and push.

### 🛑 CHECKPOINT F — Wave 5 landed, codebase clean

**Cold-start snapshot (fill in at checkpoint):**

- What landed this wave (files changed, left uncommitted in the working tree):
- Baseline should now be **empty** — confirm:
- List of breaking public-API signature changes (for changelog / downstream repos):
- Decisions / edge cases this wave (temporal/cli/builder carve-outs):
- Next action:

---

## Phase 7 — Flip to fully enforced & document

- [ ] Confirm the baseline file is empty (no remaining known violations).
- [ ] Make the guard hard-block on **any** violation; remove baseline scaffolding (or keep an empty baseline + a comment that it must stay empty).
- [ ] Confirm `check-keyword-only` is in the `make check` aggregate and runs in CI.
- [ ] Document the convention as a standing rule in `CLAUDE.md` (Pipelex coding rules) so new code follows it, linking to `wip/keyword-only-args/convention.md` (or promote the convention doc out of `wip/` to its permanent home).
- [ ] Final changelog entry under `[Unreleased]` summarizing the refactor + the new guard.
- [ ] Fold/retire the `wip/keyword-only-args/` track per the wip-docs convention once the work is done.

### 🛑 CHECKPOINT G — fully enforced, documented, done

**Cold-start snapshot (fill in at checkpoint):**

- Guard now hard-blocking? CI confirmed?
- Convention documented where:
- Final `make agent-test` result:
- Anything intentionally left out of scope (e.g. `tests/`):

---

## Risks & open questions

- **Override detection is imperfect via AST.** A method that overrides a base/Protocol/ABC must keep the parent's call convention; the guard can't resolve the base reliably. Mitigation: pyright/mypy flag LSP-incompatible overrides, plus the `# kw-only: ignore` escape hatch. If false positives are frequent, consider a lightweight `@kw_exempt` marker decorator instead of comments — **decide during Phase 1.**
- **Symmetric allowlist is a judgment call.** Keep it short and explicit; review additions. Erring toward keyword-only is the safe default.
- **Dynamic call sites** (`**kwargs` forwarding, `getattr`, `partial`) escape the type checker — rely on `make agent-test`; if a wave touches a lot of forwarding code, add targeted tests.
- **Merge pressure.** If `refactor/Function-calling`/ECR or other branches are mid-flight, sequence waves to minimize overlap with their hot files; rebase frequently.
- **`tests/` excluded for now** — revisit after the source is clean if we want call-site consistency in tests too.
