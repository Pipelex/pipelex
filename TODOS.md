# Orchestrator-agnostic runner & deployment flavors — implementation TODOS

**Effort:** make `pipelex-api` an orchestrator-agnostic base, then build N thin deployment flavors on top of it (Temporal today, Mistral next). The *consumer-side* sequel to the plugin-system externalization (that tracker is archived at [`wip/archive/plugin-system-implementation-tracker.md`](wip/archive/plugin-system-implementation-tracker.md)).

**Status:** **Phase A + Phase B DONE (through MAJOR GATE 1 / Checkpoint B).** Core seams added + refined on `refactor/Plugins-4` (`4b5449f88` Phase A; `75196e2e3` lazy-provider seam refinement; `7378afdd8` Phase B docs); `pipelex-temporal` adopts both seams on `refactor/own-temporal-config` (`6d9adff`). Both `/code-review`s clean, all gates green. **NEXT = Phase C** (`pipelex-api` decoupling — THE gate). The in-`pipelex` plugin-system foundation (seams inverted, Temporal externalized, `plugins.boot_orchestrator` gate) was done on `refactor/Plugins-3`; Phase A/B built on it from `refactor/Plugins-4`.

**Current `pipelex` branch:** `refactor/Plugins-4` (worktree `_plugins`), cut from `refactor/Plugins-3`. Phase A + the F3 seam refinement land here; each other phase lands in its own repo. Nothing pushed yet.

This is the **execution tracker**. The *why* and *how* live in [`wip/plugins/orchestrator-agnostic-runner-and-flavors.md`](wip/plugins/orchestrator-agnostic-runner-and-flavors.md) (the reviewed, decision-locked plan). **Read that doc before starting any phase** — this file tracks progress against it; it does not replace it. Adjacent background: [`wip/plugins/temporal-config-out-of-core.md`](wip/plugins/temporal-config-out-of-core.md) (the boot-gate refactor that immediately precedes this work) and the plugin-system design/SPI docs in [`wip/plugins/`](wip/plugins/).

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
- **F2** — validate is **always DIRECT in-process** (`validate_bundles_in_process`). Drops the Temporal validate branch. **Behavior change:** the API runner now loads the method library to validate (prior design pushed that onto the worker) — document the resource/isolation implication on the hosted runner.
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

- [ ] **Execution (F1).** Rewrite `ApiRunner.start()` / `execute` (`api/routes/pipelex/pipeline.py`) to build `PipelexPipeRunInput(…, execution_mode=…)` and call `run_pipe_via_bridge`; read `workflow_id` off the output payload. Resolve `execution_mode` from a new `[api] execution_mode` config default + an optional per-request override gated by a per-deployment policy (e.g. `[api] allow_request_execution_mode_override` and/or a mode allowlist). Delete `make_temporal_pipe_run` usage + import.
- [ ] **Validate (F2).** Collapse `ApiRunner.validate()` (`api/routes/pipelex/validate.py`) to the single in-process path (`validate_bundles_in_process`). Delete the `get_config().temporal.is_enabled` branch and the `dispatch_dry_validate` / `DryValidateArg` imports. Drop the now-unreachable explicit `WorkflowExecutionError` import/catch (validate is DIRECT and never raises it). Document the library-load-on-API behavior change in `pipelex-api/docs/`.
- [ ] **Exception handlers (F3).** In `api/exception_handlers.py`, remove the `temporalio` import and the hardcoded `handle_temporal_error`. At app construction (`api/main.py` → `register_exception_handlers`), iterate the registrar's HTTP-error mappers and register one FastAPI handler per `exc_type` that runs the mapper then renders via the existing RFC 7807 + `DisclosureMode` path. Keep `handle_pipelex_error` (it already covers `WorkflowExecutionError` generically).
- [ ] **Deps.** Drop the `temporal` extra from `pyproject.toml` (`pipelex[mistralai,anthropic,google,…]==<ver>`, no `temporal`). The base depends on **no** orchestrator plugin.
- [ ] **Tests.** Update `tests/unit/test_exception_handlers.py`, `test_validate_*` to the agnostic shape — a **synthetic in-test plugin** contributing a mapper proves the F3 seam without importing `temporalio`. Add an `[api] execution_mode` default + override-policy test (a caller must not be able to force `direct` when policy forbids it).

### 🛑 CHECKPOINT C — hard stop · **MAJOR GATE 2 — THE gate** (source-doc Checkpoint 2)

Flavors are meaningless until the base is clean. This is the decisive checkpoint.

- [ ] **Verify:** `pipelex-api` test suite green with **no** `pipelex.temporal` / `temporalio` import in `api/` (`grep -rn "temporal" api/` returns only incidental prose). A direct-mode run + validate works with **no orchestrator plugin installed**. The override policy refuses a forbidden per-request mode.
- [ ] **Capture cold-start context:** append `### Phase C — as-built` (the `[api] execution_mode` + override-policy config shape and defaults, how `workflow_id` is read off the bridge output, the synthetic-plugin test pattern, the validate library-load doc location).
- [ ] **Fan-out `/code-review`:** sub-agent runs `/code-review` on the full `api/` diff. This is the highest-stakes review — confirm byte-equivalence of dispatch semantics and that no transport-fault path silently became a catch-all 500. Triage as above.
- [ ] **Commit** in `pipelex-api` (its own branch). Strong session boundary before building flavors.

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
