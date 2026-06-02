# Phase 3b — code-review follow-ups (pipelex-api migration + `allow_signatures`)

Findings from an xhigh-recall `/code-review` of the Phase 3b work (CHECKPOINT B). Captured here so a fresh session can triage them without re-running the review. Nothing in this doc has been applied **except** finding R-LINT (the ruff import-order fix), which already landed.

## What was reviewed

The cross-repo diff for Phase 3b of the dry-run consolidation:

- **pipelex-api** (`feature/Update-dry-run-api`, commit `56ca06a`): `/build/runner` migrated from `dry_run_pipes` to `BundleValidator().validate_pipes(...)`; an `allow_signatures` request field added to all four validation routes (`/validate`, `/build/runner`, `/build/inputs`, `/build/output`); the test autouse fixture forced `temporal_enabled=False`; integration tests added.
- **pipelex** (`_sig`, `feature/Validate-with-signatures-4-fix-dry-run`): `SignaturesNotAllowedError` reclassified `error_domain = INPUT` (commit `24f9f9ca`); ruff import-order fix (commit `0ed98d11`); CHECKPOINT B recorded in [`../../TODOS.md`](../../TODOS.md) (commit `a49fa98a`).

Both repos: `make agent-check` clean, `make agent-test` green at review time.

> **Cold-start note.** This doc lives in the **pipelex** repo (`_sig`), but several fixes target the **pipelex-api** repo (`../pipelex-api`). Each finding names its repo. **Line numbers are indicative — verify by symbol.** None of the correctness findings were introduced by Phase 3b's *logic*; the diff re-exposes or widens pre-existing infrastructure issues, which recall-mode surfaces.

## Status at a glance

| ID | Sev | Repo | Where | Status | Note |
|---|---|---|---|---|---|
| C-1 | High | pipelex | `pipeline/bundle_validator.py` `validate_pipes` | ☐ open | Pre-existing; tracked as Part-C / TODOS finding #3–#4. Diff newly exposes `/build/runner`. |
| C-2 | Med-high | pipelex-api | `build/inputs.py`, `build/output.py` | ☐ open | Pre-existing double-open library leak; `allow_signatures=True` widens it. Self-contained fix. |
| C-3 | Med | pipelex-api | `build/runner.py` | ☐ decision | Behavior loosening (cross-package dep → SKIPPED→200, was reject). Intended consolidation semantics — **confirm OK**. |
| C-4 | Release-block | pipelex-api | `pyproject.toml` + `uv.lock` | ☐ at-merge | Editable `../_sig` pin — intentional D2 lock-step; **must flip to merged pipelex rev before merge**. |
| C-5 | Med (altitude) | pipelex-api | `tests/unit/conftest.py` | ☐ open | `temporal_enabled=False` masks that DRY validation dispatches via `PipeRun.run` → Temporal. Real fix = deferred Part B. |
| R-LINT | — | pipelex | `tests/unit/pipelex/cli/test_agent_output.py` | ☑ fixed | ruff I001 import order — fixed in `0ed98d11`. |
| Q-1 | Low | pipelex-api | 4× request models | ☐ open | `allow_signatures` field + description copy-pasted 4×; extract shared base. |
| Q-2 | Low | pipelex-api | `tests/unit/test_allow_signatures.py` | ☐ open | Near-tautological detail assertion; tighten. |
| Q-3 | Low | pipelex-api | test modules | ☐ open | `_build_client()` duplicated; move to conftest. |
| Q-4 | Low | pipelex-api | `tests/unit/test_allow_signatures.py` | ☐ open | Redundant runner-codegen test overlaps parametrized case. |
| Q-5 | Low-med | pipelex-api | `build/inputs.py`, `build/output.py` | ☐ open | Double-parse + whole-bundle dry-run for one pipe (overlaps C-2). |
| Q-6 | Low | pipelex-api | test modules | ☐ open | `SIGNATURE_MTHDS`/`VALID_MTHDS` inlined; move to `tests/unit/_constants.py`. |
| Q-7 | Very low | pipelex | `tests/unit/pipelex/cli/test_agent_output.py` | ☐ open | Test builds a full exception just to read a class attr. |

Legend: ☐ open · ☑ fixed · "decision"/"at-merge" = needs a human call, not a code fix.

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
- **Scope / decision:** this is the **intended consolidation semantics** — it aligns `/build/runner` with `/validate`, `/build/inputs`, `/build/output`, which already used `validate_pipes` (cross-package SKIPPED tolerance, D6 / Phase-3a finding #1) before this diff. The open question is product-level: **is SKIPPED-and-emit-code the right default for a code-generation endpoint**, or should `/build/runner` reject when the *requested* pipe (or its transitive deps) is unresolved? Decide and either accept (document) or add a targeted check in the route that the requested `pipe_code` was not SKIPPED.

### C-4 — committed editable `../_sig` pin breaks any non-local checkout (Release-blocking — intentional)

- **Repo / where:** pipelex-api — `pyproject.toml` (`pipelex = { path = "../_sig", editable = true }`) + `uv.lock` (`source = { editable = "../_sig" }`).
- **What:** the `pipelex` dependency pin was swapped from a GitHub git-rev to an editable local sibling path for co-development.
- **Failure scenario:** a clean checkout / CI (`tests-check.yml`) / Docker build (`uv sync --frozen`) cannot resolve `../_sig` (outside the build context) → dependency resolution fails; pipelex-api CI stays red.
- **Scope / action:** **intentional and documented** (D2 lock-step, no compat shim; see [`../../TODOS.md`](../../TODOS.md) Phase 3b open box). **Must flip to the merged pipelex git rev when the consolidation branch lands** — this is the gating action for the pipelex-api PR turning green. Not a code defect; a release-coordination checklist item.

### C-5 — `temporal_enabled=False` in the test fixture masks a production-relevant gap (Med — altitude)

- **Repo / where:** pipelex-api — `tests/unit/conftest.py` (autouse `reset_api_config_fixture`).
- **What:** forcing Temporal off makes the suite hermetic and runs dry-run validation in-process. But the underlying reason it's *needed* is that `BundleValidator.validate_pipes` routes DRY through `PipeRun.run`, which **honors the configured backend**. When `temporal.is_enabled = true`, a dry-run/validation sweep dispatches a `dry_run_untitled` workflow to Temporal.
- **Failure scenario:** Temporal ships to the runner API (`pipelex-api-deploy` sets `is_enabled = true`) **before** the deferred Part B lands → `/validate` and `/build/*` dispatch each validation sweep to Temporal as a real workflow instead of mocking in-process: added latency, worker load, and a hard failure if no worker/server is reachable. The Temporal-off test suite never catches this.
- **Scope / fix:** the test flag is the **correct minimal step for this branch** (the consolidation ships in-process). The deep fix is the deferred **leaf-level run-mode mock** — see [`followup-leaf-run-mode-mock.md`](followup-leaf-run-mode-mock.md) ("DRY honors the backend", Part B, unstarted). **Action:** before enabling Temporal on the runner API, land Part B; until then, keep `temporal.is_enabled = false` in the deployed pipelex-api config (it already is). Already noted in the CHECKPOINT B handoff in [`../../TODOS.md`](../../TODOS.md).

---

## Already fixed this session

### R-LINT — ruff I001 import order (☑ fixed, commit `0ed98d11`)

The `from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError` import added in `24f9f9ca` was placed before the `pipelex.cli.*` block; ruff isort sorts it after. It was missed because `make agent-check` on `_sig` was last run *before* that edit (the subsequent `make agent-test` runs pytest, not ruff, so it didn't catch it). Reordered; `make agent-check` re-run clean on `_sig`. **Lesson:** re-run `make agent-check` after the *final* edit in a session, not just after the first code change.

---

## Cleanup (optional — low priority, all in pipelex-api unless noted)

- **Q-1 — shared request base.** `allow_signatures: bool = Field(default=False, description=...)` (incl. the verbatim multi-line description) is copy-pasted into all four request models, which already duplicate `mthds_contents` + the `_bound_each_file` validator. Extract a `MthdsContentsRequest(BaseModel)` base in the existing `api/schemas/models.py` ("Shared request/response models for API routes") carrying `mthds_contents` + `allow_signatures` + `_bound_each_file`; the build models add `pipe_code`, output adds `format`. Cost today: the description feeds public OpenAPI docs and can drift across endpoints; the size-limit validator change must be applied 4×.
- **Q-2 — tighten the weak assertion.** `tests/unit/test_allow_signatures.py` `test_signatures_rejected_by_default`: `"allow" in detail.lower() or "signature" in detail.lower()` is near-tautological (the message always contains "PipeSignature" and ends with "--allow-signatures"). Assert the actionable phrase directly (e.g. require `"signature"` for all routes, or `--allow-signatures` for the `/build/runner` raw-error case). Verify the wrapped `ValidateBundleError` detail still contains the chosen substring on the validate/inputs/output routes before tightening.
- **Q-3 — share `_build_client()`.** Duplicated verbatim between `tests/unit/test_allow_signatures.py` and `tests/unit/test_build_and_agent_routes.py` (and a variant in ~9 other modules). Move the no-arg full-router variant to `tests/unit/conftest.py` as a fixture/factory.
- **Q-4 — fold the redundant test.** `test_build_runner_generates_code_for_bundle_with_signatures_when_opted_in` overlaps the parametrized allow case (`/build/runner` allow=true → 200). Fold the `python_code`/`success` body assertions into the parametrized case (guarded on path) or drop it.
- **Q-5 — stop the double-parse / whole-bundle dry-run.** `/build/inputs` and `/build/output` call `validate_bundle(mthds_contents=...)` (dry-runs ALL pipes, no scope) then re-`load_from_blueprints` to read one pipe. Pass `dry_run_pipe_codes=[request_data.pipe_code]` to scope the sweep and reuse the already-open library — resolves this and C-2 together. `allow_signatures=True` makes the unscoped sweep costlier (now sweeps signature pipes too).
- **Q-6 — share MTHDS test bundles.** `SIGNATURE_MTHDS` / `VALID_MTHDS` literals are inlined per test module; `tests/unit/_constants.py` ("Shared constants for unit tests") is the home.
- **Q-7 — (pipelex) lighter domain assertion.** `tests/unit/pipelex/cli/test_agent_output.py` `test_agent_error_includes_signature_hint` constructs a full `SignaturesNotAllowedError(...)` just to pass as `cause`; it only asserts hint + `error_domain == "input"`. Could assert against `SignaturesNotAllowedError.error_domain` directly and keep the cause minimal, so a constructor-signature change doesn't break a domain test.

---

## Refuted during review (do not re-chase without new evidence)

- **Missing `docs/errors/signatures-not-allowed-error.md`.** The page was already absent at the pre-Phase-3b commit `aeeac8bf` (pre-existing), `doc-check.yml` only runs `mkdocs build --strict` (it does not regenerate/diff error pages), and this diff is docs-neutral. Not introduced by Phase 3b.
- **`test_agent_output_drift` blind spot** (claim: `_EXCEPTION_MODULES` omits `pipe_signature.exceptions`, so the drift guard never evaluates `SignaturesNotAllowedError`). Refuted — the drift test **did** fire on this class during the session (it's discovered via the error-module eager-load), which is exactly why the redundant `AGENT_ERROR_DOMAINS` entry had to be removed.
