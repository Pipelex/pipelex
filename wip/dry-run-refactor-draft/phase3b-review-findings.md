# Phase 3b — code-review follow-ups (pipelex-api migration + `allow_signatures`)

Findings from an xhigh-recall `/code-review` of the Phase 3b work (CHECKPOINT B). Captured here so a fresh session can triage them without re-running the review. Nothing in this doc has been applied **except** finding R-LINT (the ruff import-order fix), which already landed.

> **Verification + arbitration (2026-06-02).** Every finding was re-verified by symbol against the current code in both repos. Outcome: C-1, C-2, C-3, C-4 confirmed real; **C-5 refuted** (its stated Temporal-dispatch risk does not exist — section rewritten below); Q-1/Q-2/Q-5/Q-6 confirmed; Q-3/Q-4/Q-7 confirmed but **overstated** (see notes). Decisions taken:
>
> - **Do-now PR (pipelex-api):** C-2 + Q-5 (one fix), plus Q-1 (shared request base) and Q-2/Q-6 (test tidy in the same files).
> - **C-3:** add a guard that **rejects `/build/runner`** when the *requested* `pipe_code` itself lands SKIPPED (other unrelated SKIPPED pipes still tolerated).
> - **C-1:** deferred to Part C (already planned). **C-4:** at-merge checklist. **C-5:** corrected, fixture kept.
>
> **Implemented 2026-06-02** (uncommitted, pipelex-api `feature/Update-dry-run-api`): C-2 + Q-5 (drop the second `open_library` in `/build/{inputs,output}`; scope the sweep via `dry_run_pipe_codes`; reuse + tear down `validate_bundle`'s library), C-3 guard (`_reject_if_requested_pipe_skipped` in `build/runner.py` → 422 when the *requested* pipe is SKIPPED), Q-1 (`MthdsContentsRequest` base in `api/schemas/models.py`; the four request models inherit it), Q-2 (tightened the signature assertion), Q-6 (`SIGNATURE_MTHDS`/`VALID_MTHDS` → `tests/unit/_constants.py`). Added C-2 no-leak + C-3 guard regression tests. **Follow-up cleanup (also touches pipelex `_sig`):** renamed the misleading `teardown_current_library()` → `clear_current_library()` across both repos — it only resets the current-library ContextVar pointer and never freed the `Library` (distinct from `library_manager.teardown`); docstring clarified. Both repos `make agent-check` clean + full `make agent-test` green. **Not done (out of do-now scope):** Q-3 (only the 2 verbatim `_build_client` are foldable), Q-4 (keep — unique body asserts), Q-7 (cosmetic).

## What was reviewed

The cross-repo diff for Phase 3b of the dry-run consolidation:

- **pipelex-api** (`feature/Update-dry-run-api`, commit `56ca06a`): `/build/runner` migrated from `dry_run_pipes` to `BundleValidator().validate_pipes(...)`; an `allow_signatures` request field added to all four validation routes (`/validate`, `/build/runner`, `/build/inputs`, `/build/output`); the test autouse fixture forced `temporal_enabled=False`; integration tests added.
- **pipelex** (`_sig`, `feature/Validate-with-signatures-4-fix-dry-run`): `SignaturesNotAllowedError` reclassified `error_domain = INPUT` (commit `24f9f9ca`); ruff import-order fix (commit `0ed98d11`); CHECKPOINT B recorded in [`../../TODOS.md`](../../TODOS.md) (commit `a49fa98a`).

Both repos: `make agent-check` clean, `make agent-test` green at review time.

> **Cold-start note.** This doc lives in the **pipelex** repo (`_sig`), but several fixes target the **pipelex-api** repo (`../pipelex-api`). Each finding names its repo. **Line numbers are indicative — verify by symbol.** None of the correctness findings were introduced by Phase 3b's *logic*; the diff re-exposes or widens pre-existing infrastructure issues, which recall-mode surfaces.

## Status at a glance

| ID | Sev | Repo | Where | Verified? | Status | Note |
|---|---|---|---|---|---|---|
| C-1 | High | pipelex | `pipeline/bundle_validator.py` `validate_pipes` | ✅ real | ⏸ defer→Part C | Confirmed: process-global dict, constant key, hard-raise on open, silent `pop` on close, real `await`s mid-sweep. Pre-existing; only bites under in-process concurrency. Tracked as Part-C / TODOS #3–#4. |
| C-2 | Med-high | pipelex-api | `build/inputs.py`, `build/output.py` | ✅ real | ✅ done | Confirmed: 1 leaked loaded `Library` per successful inputs/output call (`validate_bundle`'s lib A orphaned, route tears down only lib B). `allow_signatures=True` widens it. Anchor of do-now PR (with Q-5). |
| C-3 | Med | pipelex-api | `build/runner.py` | ✅ real | ✅ done | Confirmed: requested-pipe with unresolved cross-package dep → was reject, now 200+SKIPPED+code, no guard. **DECISION: add a guard rejecting when the *requested* `pipe_code` is SKIPPED.** |
| C-4 | Release-block | pipelex-api | `pyproject.toml` + `uv.lock` | ✅ real | ☐ at-merge | Confirmed editable `../_sig` pin; CI (`uv sync --frozen` / `uv lock --check`) breaks until flipped. Intentional D2 lock-step; **must flip to merged pipelex rev before merge**. |
| C-5 | ~~Med~~ | pipelex-api | `tests/unit/conftest.py` | ❌ refuted | ✗ corrected | **Stated mechanism WRONG.** DRY runs in-process regardless of the Temporal flag (BundleValidator uses a direct `PipeRun`; leaves force `ContentGeneratorDry`). No masked dispatch risk; keep fixture. See rewritten section. |
| R-LINT | — | pipelex | `tests/unit/pipelex/cli/test_agent_output.py` | — | ☑ fixed | ruff I001 import order — fixed in `0ed98d11`. |
| Q-1 | Low | pipelex-api | 4× request models | ✅ real | ✅ done | `allow_signatures` field + description + `mthds_contents` + `_bound_each_file` copy-pasted 4×; extract `MthdsContentsRequest` base in `api/schemas/models.py`. |
| Q-2 | Low | pipelex-api | `tests/unit/test_allow_signatures.py` | ✅ real | ✅ done | Near-tautological `"allow" or "signature"` assertion; tighten to the actionable phrase. |
| Q-3 | Low | pipelex-api | test modules | ⚠️ overstated | ☐ low | `_build_client()` verbatim in the **2 named** files only; doc's "~9 other modules" wrong (the other 8 are signature/purpose variants). Opportunistic. |
| Q-4 | Low | pipelex-api | `tests/unit/test_allow_signatures.py` | ⚠️ partial | ☐ don't-fold | Standalone test overlaps parametrized case **only on the 200 check**; it adds unique body assertions (`success`/`pipe_code`/`python_code`). Don't delete — at most move body asserts in. |
| Q-5 | Low-med | pipelex-api | `build/inputs.py`, `build/output.py` | ✅ real | ✅ done | = C-2 fix: pass `dry_run_pipe_codes=[pipe_code]` + reuse `validate_bundle`'s loaded library, drop the second open. |
| Q-6 | Low | pipelex-api | test modules | ✅ real | ✅ done | `SIGNATURE_MTHDS`/`VALID_MTHDS` inlined (`VALID_MTHDS` has 2 non-identical copies); move to `tests/unit/_constants.py`. |
| Q-7 | Very low | pipelex | `tests/unit/pipelex/cli/test_agent_output.py` | ⚠️ moot | ☐ cosmetic | Constructor requires all 3 args (no defaults) → the "full" build is already minimal; best you can do is pass empty `set()/set()/{}`. Barely worth it. |

Legend: ✅ verified real · ⚠️ verified but overstated · ❌ refuted · ▶ do-now · ⏸ deferred · ✓ decided · ☐ open/pending · ☑ fixed · ✗ corrected.

---

## Correctness / infrastructure

### C-1 — `validate_pipes` report registry keyed by a constant id collides under concurrency (High)

- **Repo / where:** pipelex — `pipelex/pipeline/bundle_validator.py`, `validate_pipes` (the `get_report_delegate().open_registry(pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED)` / `close_registry(...)` pair around the per-pipe sweep).
- **What:** the sweep opens a **process-global** report registry keyed by the **constant** `SpecialPipelineId.DRY_RUN_UNTITLED`. `ReportingManager._usage_registries` is a plain dict on the hub singleton (not a `ContextVar`), and `open_registry` hard-raises if the key already exists. The route handlers are `async` and `await` mid-sweep (`prepare_pipe_job` + `PipeRun.run` per pipe), so two requests interleave on the single uvicorn event loop.
- **Failure scenario:** request A `open_registry(DRY_RUN_UNTITLED)` → awaits per-pipe dry-run → yields; request B `open_registry(DRY_RUN_UNTITLED)` → `ReportingManagerError("... already exists")` → B 500s spuriously. Worse, B's `finally close_registry(DRY_RUN_UNTITLED)` can pop A's still-open registry mid-sweep, silently dropping A's dry-run token-usage accounting. Manifests as intermittent 500s + lost accounting under concurrent build/validate traffic; invisible to the test suite (serial, full teardown between tests).
- **Scope:** **pre-existing** (this code predates Phase 3b). It already affects `/validate`, `/build/inputs`, `/build/output` (all routed through `validate_pipes` before this diff); Phase 3b newly exposes `/build/runner`. **Already tracked** in [`../../TODOS.md`](../../TODOS.md) follow-ups table (#3 "per-sweep registry keyed by the constant `DRY_RUN_UNTITLED` id → concurrent sweeps collide") and #4 — the planned fix is a **per-sweep unique `pipeline_run_id`** threaded through `open_registry` + `prepare_pipe_job` (Part C; one fix covers #3 and #4).
- **Suggested fix:** mint a unique per-sweep id (e.g. `DRY_RUN_UNTITLED:<uuid>` or a fresh `pipeline_run_id`) and thread it through `open_registry`, `prepare_pipe_job(pipeline_run_id=...)`, and `close_registry`. This also scopes the trace read to an empty dir (TODOS #4). Verify the synthetic dry-LLM report (`content_generator_dry`) still finds its registry.

### C-2 — `/build/inputs` and `/build/output` leak `validate_bundle`'s library on every success (Med-high)

- **Repo / where:** pipelex-api — `api/routes/pipelex/build/inputs.py` and `api/routes/pipelex/build/output.py` (the `validate_bundle(...)` call followed by a second `library_manager.open_library()` + `load_from_blueprints(...)`; `finally` tears down only the second library).
- **What:** `validate_bundle()` opens a library and, on success, deliberately keeps it **loaded + current** (its `finally` tears down only `if not success` — the D6 loaded-on-success contract, intended for callers that *reuse* it). But these routes do **not** reuse it: they `open_library()` a **second** library, `set_current_library(B)`, `load_from_blueprints(B)`, and the route's `finally` tears down only B. `validate_bundle`'s library A is orphaned in the process-global `LibraryManager._libraries`.
- **Failure scenario:** every successful `/build/inputs` and `/build/output` leaks one fully-loaded `Library` (plus its pipe maps / blueprints / crate caches) for the process lifetime. Under sustained build traffic the runner's memory grows unbounded. Output is still correct (`get_required_pipe` reads current-library = B).
- **Scope:** the double-open is **pre-existing**. Phase 3b's `allow_signatures=True` **widens** it: signature bundles that previously raised (and thus self-cleaned via `validate_bundle`'s `not success` teardown) now succeed and leak. `/build/runner` does **not** have this leak (single open).
- **Suggested fix (self-contained, lives in pipelex-api):** stop double-loading. Either (a) reuse the library `validate_bundle` leaves open on success — `validate_bundle` returns the loaded pipes; read the target pipe from the already-current library and drop the second `open_library`/`load_from_blueprints`; or (b) if a fresh library is genuinely needed, tear down `validate_bundle`'s library too. Option (a) also resolves Q-5 (the redundant re-parse). Cross-check the loaded-on-success contract: `validate_bundle` leaves the library current, so `get_required_pipe(pipe_code)` should already resolve against it without re-loading.

### C-3 — `/build/runner` now SKIPs cross-package-unresolved pipes instead of rejecting (Med — decision, not a bug)

- **Repo / where:** pipelex-api — `api/routes/pipelex/build/runner.py` (the replaced per-pipe loop).
- **What:** OLD code ran `pipe.validate_with_libraries()` per pipe **outside any try**, so a cross-package `PipeNotFoundError` (a controller resolving a sub-pipe in an unloaded package) propagated uncaught and **rejected** the `/build/runner` request. NEW `BundleValidator.validate_pipes` step 1 catches that exact `PipeNotFoundError`, records the pipe **SKIPPED**, and continues; `generate_runner_code` reads only `pipe.output`/`pipe.inputs` and never resolves sub-pipes, so the route returns **200 with generated runner code** for a pipe whose cross-package dependency it previously rejected.
- **Failure scenario:** a multi-file `/build/runner` request whose controller references a sub-pipe in a package not included in `mthds_contents`: OLD → rejected (caller learns the dep is unresolved); NEW → 200 + runner code for a pipeline that cannot actually run.
- **Scope / decision:** this is the **intended consolidation semantics** — it aligns `/build/runner` with `/validate`, `/build/inputs`, `/build/output`, which already used `validate_pipes` (cross-package SKIPPED tolerance, D6 / Phase-3a finding #1) before this diff. The open question was product-level: **is SKIPPED-and-emit-code the right default for a code-generation endpoint?**
- **DECISION (2026-06-02): add the targeted guard.** `/build/runner` must **reject** when the *requested* `pipe_code` itself lands SKIPPED (its own cross-package dep is unresolved) — emitting runner code for a pipe we couldn't resolve is a footgun for a codegen endpoint. Other, unrelated SKIPPED pipes in the bundle stay tolerated. Implementation: `validate_pipes` returns a per-pipe status map; after the sweep, look up `request_data.pipe_code` (match on bare `code` or `pipe_ref`) and if its status is `SKIPPED`, raise a clear error (mention the unresolved dependency) instead of proceeding to `generate_runner_code`.

### C-4 — committed editable `../_sig` pin breaks any non-local checkout (Release-blocking — intentional)

- **Repo / where:** pipelex-api — `pyproject.toml` (`pipelex = { path = "../_sig", editable = true }`) + `uv.lock` (`source = { editable = "../_sig" }`).
- **What:** the `pipelex` dependency pin was swapped from a GitHub git-rev to an editable local sibling path for co-development.
- **Failure scenario:** a clean checkout / CI (`tests-check.yml`) / Docker build (`uv sync --frozen`) cannot resolve `../_sig` (outside the build context) → dependency resolution fails; pipelex-api CI stays red.
- **Scope / action:** **intentional and documented** (D2 lock-step, no compat shim; see [`../../TODOS.md`](../../TODOS.md) Phase 3b open box). **Must flip to the merged pipelex git rev when the consolidation branch lands** — this is the gating action for the pipelex-api PR turning green. Not a code defect; a release-coordination checklist item.

### C-5 — `temporal_enabled=False` test fixture — original "masks a prod gap" claim REFUTED (corrected 2026-06-02)

- **Repo / where:** pipelex-api — `tests/unit/conftest.py` (autouse `reset_api_config_fixture`).
- **Verdict: the stated mechanism is wrong.** The fixture is real and autouse, but it does **not** mask a "validation dispatches a Temporal workflow" production gap — **no such dispatch exists at this layer.** `BundleValidator.validate_pipes` runs DRY **in-process regardless of the Temporal flag**.
- **Why (two independent reasons, both verified):**
  1. `BundleValidator` deliberately constructs a *direct* `PipeRun` (`bundle_validator.py`) whose `run` calls `pipe_router.run` inline — it **bypasses** the hub's Temporal-capable `get_pipe_run()` seam. Only the top-level `PipelexRunner` reaches `get_pipe_run()` (the thing the hub swaps for `make_temporal_pipe_run()` when Temporal is enabled). Controllers recurse via the in-process `get_pipe_router().run(...)`, not `get_pipe_run()`.
  2. The DRY **leaf** operators force `ContentGeneratorDry()` (`pipe_llm.py`, `pipe_img_gen.py`, `pipe_extract.py`, `pipe_structure.py`, `pipe_compose.py`), so a DRY run never reaches `ContentGeneratorInWorkflow` — the only thing that dispatches `act_llm_gen_*` activities.
  - The team's own design doc says exactly this: `D-plan.md` §3.5 ("DRY never dispatches an activity even under a Temporal hub") and §4.8 ("under a Temporal hub, a DRY run mocks inline and never dispatches `act_llm_gen_*`").
- **Why the original claim arose:** it faithfully restated the commit message for `56ca06a`, whose rationale ("validate_pipes routes DRY through PipeRun.run, which under Temporal would dispatch the sweep to a workflow") is inaccurate against the code and the design docs.
- **What the fixture actually does (and why it's fine to keep):** it pins local dev runs to the CI config, suppressing a developer's gitignored Temporal override so the unit suite stays hermetic. Keep it.
- **Corrected action:** there is **no** "land Part B before enabling Temporal on the runner API" ordering constraint implied by validation — enabling Temporal will **not** make validation sweeps dispatch workflows. (Part B / [`followup-leaf-run-mode-mock.md`](followup-leaf-run-mode-mock.md) is still wanted to make DRY *honor* the backend in general — a separate goal, not a gate on this consolidation.) The CHECKPOINT B handoff note in [`../../TODOS.md`](../../TODOS.md) that cites this gate should be softened accordingly.

---

## Already fixed this session

### R-LINT — ruff I001 import order (☑ fixed, commit `0ed98d11`)

The `from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError` import added in `24f9f9ca` was placed before the `pipelex.cli.*` block; ruff isort sorts it after. It was missed because `make agent-check` on `_sig` was last run *before* that edit (the subsequent `make agent-test` runs pytest, not ruff, so it didn't catch it). Reordered; `make agent-check` re-run clean on `_sig`. **Lesson:** re-run `make agent-check` after the *final* edit in a session, not just after the first code change.

---

## Cleanup (optional — low priority, all in pipelex-api unless noted)

- **Q-1 — shared request base.** `allow_signatures: bool = Field(default=False, description=...)` (incl. the verbatim multi-line description) is copy-pasted into all four request models, which already duplicate `mthds_contents` + the `_bound_each_file` validator. Extract a `MthdsContentsRequest(BaseModel)` base in the existing `api/schemas/models.py` ("Shared request/response models for API routes") carrying `mthds_contents` + `allow_signatures` + `_bound_each_file`; the build models add `pipe_code`, output adds `format`. Cost today: the description feeds public OpenAPI docs and can drift across endpoints; the size-limit validator change must be applied 4×.
- **Q-2 — tighten the weak assertion.** `tests/unit/test_allow_signatures.py` `test_signatures_rejected_by_default`: `"allow" in detail.lower() or "signature" in detail.lower()` is near-tautological (the message always contains "PipeSignature" and ends with "--allow-signatures"). Assert the actionable phrase directly (e.g. require `"signature"` for all routes, or `--allow-signatures` for the `/build/runner` raw-error case). Verify the wrapped `ValidateBundleError` detail still contains the chosen substring on the validate/inputs/output routes before tightening.
- **Q-3 — share `_build_client()`.** Duplicated **verbatim** between `tests/unit/test_allow_signatures.py` and `tests/unit/test_build_and_agent_routes.py`. ⚠️ Correction: the original "~9 other modules" claim is overstated — the other 8 `_build_client` definitions are **signature/purpose variants** (different params, different apps), not verbatim copies. Only these two are foldable; move the no-arg full-router variant to `tests/unit/conftest.py`.
- **Q-4 — don't blindly fold.** ⚠️ Correction: `test_build_runner_generates_code_for_bundle_with_signatures_when_opted_in` overlaps the parametrized allow case (`/build/runner` allow=true → 200) **only on the status check**; it adds unique body assertions (`success is True`, `pipe_code == "caller_seq"`, non-empty `python_code`) the parametrized case lacks. So it is **not** dead weight — at most, move those body assertions into the parametrized case (guarded on path); do not just delete it.
- **Q-5 — stop the double-parse / whole-bundle dry-run.** `/build/inputs` and `/build/output` call `validate_bundle(mthds_contents=...)` (dry-runs ALL pipes, no scope) then re-`load_from_blueprints` to read one pipe. Pass `dry_run_pipe_codes=[request_data.pipe_code]` to scope the sweep and reuse the already-open library — resolves this and C-2 together. `allow_signatures=True` makes the unscoped sweep costlier (now sweeps signature pipes too).
- **Q-6 — share MTHDS test bundles.** `SIGNATURE_MTHDS` / `VALID_MTHDS` literals are inlined per test module; `tests/unit/_constants.py` ("Shared constants for unit tests") is the home.
- **Q-7 — (pipelex) lighter domain assertion.** `tests/unit/pipelex/cli/test_agent_output.py` `test_agent_error_includes_signature_hint` constructs a full `SignaturesNotAllowedError(...)` just to pass as `cause`; it only asserts hint + `error_domain == "input"`. ⚠️ Correction: the constructor **requires all three args** (`offending_pipe_refs`, `signature_refs`, `dep_paths` — no defaults), so the "full" build is already the minimum the constructor allows; the only available trim is passing empty `set()/set()/{}`. Cosmetic at best — low value.

---

## Refuted during review (do not re-chase without new evidence)

- **Missing `docs/errors/signatures-not-allowed-error.md`.** The page was already absent at the pre-Phase-3b commit `aeeac8bf` (pre-existing), `doc-check.yml` only runs `mkdocs build --strict` (it does not regenerate/diff error pages), and this diff is docs-neutral. Not introduced by Phase 3b.
- **`test_agent_output_drift` blind spot** (claim: `_EXCEPTION_MODULES` omits `pipe_signature.exceptions`, so the drift guard never evaluates `SignaturesNotAllowedError`). Refuted — the drift test **did** fire on this class during the session (it's discovered via the error-module eager-load), which is exactly why the redundant `AGENT_ERROR_DOMAINS` entry had to be removed.
