# Orchestrator-agnostic runner & deployment flavors — implementation TODOS

**Effort:** make `pipelex-api` an orchestrator-agnostic base, then build N thin deployment flavors on top of it (Temporal today, Mistral next). The *consumer-side* sequel to the plugin-system externalization (that tracker is archived at [`wip/archive/plugin-system-implementation-tracker.md`](wip/archive/plugin-system-implementation-tracker.md)).

**Status:** **Phases A + B + C DONE (committed & pushed) + two post-C follow-on extensions DONE (pushed).** Phase A/B core seams (`pipelex`: `4b5449f88` Phase A, `75196e2e3` seam refinement, `7378afdd8` Phase B docs; `pipelex-temporal` `6d9adff`). **Phase C** = `pipelex-api` made orchestrator-agnostic, commit **`a39841e`** on `refactor/orchestrator-agnostic-base` (cut from `dev`): F1 execution via the orchestrator-registry hub seam (byte-equivalent — see the F1 deviation note in the as-built), F2 validate always DIRECT, F3 exception-handler mappers consumed at app construction, `[api]` config = Option C `api.toml` via `load_plugin_config`, `temporal` extra dropped. Clean-context `/code-review`s + all gates green (308 tests, pyright 0, mypy 0, pylint 10, openapi-check). **MAJOR GATE 2 / Checkpoint C (THE gate) cleared.** **Follow-on extension plans then landed on top of Phase C** (their own plan docs + `feature/*` branches — see "Follow-on extensions" below): orchestrator-dispatched `/validate` (reverses/extends F2), per-request `execution_mode` on `/execute` (extends F1, **PR #27**), and `/start` deriving the fire-and-forget variant of `execution_mode` (`f5e3ef7` + review fixes `7e4bc13`). **NEXT = Phase D** (`pipelex-api-hosted` Temporal flavor — MAJOR GATE 3), unchanged by the follow-ons. The in-`pipelex` plugin-system foundation (seams inverted, Temporal externalized, `plugins.boot_orchestrator` gate) was done earlier on `refactor/Plugins-3`.

**Current branches:** the follow-on work + this tracker live on **`feature/Orchestrator-dispatched-validate`** — `pipelex` (`_plugins`) and `pipelex-temporal` (tip `459e04d`). `pipelex-api` is a stack: `a39841e` (Phase C, `refactor/orchestrator-agnostic-base`) → `72c0efc` (validate, `feature/Orchestrator-dispatched-validate`) → `feature/Execute-per-request-mode` (execute **PR #27** `191c900`, then `/start` f&f derivation `f5e3ef7` + review fixes `7e4bc13`, **tip `7e4bc13`**). The PR #27 stack through `191c900` is pushed/CI-green; `f5e3ef7` + `7e4bc13` and this tracker update are **not pushed**. Phase D onward each lands in its own repo/branch.

### Follow-on extensions (post-Phase-C — DONE; not part of the original A–F phases)

Extension plans written + executed **after** Phase C; each has its own plan doc and `feature/*` branch line. They do **not** change the D/E/F roadmap below.

- **Orchestrator-dispatched `/validate`** — plan [`wip/plugins/orchestrator-dispatched-validate.md`](wip/plugins/orchestrator-dispatched-validate.md). **Reverses/extends F2:** `/validate` is now `execution_mode`-aware via a NEW per-call `BundleValidatorRegistry` seam (mirrors `OrchestratorRegistry`) — `direct` validates in-process (F2 kept for the agnostic base), `temporal_*` dispatches the whole job to a worker. Verdict-as-value (`ApiRunner.validate` override removed → `validate_verdict`; route discriminates on `isinstance(verdict, PipelexValidationReport)`). Landed across all 3 repos on `feature/Orchestrator-dispatched-validate`: core PR **#998** (CI-green + Greptile-happy), `pipelex-api` tip **`72c0efc`**, `pipelex-temporal` tip **`459e04d`**. **DONE.**
- **Per-request `execution_mode` on `/execute`** — plan [`wip/plugins/execute-per-request-execution-mode.md`](wip/plugins/execute-per-request-execution-mode.md) (+ `execute-per-request-mode-deferred.md`). **Extends F1:** `/execute` now dispatches by resolved `execution_mode` through the `OrchestratorRegistry` (symmetric with `/start`), rejects fire-and-forget with a 400, and rehydrates the orchestrator's JSON-safe output back into the full `PipeOutput`. **`pipelex-api`-only** (reuses the existing seam — no core/temporal change). **PR #27** (`feature/Execute-per-request-mode` → `feature/Orchestrator-dispatched-validate`, tip **`191c900`**): CI green, Greptile 5/5, gstack `/review` merge-ready; **not merged (user's call).** Deferred items in `wip/plugins/execute-per-request-mode-deferred.md` (DIRECT round-trip cost; pre-existing `/start` resource leak; `/start` schema gap + dangling-`#/$defs/` OpenAPI ref pattern; failing-pipe error double-wrap via the shared seam).
  - **CI gotcha (any `pipelex-api` PR on these branches):** the editable `pipelex = ../_plugins` pin breaks CI (no sibling worktree on the runner). Fix = pin core to a **git+https SHA** in `pyproject.toml` `[tool.uv.sources]` (core repo is PUBLIC → no creds) + relock `uv.lock`; flip back to the PyPI `==` pin at release. Done on PR #27 as `c60be1f` (pinned to core `51ff09417`).
- **`/start` derives the fire-and-forget variant of `execution_mode`** — commit **`f5e3ef7`** (+ review fixes **`7e4bc13`**) on `feature/Execute-per-request-mode`, stacked on PR #27. **Endpoint, not deployment:** fire-and-forget vs blocking is a property of the *endpoint*. A deployment configures ONE *synchronous* `execution_mode`; `/execute` + `/validate` dispatch it as-is, while `/start` derives its f&f sibling (`temporal_blocking → temporal_fire_and_forget`; `direct`/`mistral_native` have none → dispatched unchanged, blocking). Kills the `/execute` 400 / forced-direct footgun — one coherent mode across all three endpoints. Route-local `_async_start_mode` (kept off the core enum per smallest-surface). **`pipelex-api`-only** (no core/temporal change). **xhigh-workflow `/code-review` + fixes (`7e4bc13`):** (1) `ApiConfig` now rejects a *configured* f&f `execution_mode` (field validator on `is_fire_and_forget`) — the docs declared it unconfigurable but nothing enforced it (a baked f&f would 400 every `/execute` + misroute `/validate`); fail-fast at load, per-request f&f override on `/start` still allowed (policy-gated). (2) Corrected the `mistral_native` `workflow_id` claim in the `_async_start_mode` docstring + call-site comment + `configuration.md` — `mistral_native` runs per-call and answers with a *non-null* `workflow_id` (the run id); only `direct` returns `None`. (3) Added a pure-mapping test of `_async_start_mode` over every mode + a `mistral_native` end-to-end `/start` case (both previously unverified despite the test docstring claiming the coverage); `test_api_config`'s locked-Temporal helper switched to the synchronous `temporal_blocking` + a configured-f&f-rejection test added. Gates green (ruff/pyright 0/mypy 0/pylint 10, full unit suite pass, OpenAPI in sync). Review verdict: the F1-gate ordering (403 runs *before* the f&f derivation) and single-caller transform are correct; deferred low-priority items (route-local-vs-enum altitude; a custom blocking-only orchestrator plugin now needs a f&f arm for `/start`) noted as by-design. **DONE; not pushed.**

---

This is the **execution tracker**. The *why* and *how* live in [`wip/plugins/orchestrator-agnostic-runner-and-flavors.md`](wip/plugins/orchestrator-agnostic-runner-and-flavors.md) (the reviewed, decision-locked plan). **Read that doc before starting any phase** — this file tracks progress against it; it does not replace it. **Resuming in a fresh session?** Start with [`wip/plugins/resume-and-verify-state.md`](wip/plugins/resume-and-verify-state.md) — paste-ready orientation + commands to verify the state against the repos before doing anything. Adjacent background: [`wip/plugins/temporal-config-out-of-core.md`](wip/plugins/temporal-config-out-of-core.md) (the boot-gate refactor that immediately precedes this work) and the plugin-system design/SPI docs in [`wip/plugins/`](wip/plugins/).

> **How to use this file.** Tick boxes as you land work. **Do not skip a `🛑 CHECKPOINT`** — each is a hard stop with three mandatory actions (verify · capture cold-start context · fan-out `/code-review`). Three checkpoints are flagged **MAJOR GATE** — they are the points the source plan calls out as the ones that must hold before the effort can continue.
>
> **Fan-out convention for `/code-review`.** Spawn each review sub-agent with **no inherited context** — hand it only a pointer to the changes under review (the phase's commit SHA, `git diff <base>..HEAD`, or the unstaged/working-tree files), never the plan, the rationale, or your own conclusions. A clean-context reviewer reviews the code as written, not your story about it — that independence is the point of fanning it out.

---

## Cold-start primer (read this first if you're new to the session)

**Goal of the whole effort:** today `pipelex-api` is wired directly to Temporal in production code — it is *not* an orchestrator-agnostic runner. Make the public `pipelex/pipelex-api` base name **no** orchestrator (ship only the in-process/direct path), then express each deployment as **base image + exactly one orchestrator plugin + that plugin's activation**. That is what lets a Temporal flavor (`pipelex-api-hosted`) and a future Mistral flavor (`pipelex-api-mistral`) both exist on one base.

**The model shift — internalize before touching any repo.** The plugin system split a previously-monolithic idea ("Temporal is on") into orthogonal concepts:

- **Presence** = the plugin distribution is installed, so its `pipelex.plugins` entry point is discovered at boot and `register()` runs, contributing its `execution_mode` arms to the orchestrator registry. Presence makes a mode *dispatchable*; it does **not** make it *used*.
- **Activation** = the runtime is told to use it. It decomposes into **two independent knobs that are not derivable from each other:**

| Knob | Owns | Set by | Temporal | Mistral | Direct |
|---|---|---|---|---|---|
| `execution_mode` | which mode a *top-level* run dispatches as, through the bridge | runner config default + optional per-request override | `temporal_blocking` / `temporal_fire_and_forget` | `mistral_native` | `direct` |
| `plugins.boot_orchestrator` | whether to claim the process-global hub slots (content generator / pipe router / pipe run / task manager) at boot | deployment config TOML | `"temporal"` | *unset* | *unset* |

**Mistral is the proof the two knobs are independent.** A Temporal deployment needs *both* (the boot gate stands up the Temporal client/task-manager the orchestrator enqueues against; `execution_mode` tells the bridge to enqueue). A Mistral deployment needs **only** `execution_mode = mistral_native` — its plugin claims **no** hub slots (self-contained per-call orchestrator), so there is no boot gate to set. A plain in-process deployment sets neither.

**Boot-global vs per-call orchestrators** — *why* the two knobs exist. A **boot-global** orchestrator (Temporal) replaces process-wide execution machinery → must claim hub slots at boot, gated by `boot_orchestrator`. A **per-call** orchestrator (Mistral) only adds a dispatch arm → presence is enough; selection is per-run via `execution_mode`. Classify any new orchestrator first; the classification decides whether `boot_orchestrator` is even meaningful for it.

**Install channel follows license, not convenience.**

- `pipelex-temporal` is **private** → pinned `git+ssh` ref (precedent: `pipelex-shared @ git+ssh://…/infra-python-tools.git@<ref>`). Only **private** images may pin it.
- `pipelex-mistralai-workflows` is **public** → plain PyPI (`pipelex-mistralai-workflows==X`). Currently pre-publish; gated on its own `mistralai-2.x` work — treat as PyPI once published.

**Verified anchors (2026-06-21, this worktree)** — the plan's foundations are present and current:

- `plugins.boot_orchestrator` gate exists: `configs.py:258`, applied in `pipelex.py:206-207` (only overridden when the param is non-`None`, so a TOML value is **preserved** — D1 safe).
- Plugin contract: `PLUGIN_API_VERSION = 1` (`pipelex/plugins/contract.py:10`); `PluginRegistrar` already hosts `add_inference_backend` / `add_model_lister` / `add_orchestrator` / `claim_*` / `add_teardown` (no `add_cli_command` — removed by Option A). F3 adds one method here.
- `ErrorReport` is a core type (`pipelex/base_exceptions.py:309`) → F3's mapper signature uses it (no FastAPI in core).
- Config loader env-layering pattern to mirror for D2: `ConfigManager._override_files_for_dir` / `load_config` (`pipelex/system/configuration/config_loader.py`), keyed on `runtime_manager.environment`.
- The §2 gap is real and current: `pipelex-api/api/` still names temporal in `exception_handlers.py`, `routes/pipelex/validate.py`, `routes/pipelex/pipeline.py`. All sibling repos exist (`pipelex-temporal`, `pipelex-api`, `pipelex-api-hosted`, `pipelex-worker`, `pipelex-mistralai-workflows`).

**Locked decisions (D1, D2, F1, F2, F3)** — do not re-litigate; if you believe one is wrong, raise it explicitly before deviating. Full text in §3 of the source doc.

- **D1** — `boot_orchestrator` is set from the flavor's deployment TOML (`[plugins] boot_orchestrator = "temporal"`). No `pipelex-api` change for the gate; verified preserved by `setup()`.
- **D2** — plugin config files become env-aware, mirroring the main config. Add a **reusable core helper** so every plugin self-loads `name.toml` → `name_{env}.toml` → `name_override.toml` with deep-merge. `pipelex-temporal` adopts it. One image bakes all envs; `PIPELEX_ENV` selects at runtime.
- **F1** — `execution_mode` = runner config default + optional per-request override, gated by a per-deployment policy (a locked-down Temporal runner can refuse a caller forcing `direct`). Runner builds `PipelexPipeRunInput(execution_mode=…)` and dispatches via `run_pipe_via_bridge`; the bridge output already carries `workflow_id`, so async-start survives.
- **F2** — validate is **always DIRECT in-process** (`validate_bundles_in_process`). Drops the Temporal validate branch. **Behavior change:** the API runner now loads the method library to validate (prior design pushed that onto the worker) — document the resource/isolation implication on the hosted runner. **→ REVERSED / EXTENDED** by orchestrator-dispatched `/validate` (new per-call `BundleValidatorRegistry` seam): `/validate` is now `execution_mode`-aware — `direct` in-process (F2 kept for the agnostic base) | `temporal_*` dispatched to a worker (restored). Same canonical verdict either way. See [`wip/plugins/orchestrator-dispatched-validate.md`](wip/plugins/orchestrator-dispatched-validate.md).
- **F3** — orchestrator-specific HTTP error handling via a **new framework-agnostic plugin seam**: `PluginRegistrar.add_http_error_mapper(*, exc_type, to_error_report: Callable[[Exception], ErrorReport])`. The orchestrator plugin registers its transport-fault mapping; `pipelex-api` iterates the mappers at app construction and wraps each into a FastAPI handler using its existing RFC 7807 + `DisclosureMode` rendering. **FastAPI/Starlette stays only in `pipelex-api`; core and the plugin import neither.** Grows the contract by one optional capability → bump `PLUGIN_API_VERSION`.

**Delivery model (cross-repo).** Unlike the archived plugin-system tracker (one repo, one-commit-per-checkpoint, single PR), this effort spans repos. **Each phase lands in its own repo on its own branch as its own commit(s) + PR — there is no single cross-repo PR.** Ordering is load-bearing: the `pipelex` (A) and `pipelex-temporal` (B) enabling changes must land before `pipelex-api` (C) can consume the F3 seam.

**Local cross-pin strategy (for dev before anything is published/released):** pin editable across the chain so the seam can be exercised end-to-end locally — `pipelex-temporal` → editable `pipelex` (`[tool.uv.sources] pipelex = { path = "../_plugins", editable = true }`), and `pipelex-api` → editable `pipelex` (+ a synthetic in-test plugin to prove the F3 seam without importing `temporalio`). The published `==` / git+ssh pins are the release-time flip (Phases D–F).

**Commands** (from `_plugins/CLAUDE.md`, for the `pipelex` Phase-A work): `make agent-check` (lint/types — always after changes) · `make agent-test` (full suite, silent on success — at end of phase) · `make tb` (boot/config sanity — fast, after config or seam edits). Always use the venv: `.venv/bin/...`. Consumer repos use their own `make agent-check` / `make agent-test` (same family conventions).

---

## Image architecture (target — handles public + private plugins uniformly)

A **two-layer** build per flavor isolates plugin-install complexity (private SSH, version-locking) into one place and keeps the env-config layer trivial:

```
pipelex/pipelex-api:<ver>          (public base, orchestrator-agnostic, Docker Hub)
  ├─ flavored base = base + ONE plugin            (built once per flavor → private ECR)
  │     pipelex-api-temporal:<ver> = base + pipelex-temporal  (git+ssh)
  │     pipelex-api-mistral:<ver>  = base + pipelex-mistralai-workflows (PyPI)
  └─ env-config child = flavored base + COPY env TOMLs   (per env; config-only)
        pipelex-api-{dev,staging,prod}        (Temporal)
        pipelex-api-mistral-{dev,staging,prod}
```

**One parameterized install recipe.** Flavored-base Dockerfile takes `PLUGIN_SPEC` and always exposes a BuildKit SSH mount. PyPI plugin → plain install (SSH mount unused). Private plugin → `--mount=type=ssh` with the deploy key in the CI builder (`docker build --ssh default`); never bake a key into a layer. Install mechanics that bite (encode in the Dockerfile): base Python is a uv project venv at `/app/.venv` (install into it; don't let the resolver swap the pinned `pipelex`); the base purges `git`/`build-essential` in a late layer (re-add `git` + `openssh-client` before installing the private plugin); the plugin ref and base `pipelex` version are a **coupled pair that bump together** — track it in the flavor's version file.

---

## Phase A — Core enabling changes (`pipelex`, the `_plugins` worktree)

**Goal:** add the two seams `pipelex-api` will consume, in the public core, with no orchestrator named and no FastAPI imported. Lands on `refactor/Plugins-3`.

- [x] **D2 — env-aware plugin config loader.** Add a reusable helper on `ConfigManager` (e.g. `load_plugin_config(*, name, schema)`) resolving `name.toml` (the calling plugin's packaged default) → `name_{environment}.toml` → `name_override.toml` with deep-merge, mirroring `load_config`'s env layering. Anchor: `pipelex/system/configuration/config_loader.py` (`_override_files_for_dir` / `load_config`, keyed on `runtime_manager.environment`).
- [x] **F3 — HTTP-error-mapper seam.** Add `add_http_error_mapper(*, exc_type: type[Exception], to_error_report: Callable[[Exception], ErrorReport])` to `PluginRegistrar` (`pipelex/plugins/registrar.py`, alongside the existing menu methods) plus a read accessor for the collected mappers. Signature uses `ErrorReport` (`pipelex/base_exceptions.py`) — **no FastAPI import.**
- [x] **Bump `PLUGIN_API_VERSION`** (`pipelex/plugins/contract.py:10`, `1 → 2`) and document the new optional capability in the orchestrator SPI doc (`docs/under-the-hood/orchestrator-plugins.md`). Note the contract bump means every plugin's `targets_api` must be re-confirmed (built-ins + `pipelex-temporal` in Phase B).
- [x] **Tests:** env-layered plugin-config round-trip (packaged default → `_{env}` → `_override` deep-merge); registrar collects/returns mappers; import-light boot still green (the seam adds no SDK/HTTP import — extend the existing import-light subprocess guard if needed).

### 🛑 CHECKPOINT A — hard stop (core seams exist; consumed at B/C)

- [x] **Verify:** `make agent-check` clean · `make tb` green · `make agent-test` green. Core still names **no** orchestrator and imports **no** FastAPI (`grep -rn "fastapi\|starlette" pipelex/` → only telemetry labels + `WorkerMode.FASTAPI` enum, no imports; temporal refs in core unchanged). The seam's *end-to-end* exercise lands at Checkpoint B (when the plugin contributes through it) — don't expect integration proof here.
- [x] **Capture cold-start context:** append `### Phase A — as-built` below (final helper name/signature, the registrar method + accessor signature, the `PLUGIN_API_VERSION` value, which plugins' `targets_api` still need re-confirming, test locations).
- [x] **Fan-out `/code-review`:** sub-agent runs `/code-review` on the Phase A `pipelex` diff. Triage findings into the as-built (apply cheap ones; defer design-tradeoffs to a `wip/plugins/` follow-up per the deferral convention). _(done — verdict clean; nit #2 applied; tradeoff #1 deferred to `wip/plugins/phase-c-http-error-mapper-consumer-path.md`)_
- [x] **Commit** on `refactor/Plugins-4`. This is a natural session boundary before switching to the `pipelex-temporal` repo.

---

## Phase B — `pipelex-temporal` adopts the new seams (additive, private repo)

**Goal:** the private Temporal plugin uses the D2 helper and contributes through the F3 seam. Additive — no behavior change to its existing orchestrator/slot-claim contributions.

- [x] **D2 adoption.** Switch `load_temporal_config()` to the new helper; ship `temporal_{env}.toml` resolution (the packaged default `temporal.toml` stays). One image bakes all envs; `PIPELEX_ENV` selects.
- [x] **F3 mapper.** In `TemporalPlugin.register()`, register `temporalio.TemporalError → ErrorReport` classified transient / `RUNTIME` (port the classification currently in `pipelex-api`'s `handle_temporal_error`). Keep `register` import-light — via a lazy `exc_type_provider` thunk + a lazy SDK import, `register` imports no `temporalio` (the Phase A seam was refined to take the provider; see Phase A as-built "Why lazy").
- [x] **Re-confirm `targets_api`** matches the new `PLUGIN_API_VERSION` from Phase A. (`targets_api = PLUGIN_API_VERSION`, auto-tracks to 2 via the editable pin — verified by the suite running against the Phase A core.)
- [x] Pin editable `pipelex` (`../_plugins`) for local testing against the Phase A core. (Already present in `pyproject.toml` `[tool.uv.sources]`.)

### 🛑 CHECKPOINT B — hard stop · **MAJOR GATE 1** (source-doc Checkpoint 1)

- [x] **Verify:** `pipelex-temporal` `make agent-check` + `make agent-test` green against the Phase A `pipelex`. The seam now has a real consumer: a `pipelex-temporal` install contributes its mapper through `add_http_error_mapper` and self-loads `temporal_{env}.toml`. Import-light `register` still proven (no `temporalio` at registration) — subprocess blocks `temporalio` and runs `register` to completion.
- [x] **Capture cold-start context:** `### Phase B — as-built` appended below.
- [x] **Fan-out `/code-review`:** two forked `/code-review`s (core seam refinement + pipelex-temporal diff) — both **clean, no bugs**. Triage recorded in the Phase B as-built (one NIT applied: slot-claim count in the import-light test; rest deferred).
- [x] **Commit** in `pipelex-temporal` (`refactor/own-temporal-config`, `6d9adff`). Core seam refinement + Phase B docs on `refactor/Plugins-4` (`75196e2e3`, `7378afdd8`).

---

## Phase C — `pipelex-api` decoupling (the big one, public Docker Hub)

**Goal:** make the base orchestrator-agnostic. **No `pipelex.temporal.*`, no `temporalio`, anywhere in `api/`.** Each of F1/F2/F3 removes one of the §2 coupling sites.

- [x] **Execution (F1).** Rewrite `ApiRunner.start()` (`api/routes/pipelex/pipeline.py`). **DEVIATION (flagged in as-built):** dispatch via `get_orchestrator_registry().get_optional(mode=execution_mode).run(pipe_job, delivery_assignment)` (the identical final dispatch `run_pipe_via_bridge` performs) fed the **rich** `pipeline_run_setup` job — NOT `PipelexPipeRunInput`+`run_pipe_via_bridge`, which is lossy (drops `request_id`/`output_multiplicity`/`dynamic_output_concept_ref`/registration/telemetry) and would need a forbidden 2nd core change to fix. `workflow_id` off `run_output`. `execution_mode` from `api.toml` (Option C) + per-request override gated by `allow_request_execution_mode_override`. `make_temporal_pipe_run` import/usage gone. (`execute` was already agnostic via the `get_pipe_run()` hub slot — untouched.)
- [x] **Validate (F2).** Collapsed `ApiRunner.validate()` to the single `validate_bundles_in_process` path. Deleted the `temporal.is_enabled` branch + `dispatch_dry_validate`/`DryValidateArg`/`PipelexInterpreter`/`build_validation_report` imports + the route's `WorkflowExecutionError` catch. Behavior change documented in `pipelex-api/docs/pipe-validate.md`.
- [x] **Exception handlers (F3).** Removed the `temporalio` import + hardcoded `handle_temporal_error`. `register_exception_handlers(…, http_error_mappers=…)` registers one handler per `exc_type` via `_make_orchestrator_error_handler` → existing `_problem_response`. `api/main.py` resolves the mappers at import via `build_registrar(...).get_http_error_mappers()` (deferred-doc option 1 — no 2nd core change). `handle_pipelex_error` kept.
- [x] **Deps.** Dropped the `temporal` extra from `pyproject.toml`; removed the `[temporal]` block from the base `.pipelex/pipelex.toml`. Base depends on **no** orchestrator plugin.
- [x] **Tests.** `test_exception_handlers.py` rewritten to the synthetic-plugin shape (real `PluginRegistrar` + `add_http_error_mapper` + `get_http_error_mappers`, no `temporalio`); `test_validate_*` temporal arms removed; conformance webhook test mocks `get_orchestrator_registry`. New `test_api_config.py` covers the default + override policy (forbidden → 403, allowed honored, same-as-default ok) at the resolver AND end-to-end on `POST /start`.

### 🛑 CHECKPOINT C — hard stop · **MAJOR GATE 2 — THE gate** (source-doc Checkpoint 2)

Flavors are meaningless until the base is clean. This is the decisive checkpoint.

- [x] **Verify:** `pipelex-api` suite green (307 pass) with **no** `pipelex.temporal`/`temporalio` import in `api/` (`grep` → only incidental prose; `import api.main` → `temporalio` not in `sys.modules`). Direct-mode validate + execute work with no orchestrator plugin installed. Override policy refuses a forbidden per-request mode (403). All gates green (lint/pyright 0/mypy 0/pylint 10/openapi-check).
- [x] **Capture cold-start context:** `### Phase C — as-built` appended below (config Option C + root-key gotcha, the F1 dispatch deviation + why, override policy, synthetic-plugin test pattern, validate doc location).
- [x] **Fan-out `/code-review`:** two clean-context reviews on the working-tree diff (correctness/byte-equivalence + tests/config) — both **correct, no silent bugs, byte-equivalence verified**. Triage recorded in the Phase C as-built (5 applied incl. a re-added coverage test; 2 pre-existing deferred).
- [x] **Commit:** `pipelex-api` `a39841e` (`refactor/orchestrator-agnostic-base`) + this tracker update on `refactor/Plugins-4`. Nothing pushed. Strong session boundary before building flavors.

---

## Phase D — `pipelex-api-hosted` (Temporal flavor, private ECR)

**Goal:** the first real flavor = agnostic base + `pipelex-temporal` + Temporal activation.

- [ ] **Flavored base** (`pipelex-api-temporal`): `FROM pipelex/pipelex-api:<ver>` + install `pipelex-temporal @ git+ssh://…@<ref>` per the image architecture (re-add `git` + `openssh-client`, SSH mount, version-locked to `<ver>`). Wire the deploy key into CI (`--ssh default`).
- [ ] **Config migration** in the baked `.pipelex/pipelex_{env}.toml`:
  - [ ] Replace `[temporal] is_enabled = true` → `[plugins] boot_orchestrator = "temporal"`.
  - [ ] Add `[api] execution_mode = "temporal_fire_and_forget"` (or `temporal_blocking` per route semantics) + the override policy.
  - [ ] **Move** the connection tree (`temporal_config`, `worker_config`, `queue_options`, `search_attributes`) **out** of `pipelex_{env}.toml` into baked `.pipelex/temporal_{env}.toml` (the D2 plugin-config file). The main `pipelex_{env}.toml` carries no `[temporal.*]` keys — core would reject them.
- [ ] **Env-config child Dockerfile** stays a `COPY` — now copying `pipelex_{env}.toml` **and** `temporal_{env}.toml`.
- [ ] Record the (base `pipelex-api` version ⇄ `pipelex-temporal` ref) pair in the flavor's version file.

### 🛑 CHECKPOINT D — hard stop · **MAJOR GATE 3** (source-doc Checkpoint 3)

First flavor boots end-to-end — validates the whole chain before replicating for Mistral.

- [ ] **Verify:** dev image boots with Temporal active; a run enqueues to Temporal Cloud; `PIPELEX_ENV` selects the right `temporal_{env}.toml`. Validate runs DIRECT in-process (F2) and the runner is sized for the library load.
- [ ] **Capture cold-start context:** append `### Phase D — as-built` (the two-layer Dockerfile shape, the SSH/deploy-key CI wiring, the exact config keys moved to `temporal_{env}.toml`, the version-pair record location, any e2e boot evidence).
- [ ] **Fan-out `/code-review`:** sub-agent runs `/code-review` on the `pipelex-api-hosted` diff (Dockerfile + config migration). Triage as above.
- [ ] **Commit** in `pipelex-api-hosted` (its own branch). This is where outward-facing/deploy-breaking work begins — confirm go/no-go with the user before any actual deploy.

---

## Phase E — `pipelex-api-mistral` (Mistral flavor, new repo) — GATED

**Goal:** prove the base supports a *second*, differently-shaped (per-call) orchestrator. **Gated on `pipelex-mistralai-workflows` being published to PyPI and its in-flight `mistralai-2.x` work settling — coordinate, don't disrupt.**

- [ ] **Scaffold** mirroring `pipelex-api-hosted` conventions.
- [ ] **Flavored base** (`pipelex-api-mistral`): `FROM pipelex/pipelex-api:<ver>` + `uv pip install pipelex-mistralai-workflows==X` (PyPI — no SSH, no `git` re-add).
- [ ] **Config** in baked `.pipelex/pipelex_{env}.toml`: `[api] execution_mode = "mistral_native"`. **No** `boot_orchestrator` (per-call orchestrator), **no** plugin config file (the Mistral plugin self-loads none today).

### 🛑 CHECKPOINT E — hard stop

- [ ] **Verify:** image boots with `mistral_native` dispatchable; a run routes through the Mistral orchestrator; no Temporal anything present (proves the base is genuinely agnostic, not Temporal-shaped).
- [ ] **Capture cold-start context:** append `### Phase E — as-built` (confirming the per-call vs boot-global distinction held in practice: no `boot_orchestrator`, no plugin config file needed).
- [ ] **Fan-out `/code-review`:** sub-agent runs `/code-review` on the new-repo scaffold + flavor config. Triage as above.
- [ ] **Commit** in `pipelex-api-mistral` (new repo).

---

## Phase F — `pipelex-worker` pin flip (private; lands with the release)

**Goal:** flip the worker to the externalized Temporal plugin. Per the archived plugin-system cut-list — land in the **same commit** as the `pipelex` release pin bump.

- [ ] `pyproject.toml`: `pipelex[dynamodb,s3,temporal]==X` → `pipelex[dynamodb,s3]==X` + `pipelex-temporal @ git+ssh://…@<ref>`.
- [ ] `Dockerfile` CMD `["pipelex","worker",…]` → `["pipelex-temporal","worker",…]`; `Makefile` `pipelex worker` → `pipelex-temporal worker`.
- [ ] Set `boot_orchestrator = "temporal"` for the worker process.
- [ ] Run downstream consumers' suites against the new pins **before** publishing.

### 🛑 CHECKPOINT F — hard stop (final)

- [ ] **Verify:** worker runs on the externalized plugin; Temporal is fully external (no `temporal` extra anywhere in the public base); consumer suites green against the new pins.
- [ ] **Capture cold-start context:** append `### Phase F — as-built` (the published `pipelex-api` version, the `pipelex-temporal` ref, the pins flipped per repo, consumer-suite green evidence).
- [ ] **Fan-out `/code-review`:** sub-agent reviews the pin-flip diffs.
- [ ] **Ship:** coordinate the cross-repo release. Effort complete.

---

## Per-repo handoff summary

| Phase | Repo | Change | Channel |
|---|---|---|---|
| A | `pipelex` (`_plugins`) | D2 env-aware plugin-config helper; F3 `add_http_error_mapper` seam + `PLUGIN_API_VERSION` bump; SPI doc | public, normal release |
| B | `pipelex-temporal` | use D2 helper (`temporal_{env}.toml`); register F3 `TemporalError → ErrorReport` mapper | private git+ssh |
| C | `pipelex-api` | drop `temporal` extra; execution via bridge (F1); validate DIRECT (F2); consume F3 mappers; remove all `pipelex.temporal`/`temporalio` imports | public Docker Hub |
| D | `pipelex-api-hosted` | flavored-base install of `pipelex-temporal` (git+ssh); `boot_orchestrator=temporal` + `[api] execution_mode`; connection tree → `temporal_{env}.toml` | private ECR |
| E | `pipelex-api-mistral` (new) | scaffold; flavored-base install of `pipelex-mistralai-workflows` (PyPI); `[api] execution_mode=mistral_native`, no boot gate | private ECR |
| F | `pipelex-worker` | pin `pipelex-temporal` (git+ssh); CLI → `pipelex-temporal worker`; `boot_orchestrator=temporal` | private |

---

## Open items / risks to verify during execution

- **F3 — confirm transport faults are wrapped, or rely on the mapper.** Verify whether the Temporal orchestrator already wraps bare `temporalio` transport errors into `PipelexError`s (`TemporalServerError` etc.) before they reach HTTP. If it does, the F3 mapper is belt-and-suspenders; if not, it is the only thing keeping such errors off the catch-all 500. Either way the mapper makes the base correct without naming Temporal.
- **F1 — define the override policy precisely.** Decide the exact shape (`allow_request_execution_mode_override` bool vs a per-deployment allowlist of modes) and the default — recommend override **off** on hosted flavors. A caller must never force `direct` on a runner whose whole point is distributed execution.
- **F2 — quantify the library-load cost on the hosted runner.** Validate now loads the method library API-side. Confirm the hosted runner image/resources are sized for it; document in `pipelex-api` / `pipelex-api-hosted` docs.
- **Version-lock bookkeeping.** Record the (base `pipelex-api` version ⇄ plugin ref) pair in each flavor repo's version file so a bump can't drift them apart.
- **Mistral publish gating.** `pipelex-mistralai-workflows` must be published to PyPI and its `mistralai-2.x` work settled before Phase E.
- **Docs deploy.** The Temporal error pages left in core `docs/errors/` (type_uri dereference targets) still need a home decision when `pipelex-temporal` docs exist — tracked in the archived Phase-5 cut-over notes, not here. **Concrete instance from Phase B:** the F3 mapper emits `type_uri = .../errors/temporal-transport-error/`, but `TemporalTransportError` is a synthetic `error_type` string (not a `PipelexError` subclass), so `generate-error-pages` never emits a page — the RFC 7807 `type` link 404s. This is **pre-existing parity** (pipelex-api's old `handle_temporal_error` emitted the identical dangling URI), now plugin-owned. Resolve with the same "where do Temporal docs live" decision: author a `<!-- pipelex:authored -->` page once a home exists.

---

## As-built log (append per phase at each checkpoint — keep this current for cold starts)

> Each checkpoint appends an `### Phase N — as-built` subsection here with: final names/signatures, divergences from plan, test evidence, and anything a cold resume needs.

### Phase A — as-built

**Branch:** `refactor/Plugins-4` (worktree `_plugins`), cut from `refactor/Plugins-3`. One commit for the whole phase.

**D2 — env-aware plugin config loader.** `pipelex/system/configuration/config_loader.py`:

- `ConfigLoader.load_plugin_config(*, name: str, package_dir: Path, schema: type[_PluginConfigT], extra_overrides: dict[str, Any] | None = None) -> _PluginConfigT` — loads, deep-merges and **validates** (returns the `schema` instance, not a raw dict — the `schema` param from the plan is honored as a validated return).
- **Signature divergence from the plan sketch `load_plugin_config(*, name, schema)`:** added `package_dir: Path`. The packaged default `{name}.toml` lives inside the *plugin's own* distribution; core cannot locate it, so the plugin passes its package dir (`Path(__file__).parent`). This is necessary, not optional.
- Layering (later wins per leaf, via `deep_update`): `{package_dir}/{name}.toml` → global `~/.pipelex/{name}_{env}.toml` → global `~/.pipelex/{name}_override.toml` → project `.pipelex/{name}_{env}.toml` → project `.pipelex/{name}_override.toml` (project only if distinct from global) → `extra_overrides`. `env` = `runtime_manager.environment`.
- Helper `ConfigLoader._plugin_override_files_for_dir(config_dir, *, name)` mirrors `_override_files_for_dir` but is **intentionally narrower**: only `{name}_{env}` + `{name}_override` — no `local` / `run_mode` / `temporary` tiers (a plugin config is env-selected + deployment-baked, not developer-scratch-layered). Missing files at any tier are skipped, so the packaged default alone is valid. Does **not** call `ensure_global_config_exists()` (no kit-template copy for plugin configs).
- New module-level `_PluginConfigT = TypeVar(..., bound=BaseModel)`; added `from pydantic import BaseModel`.

**F3 — HTTP-error-mapper seam.** `pipelex/plugins/registrar.py` (reflects the **lazy-provider refinement** landed during Phase B — see the next paragraph for why):

- Type aliases `HttpErrorMapperFn = Callable[[Exception], ErrorReport]` and `HttpErrorTypeProviderFn = Callable[[], type[Exception]]` (`ErrorReport` from `pipelex.base_exceptions` — a core type, no cycle, no FastAPI/SDK pull).
- Menu method `PluginRegistrar.add_http_error_mapper(*, exc_type_provider: HttpErrorTypeProviderFn, to_error_report: HttpErrorMapperFn) -> None` — the exc type is supplied as a **thunk**, not the bare class. `register` only appends a `_HttpErrorMapperContribution(exc_type_provider, to_error_report, source_plugin)` NamedTuple to `self.http_error_mappers: list[...]` + a generic `"http error mapper"` contribution line; it neither resolves the type nor imports the SDK.
- Read accessor `PluginRegistrar.get_http_error_mappers() -> dict[type[Exception], HttpErrorMapperFn]` **runs every provider** to build a freshly-keyed `{exc_type: mapper}` dict (so any SDK import is paid here, at the host's read time, not at registration), fail-loud `DuplicateHttpErrorMapperError` naming both plugins on a duplicate *resolved* type. Consumer can't mutate registrar state.
- New error class `DuplicateHttpErrorMapperError(PluginError)` in `pipelex/plugins/exceptions.py` (mirrors `DuplicateOrchestratorError`; fields `exc_type`/`first_plugin`/`second_plugin`).

**Why lazy (the Phase-B-forced refinement).** Phase A originally shipped `add_http_error_mapper(*, exc_type: type[Exception], …)` keyed on the concrete class. Phase B exposed the conflict: naming `temporalio.exceptions.TemporalError` imports the whole `temporalio` SDK (measured ~146 ms — pulls the `temporalio.api`/`temporalio.bridge` protobuf chain), so a bare `exc_type=` forces that import inside `TemporalPlugin.register` — violating Checkpoint B's hard acceptance ("import-light register, no temporalio at registration") and the plugin's own thunk discipline. The provider thunk defers the SDK import to `get_http_error_mappers` (a host runtime's app construction), where the plugin — and therefore its SDK — is by definition installed. Duplicate-by-type detection moves with it (to resolution time). `PLUGIN_API_VERSION` stays **2** (same capability, refined signature; nothing external consumed v2 yet). Landed as its own commit on `refactor/Plugins-4`.

**No hub wiring (deliberate).** Phase A is exactly the planned surface: registrar method + accessor. The mappers are **not** pushed onto the hub. **How `pipelex-api` reaches them in Phase C:** call `build_registrar(config=get_config())` at app construction (documented pure/repeatable fn; `cli/commands/plugins_cmd.py` already does this standalone) and iterate `registrar.get_http_error_mappers()`. No further core exposure needed → Phase C stays pipelex-api-only. If Phase C prefers reading the boot registrar instead of rebuilding, that needs a *new* public getter (the registrar is `Pipelex._plugin_registrar`, private today) — small follow-up, decide in Phase C.

**Version bump.** `pipelex/plugins/contract.py`: `PLUGIN_API_VERSION: int = 1 → 2` (+ comment noting v2 = the optional `add_http_error_mapper` capability). `PipelexPlugin` docstring corrected (dropped the stale "CLI commands" mention removed by Option A; added "model listers" and "HTTP-error mappers"). **`targets_api` re-confirmation:** all built-ins set `targets_api = PLUGIN_API_VERSION` (auto-tracks the bump — verified). **Still to re-confirm in Phase B:** the external `pipelex-temporal` plugin (and `pipelex-mistralai-workflows`, already an entry-point plugin) — both import `PLUGIN_API_VERSION` from core, so an editable-pinned core gives them `2` automatically, but their suites must run against the Phase A core to confirm.

**SPI doc.** `docs/under-the-hood/orchestrator-plugins.md`: new section "HTTP error mappers: rendering an orchestrator's transport faults" (plugin owns classification / core owns transport / host owns presentation), the registrar-menu table row now lists `add_http_error_mapper` + `get_http_error_mappers`, and the `PLUGIN_API_VERSION = 2` note. Error reference page `docs/errors/duplicate-http-error-mapper-error.md` generated via `pipelex-dev generate-error-pages` (+ index line in `inference-and-providers.md`).

**Tests (all green).**

- `tests/unit/pipelex/system/test_plugin_config_loader.py` — `TestPluginConfigLoader`: packaged-default-only, env-file deep-merge + sibling-env-ignored, override-beats-env, project-beats-global, extra_overrides-win-last, validation-after-merge. Hermetic via `PropertyMock` on `global_config_dir`/`project_config_dir`/`runtime_manager.environment`.
- `tests/unit/pipelex/plugins/test_http_error_mapper_seam.py` — `TestHttpErrorMapperSeam`: add+get (resolved type), **provider resolved lazily not at registration** (the import-light proof — an exploding provider survives `register`), contribution recorded without resolving, duplicate fails loud naming both at resolution time, accessor returns a fresh dict, empty-by-default.
- `tests/unit/pipelex/plugins/test_import_light_boot.py` — extended the BLOCKED set with `fastapi`/`starlette` so the subprocess guard now also proves registration imports no web framework (locks the F3 invariant at the discovery layer).

**Gates:** `make agent-check` clean (ruff/plxt/pyright 0/mypy 0/keyword-only ✓) · `make tb` green · `make agent-test` green. Core names no orchestrator; no `import fastapi`/`starlette` anywhere in core (the only `fastapi` strings are telemetry-integration labels + the `WorkerMode.FASTAPI` enum value, not imports).

**Code-review triage** (forked `/code-review`, high effort — verdict: clean, correct, faithful to D1/D2/F1/F2/F3; no bugs):

- **Applied:** test `begin_plugin(targets_api=…)` now uses `PLUGIN_API_VERSION` instead of a literal `2` (nit #2 — latent stale-on-bump).
- **Deferred (design tradeoff):** the Phase-C consumer path for the mappers (registrar has the accessor but it isn't on the hub and the boot registrar is private) → captured in [`wip/plugins/phase-c-http-error-mapper-consumer-path.md`](wip/plugins/phase-c-http-error-mapper-consumer-path.md). Recommended default: Phase C calls `build_registrar(config=get_config())` and iterates `get_http_error_mappers()` (keeps Phase C pipelex-api-only).
- **Info / no action:** `DuplicateHttpErrorMapperError` message uses `__qualname__` (only ever fires on a true same-class dup, so unambiguous); `load_plugin_config` has no `is_unit_testing` hermetic branch (correct — no run_mode tier; Phase B tests must mock the config dirs); D2 intentionally has no `.pipelex/{name}.toml` *base* tier (packaged default is the only base — worth a one-line plugin-authoring-doc callout when Phase B lands).

### Phase B — as-built

**Repos/branches:** core seam refinement on `refactor/Plugins-4` (`pipelex`, worktree `_plugins`) commit `75196e2e3`; Phase B proper on `refactor/own-temporal-config` (`pipelex-temporal`). pipelex-temporal pins core editable (`[tool.uv.sources] pipelex = { path = "../_plugins", editable = true }`), so it builds against the Phase A core live.

**Seam refinement (core, `75196e2e3`) — prerequisite, see Phase A as-built "Why lazy".** `add_http_error_mapper(*, exc_type_provider: Callable[[], type[Exception]], to_error_report)`; `register` only stores a `_HttpErrorMapperContribution` NamedTuple; `get_http_error_mappers()` runs the providers at the host's read time and dedups on the resolved type. This is what lets `TemporalPlugin.register` name `temporalio.TemporalError` without importing `temporalio` (which costs ~146 ms — the whole api/bridge protobuf chain).

**D2 adoption.** `pipelex_temporal/temporal_config_loader.py`: `load_temporal_config()` now delegates to `config_manager.load_plugin_config(name="temporal", package_dir=Path(__file__).resolve().parent, schema=Temporal)`. Dropped the hand-rolled `load_toml_from_path` + single-`resolve_config_file` override; the helper layers packaged `temporal.toml` → global `~/.pipelex/temporal_{env}.toml` → `temporal_override.toml` → project `.pipelex/{...}` with deep-merge, `env = runtime_manager.environment`. **Behavior change:** the old loader read a plain `.pipelex/temporal.toml`; the new layering has **no plain-`.pipelex/temporal.toml` base tier** (packaged default is the only base — D2 design). No such override file existed in the repo, so nothing silently dropped. The env files themselves are baked per-deployment in Phase D; Phase B only switches the loader to support the layering. **Phase-D guardrail (deferred, from the Phase B `/code-review`):** a stray suffix-less `.pipelex/temporal.toml` left over after a botched migration would now vanish silently — a one-line `log.warning` when such a file is found would catch it. Deferred as an enhancement (not added now per smallest-correct-surface; revisit when Phase D migrates the connection tree).

**F3 mapper.** `pipelex_temporal/temporal_plugin.py`: two new module-level fns + one `register` line (unconditional, alongside the orchestrators — an API runner that only dispatches Temporal per-request still needs the mapper):

- `_temporal_transport_error_type() -> type[Exception]` — lazily `from temporalio.exceptions import TemporalError; return TemporalError`. Keyed on the **base** `TemporalError`: `RPCError` and `WorkflowFailureError` both subclass it, so the host's exception-MRO walk catches every bare transport fault. Invoked only by `get_http_error_mappers()`, never at register.
- `_temporal_transport_error_to_report(exc) -> ErrorReport` — ports pipelex-api's old `handle_temporal_error`: `error_type="TemporalTransportError"`, `message=str(exc)`, `title=pascal_case_to_sentence(...)` → "Temporal transport error", `type_uri=f"{URLs.error_docs_base}/{pascal_case_to_kebab(...)}/"` → `.../errors/temporal-transport-error/`, `error_category="transient"`, `error_domain=ErrorDomain.RUNTIME`, `retryable=True`. Imports no `temporalio` (only `str(exc)`); the identity pair uses the same core helpers `PipelexError.title`/`type_uri` use, so the docs URI matches the canonical scheme.
- Module-top imports added: `ErrorDomain`, `ErrorReport` (`pipelex.base_exceptions`), `pascal_case_to_kebab`/`pascal_case_to_sentence` (`pipelex.tools.misc.string_utils`), `URLs` (`pipelex.urls`) — all import-light core, no SDK.

**F3 is mostly belt-and-suspenders (open-item resolved).** `pipelex_temporal/tprl/workflow_caller.py` already wraps `RPCError` / `WorkflowFailureError` / `WorkflowAlreadyStartedError` into `WorkflowExecutionError` (a `PipelexError`) inside `execute_workflow`/`start_workflow`, so the common transport faults reach the API as `PipelexError` (handled generically by `handle_pipelex_error`). The F3 mapper is the safety net for any temporalio error that escapes that wrapping (e.g. a connection error raised outside execute/start) — and, more importantly, it is what makes the public `pipelex-api` base render such a fault correctly **without naming Temporal**. Implemented as planned regardless.

**`targets_api`.** Unchanged: `TemporalPlugin.targets_api = PLUGIN_API_VERSION` auto-tracks to 2 via the editable core pin. The whole suite running against the Phase A core is the confirmation.

**Tests (pipelex-temporal, all green).**

- `tests/unit/pipelex_temporal/test_temporal_config_env_layering.py` — `TestTemporalConfigEnvLayering`: packaged-default-only valid; `temporal_{env}.toml` deep-merges onto the real packaged default (overridden leaf wins, untouched leaves + sibling env ignored). Hermetic via `PropertyMock` on `ConfigLoader.global_config_dir`/`project_config_dir` + `runtime_manager.environment` (mirrors core's `test_plugin_config_loader`).
- `tests/unit/pipelex_temporal/test_temporal_plugin_http_error_mapper.py` — `TestTemporalPluginHttpErrorMapper`: register → `get_http_error_mappers()` keyed on `TemporalError` + full classification through the public seam; **import-light proof** = a fresh subprocess with a `temporalio` meta-path blocker imports the plugin and runs `register` (both `boot_orchestrator=None` and `"temporal"`) to completion, asserting `temporalio` never lands in `sys.modules`.
- Existing `test_temporal_config_loader.py` (packaged-default + hub cache) still green against the new loader.

**Gates:** pipelex-temporal `make agent-check` clean (ruff ✓ / pyright 0 / mypy 0) · `make agent-test` GREEN against the Phase A core (full suite incl. `temporal`-marked workflow integration tests, exit 0). Core (`refactor/Plugins-4`) `make agent-check` + plugins tests + `make tb` also green.

**Code-review triage** (two forked `/code-review`s, high effort — both verdicts: **clean, no bugs**):

- _Core seam refinement (`75196e2e3`):_ correct + internally consistent (no dangling `_http_error_mapper_sources`; `_add` still drives the 3 sibling adders; dedup attribution at resolution time correct; repeated `get_http_error_mappers()` side-effect-safe; NamedTuple standards-correct). **Deferred (recorded in `wip/plugins/phase-c-http-error-mapper-consumer-path.md`):** dedup raise now lands at the host's app-construction read time (theoretical for one-plugin-per-image); `plugins list` shows a generic `"http error mapper"` line (lost the per-type label — optional `display_label` param if it ever matters).
- _pipelex-temporal Phase B:_ F3 classification verified **byte-exact** vs pipelex-api `handle_temporal_error` (title/type_uri identical — same `URLs.error_docs_base` + helpers); `TemporalError`-base keying complete via MRO; import-light genuinely proven. **Applied:** import-light subprocess now also asserts `slot_claims` count per boot arm (0 off-gate, 4 on `"temporal"`). **Deferred:** dangling `temporal-transport-error` docs URI (pre-existing parity → folded into the "Temporal error pages need a home" open item); D2 base-tier-drop `log.warning` guardrail (Phase D).

### Phase C — as-built

**Repo/branch:** `pipelex-api` on `refactor/orchestrator-agnostic-base` (cut from `dev`), commit `a39841e`. The `pipelex` worktree only carries this tracker update (`refactor/Plugins-4`). Nothing pushed. pipelex-api pins core **editable** (`[tool.uv.sources] pipelex = { path = "../_plugins", editable = true }`) so it builds against the Phase A core live; the published `==<ver>` pin (no `temporal` extra) is the release-time flip. Nothing pushed.

**Decision — `[api]` config home = Option C (the user chose it).** `execution_mode` + override policy live in a **pipelex-api-owned `api/api.toml`**, loaded via the Phase A D2 helper `config_manager.load_plugin_config(name="api", package_dir=Path(api/), schema=ApiConfig)` — NOT a core `[api]` section (core config is `extra="forbid"`, would reject it → would need a 2nd core change, which the plan forbids). **Mechanics gotcha:** `load_plugin_config` validates the **whole** merged TOML document against the schema (exactly like `temporal.toml`), so `api.toml` keys are **root-level — no `[api]` table wrapper** (the user's preview showed `[api]`; the real file has root keys; functionally identical). `ApiConfig(BaseModel, extra="forbid")` has NO field defaults (defaults live in `api.toml`, mirroring core's discipline): `execution_mode: PipelexExecutionMode`, `allow_request_execution_mode_override: bool`. Base ships `execution_mode = "direct"`, override off. `get_api_config()` is `@cache`'d (immutable per process), **warmed in `lifespan` after `Pipelex.make`** for fail-fast (matches `ERROR_DISCLOSURE`). A flavor bakes `.pipelex/api_{env}.toml` (Phase D).

**F1 — dispatch DEVIATION from the literal plan (flagged; the only option satisfying all three locked constraints).** The plan's F1 wording said "build `PipelexPipeRunInput` and dispatch via `run_pipe_via_bridge`." **That path is lossy:** `PipelexPipeRunInput` carries no `request_id` / `output_multiplicity` / `dynamic_output_concept_ref`, and `build_pipe_job_from_input` skips pipeline-manager registration (the 409-conflict path) + telemetry — so routing `start` through it would silently regress those features. The only non-lossy bridge variant is extending the **core** `PipelexPipeRunInput` = a 2nd core change the plan forbids ("Phase C = pipelex-api only"). **Chosen instead (Design B):** keep `pipeline_run_setup(...)` to build the rich `PipeJob` (preserves everything → byte-equivalent, which Checkpoint C explicitly demands), then dispatch via the agnostic hub seam `get_orchestrator_registry().get_optional(mode=execution_mode).run(pipe_job=…, delivery_assignment=…)` — the **identical final dispatch** `run_pipe_via_bridge` performs internally (bridge.py:92-95), just fed a live job instead of a serialized lossy input. Names no orchestrator, imports no SDK. `None` orchestrator → `MissingOrchestratorError(mode)` (a `PipelexError` → `handle_pipelex_error`, carries the install hint). `workflow_id` read off `run_output.workflow_id` (Temporal FF sets it, DIRECT returns `None`); returned `pipeline_run_id` stays the `pipeline_run_setup`-resolved id (byte-equivalent to old). Verified equivalent against `TemporalFireAndForgetOrchestrator.run` (pipelex-temporal) which calls the same `temporal_pipe_run.start(pipe_job)` the old code did. `execution_mode` resolved **first** in `start()` (before `pipeline_run_setup`) so a forbidden override 403s before any library load.

**F1 — override policy.** Per-request mode rides `PipelineApiExtras.execution_mode` (API-server extra; route `_validate_extras` parses it, `start` route passes `requested_execution_mode=`). `resolve_execution_mode(requested, *, config)`: `None`/equal-to-default → default; differs + override on → requested; differs + override off → `raise_forbidden(403, ErrorType.EXECUTION_MODE_OVERRIDE_FORBIDDEN)`. Documented in OpenAPI only via the `PipelineApiExtras` field description (NOT added to `PipelexApiStartRequest`, so the committed OpenAPI artifact's `/start` schema is unchanged — only the validate-route docstring regen'd).

**F2 — validate always DIRECT.** `ApiRunner.validate` collapsed to the single `validate_bundles_in_process(...)` path; dropped the `get_config().temporal.is_enabled` branch + `dispatch_dry_validate`/`DryValidateArg`/`PipelexInterpreter`/`build_validation_report` imports; dropped the route's `WorkflowExecutionError` catch in `validate.py` (unreachable). **Behavior change documented** in `pipelex-api/docs/pipe-validate.md` ("Where validation runs" + a deployment resource note: the runner now loads the method library API-side — size a flavor's runner for it).

> **F2 SUBSEQUENTLY REVERSED / EXTENDED** by the orchestrator-dispatched-`/validate` follow-on (its own plan: [`wip/plugins/orchestrator-dispatched-validate.md`](wip/plugins/orchestrator-dispatched-validate.md)). `/validate` is now `execution_mode`-aware through a new per-call `BundleValidatorRegistry` seam (V0 core, V1 `pipelex-temporal`, V2 `pipelex-api`): `ApiRunner.validate` (the override) was **removed** in favor of `ApiRunner.validate_verdict` (verdict-as-value); the route discriminates on `isinstance(verdict, PipelexValidationReport)` instead of catching `ValidateBundleError`. `direct` keeps the in-process path; `temporal_*` dispatches to a worker and assembles the same canonical report API-side. The library-load note is now flavor-conditional. Branches: all three repos on `feature/Orchestrator-dispatched-validate`.

**F3 — consume the mappers.** `api/exception_handlers.py`: dropped `from temporalio.exceptions import TemporalError` + hardcoded `handle_temporal_error`; `register_exception_handlers(app, *, disclosure_mode, http_error_mappers=None)` now registers one FastAPI handler per `(exc_type, mapper)` via `_make_orchestrator_error_handler` (runs the mapper → existing `_problem_response` RFC 7807 + DisclosureMode render). **Consumer path = deferred-doc option 1 (no 2nd core change):** `api/main.py` resolves the mappers at module import via `build_registrar(config=PipelexConfig.model_validate(config_manager.load_config())).get_http_error_mappers()` (the standalone pattern `plugins_cmd.py` uses — pure, pre-boot-safe; smoke-confirmed empty in the base). The module keeps its import-side-effect-free contract (mappers are a param, not a `build_registrar` call inside it), so tests register handlers on throwaway apps. **Base = zero mappers** ⇒ a bare orchestrator transport fault with no plugin installed falls to the sanitized catch-all 500 (the dedicated transient classification is now plugin-owned; intended for the agnostic base — proven by `test_unmapped_transport_error_falls_back_to_sanitized_500`).

**F3 test pattern (synthetic plugin, no temporalio).** `test_exception_handlers.py`: `_SyntheticTransportError(Exception)` (bare, non-PipelexError) + `_SyntheticOrchestratorError(PipelexError)` + `_synthetic_transport_to_report` mapper. `_synthetic_http_error_mappers()` builds a real `PluginRegistrar`, `begin_plugin(...)`, `add_http_error_mapper(exc_type_provider=lambda: _SyntheticTransportError, …)`, returns `get_http_error_mappers()` — exercises the **real producer→consumer seam** (same as `api/main.py`) without installing a plugin or importing an SDK. Conformance webhook test now mocks `get_orchestrator_registry` (fake orchestrator `run` does the real `DeliveryExecutor` delivery + returns a FF `PipelexPipeRunOutput`).

**Deps + base config.** `pyproject.toml`: `pipelex[mistralai,anthropic,google,google-genai,bedrock,fal]` (dropped `temporal`). Removed the whole `[temporal]` block from the base `.pipelex/pipelex.toml` (core would reject it). **Local-env cleanups (NOT committed, machine-only):** a stale `[temporal]` section in the gitignored `.pipelex/pipelex_override.toml` (had `worker_scopes`/search-attributes) broke loading against the temporal-free core — removed it; the global `~/.pipelex/pipelex.toml` only had the valid `tracing_config.temporal_dynamodb` backend (left alone). `tests/unit/conftest.py`: dropped the removed `temporal_enabled=False` kwarg from `Pipelex.make` (agnostic base defaults to in-process DIRECT, which is what the hermetic suite wants).

**Gates (all green):** `make lint` (ruff, incl. 2 TC002 moves — `PipelexValidationReport`+`PipelexExecutionMode` to TYPE_CHECKING in pipeline.py, both annotation-only under `from __future__ import annotations`; pydantic `models.py` keeps its runtime import) · `make pyright` 0 · `make mypy` 0 · `make pylint` 10.00/10 · **307 tests pass** (`make t`, xdist) · `make openapi-check` ✓ (only the validate docstring regen'd). `grep -rn temporal api/` → only incidental prose (`pipelex-temporal` plugin name, `temporalio.TemporalError` in a docstring, the execution-mode enum value strings). `import api.main` → `temporalio` NOT in `sys.modules` (agnostic base proven).

**Docs.** `docs/configuration.md` (new "Execution mode" section + de-Temporal'd the intro), `docs/pipe-validate.md` ("Where validation runs" + resource note), `docs/pipe-run.md` / `docs/index.md` / `docs/error-responses.md` (de-Temporal'd stale mentions), `CHANGELOG.md` `[Unreleased]`.

**Code-review triage** (two clean-context `/code-review`s on the working-tree diff — correctness/byte-equivalence + tests/config; both verdicts: **correct, byte-equivalence holds, no silent bugs, no 500 regression, clean coupling**):

- **Applied (5):** (1) _Real coverage loss_ — re-added the validate **no-verdict→5xx** invariant test (deleted with the Temporal arm; route still upholds it but nothing tested it) as `test_non_verdict_failure_is_not_a_200_verdict` (mocks `validate` to raise a non-`ValidateBundleError` `PipelexConfigError` → asserts ≥500 + problem+json + `is_valid` absent). (2) _Direct-mode `/start` blocks_ — the agnostic base runs `direct` in-process to completion before the 202, so the "asynchronous/non-blocking" promise is a **distributed-flavor** property; clarified in the `start` route docstring + `docs/pipe-run.md` (callback still fires either way). (3) Conformance webhook test now asserts `get_optional.assert_called_once_with(mode=DIRECT)` + `run.assert_awaited_once()` (closes the "wrong mode silently dispatched" gap). (4) conftest `get_api_config.cache_clear()` on setup+teardown (insurance vs `@cache` leak across tests). (5) Stale-doc fixes: `handle_unexpected_error` docstring + `ErrorType.INTERNAL_SERVER_ERROR` comment (dropped the `TemporalError` mention) + `test_validate_errors` module docstring.
- **Deferred (pre-existing / design, recorded here):** _`_validate_extras` mislabels error_type_ — a malformed `execution_mode`/`pipeline_run_id` in the start extras is a correct 422 but labeled `InvalidCallbackUrls` (one catch covers all three extras; the `message` still names the real field). Pre-existing pattern my new field slightly widened; proper fix = per-field error_type discrimination (more surface) → follow-up, untested today. _Double `build_registrar`_ — runs once at `api/main.py` import (mapper resolution) and once in `Pipelex.make` boot; harmless (pure fn), the deferred-doc option-1 tradeoff.
- **Verdict on the F1 deviation:** the correctness reviewer independently **verified byte-equivalence** of the orchestrator-registry dispatch vs the old `make_temporal_pipe_run().start()` (same `pipe_job`, same `delivery_assignment`, `pipeline_run_id` still from `pipeline_run_setup`, `workflow_id` off `run_output` — the F&F orchestrator calls the identical `temporal_pipe_run.start`). No silent change.

**Gates re-run after triage:** lint ✓ · pyright 0 · mypy 0 · pylint 10.00/10 · **308 tests pass** · openapi-check ✓ (the `start` + `validate` route docstrings regen'd the artifact).
