# Orchestrator-agnostic runner & deployment flavors

**Status:** plan + agent handoff. Decisions locked (see §3). Not yet started in any consumer repo.
**Owner effort:** the plugin-system externalization (see [`TODOS.md`](../../TODOS.md) and the Phase 5 cut-over notes). This doc is the forward-looking *consumer* migration: it explains how the new plugin system changes the world for projects that consume `pipelex` and choose an orchestrator (Temporal, Mistral, or none), and gives the concrete, sequenced handoff to make `pipelex-api` an orchestrator-agnostic base plus N thin deployment flavors.

> **Why this exists.** Once Temporal left core (it is now the private `pipelex-temporal` plugin, discovered via the `pipelex.plugins` entry point), a consumer no longer gets Temporal "for free" by installing an extra. More importantly, the recon for this migration found that `pipelex-api` is **not** an orchestrator-agnostic runner today — it is wired directly to Temporal in production code. Making it the shared base for multiple deployment flavors (`pipelex-api-hosted` = Temporal, a future `pipelex-api-mistral` = Mistral) is a real decoupling refactor, not a dependency bump. This doc captures the target model, the locked design decisions, and the per-repo work.

---

## 1. The model shift (read this first)

The plugin system splits a previously-monolithic idea ("Temporal is on") into orthogonal concepts. Internalize these before touching any repo.

**Presence vs activation.**

- **Presence** = the plugin distribution is installed, so its `pipelex.plugins` entry point is discovered at boot and its `register()` runs. For an orchestrator plugin, `register()` always contributes its `execution_mode` arms to the orchestrator registry. Presence alone makes a mode *dispatchable*; it does not make it *used*.
- **Activation** = the runtime is actually told to use it. Activation decomposes into **two independent knobs** (this is the crux — see below).

**Two independent activation knobs.**

| Knob | Owns | Set by | Temporal | Mistral | Direct |
|---|---|---|---|---|---|
| `execution_mode` | which mode a *top-level* run dispatches as, through the bridge | runner config (default) + optional per-request override | `temporal_blocking` / `temporal_fire_and_forget` | `mistral_native` | `direct` |
| `plugins.boot_orchestrator` | whether to claim the process-global hub slots (content generator / pipe router / pipe run / task manager) at boot | deployment config TOML | `"temporal"` | *unset* | *unset* |

The two are **not derivable from each other** — and Mistral is the proof. A Temporal deployment needs *both* (the boot gate stands up the Temporal client/task-manager that the orchestrator uses to enqueue; the `execution_mode` tells the bridge to enqueue). A Mistral deployment needs **only** `execution_mode = mistral_native` — its plugin claims **no** hub slots (it is a self-contained per-call orchestrator), so there is no boot gate to set. A plain in-process deployment sets neither.

**Boot-global vs per-call orchestrators.** This is *why* the two knobs exist. A **boot-global** orchestrator (Temporal) replaces process-wide execution machinery — it must claim hub slots at boot, gated by `boot_orchestrator`. A **per-call** orchestrator (Mistral) only adds a dispatch arm — presence is enough; selection is per run via `execution_mode`. When you add a new orchestrator plugin, classify it first; the classification decides whether `boot_orchestrator` is even meaningful for it.

**Install channel follows license, not convenience.**

- `pipelex-temporal` is **private** → distributed by a pinned `git+ssh` ref (precedent: `pipelex-shared @ git+ssh://…/infra-python-tools.git@<ref>`). Only **private** images may pin it.
- `pipelex-mistralai-workflows` is **public** → plain PyPI install (`pipelex-mistralai-workflows==X`). (Currently pre-publish; gated on its own `mistralai-2.x` work — treat as PyPI once published.)

**Base-agnostic + flavor = base + one plugin.** The target: `pipelex/pipelex-api` (public, Docker Hub) names *no* orchestrator and ships only the in-process/direct path. Each deployment **flavor** is `base image + exactly one orchestrator plugin + that plugin's activation`. This is what lets a future `pipelex-api-mistral` exist at all — and it is the architecture the rest of this doc builds toward.

---

## 2. Where we are today (the gap)

`pipelex-api` is a Temporal-only runner. Concrete coupling sites (line numbers drift; locations hold):

- **Execution has no agnostic path.** `ApiRunner.start()` (`api/routes/pipelex/pipeline.py`) calls `make_temporal_pipe_run().start()` directly. There is **zero** use of the agnostic bridge entry `run_pipe_via_bridge` / `PipelexPipeRunInput` anywhere in `api/`.
- **Validate reads a deleted field.** `ApiRunner.validate()` branches on `get_config().temporal.is_enabled` — a config field **core has removed** — and on the "enabled" arm dispatches `dispatch_dry_validate(DryValidateArg(...))` from `pipelex.temporal.tprl_pipe`. The "disabled" arm already runs `validate_bundles_in_process(...)` in-process.
- **Exception handling imports `temporalio`.** `api/exception_handlers.py` imports `temporalio.exceptions.TemporalError` and registers a dedicated `handle_temporal_error`. It also references `WorkflowExecutionError` (which is a `PipelexError` via `TemporalFlowError`, so it is already covered generically by `handle_pipelex_error`).

Because core deleted both the `temporal` extra and the `temporal` config field, `pipelex-api` against the current `pipelex` worktree is broken on all three sites. The fix is the refactor below, not a pin nudge.

The plugin system inverted **core pipelex's** couplings (Phases 0–5). It did **not** provide seams for the **runner/HTTP layer** — exception-handler contribution and validate dispatch are `pipelex-api` concerns. One small new core seam is required (§3 F3).

---

## 3. Locked decisions

These were decided with the user. Do not re-litigate; if you believe one is wrong, raise it explicitly before deviating.

- **D1 — `boot_orchestrator` is set from the flavor's deployment TOML.** The Temporal flavor bakes `[plugins] boot_orchestrator = "temporal"` into its env-specific `pipelex_{env}.toml`. No change to `pipelex-api` for the gate. *Verified safe:* `Pipelex.setup()` only overrides `plugins.boot_orchestrator` when its param is non-`None` (`pipelex/pipelex.py` ~`:206`), so a TOML-provided value is **preserved**, not clobbered, and it is in place before `build_registrar` reads it. The core comment "set programmatically, not from pipelex.toml" describes core's *defaults*; a deployment override is a supported, distinct use.
- **D2 — plugin config files become env-aware, mirroring the main config.** Today `load_temporal_config()` resolves a *single* `temporal.toml` (project-then-global, no env layering), unlike the main config which layers `pipelex_{env}.toml` via `PIPELEX_ENV`. Add env-aware resolution so a plugin's config self-loads `name.toml` (packaged default) → `name_{env}.toml` → `name_override.toml`. Implement as a **reusable core helper** so every plugin inherits identical env semantics; `pipelex-temporal` uses it. One image bakes all envs; `PIPELEX_ENV` selects at runtime.
- **F1 — `execution_mode` = runner config default + optional per-request override, gated by a per-deployment policy.** `[api] execution_mode` sets the deployment default; the request may override it **only** when the deployment's policy allows it (so a locked-down Temporal runner can refuse a caller forcing `direct`). The runner builds `PipelexPipeRunInput(execution_mode=…)` and dispatches through `run_pipe_via_bridge`; the bridge output already carries `workflow_id`, so async-start semantics survive.
- **F2 — validate is always DIRECT in-process.** Drop the Temporal validate branch entirely; `ApiRunner.validate()` always calls `validate_bundles_in_process(...)`. Removes the `pipelex.temporal` imports (`dispatch_dry_validate` / `DryValidateArg`). **Behavior change to call out at handoff:** the API runner now loads the method library to validate, which the prior D10/D14 design deliberately pushed onto the worker. Acceptable per decision; note the resource/isolation implication on the hosted runner in that repo's docs.

  > **REVERSED / EXTENDED — orchestrator-dispatched `/validate`.** F2's "always DIRECT" is superseded: `/validate` is now `execution_mode`-aware through a new per-call `BundleValidatorRegistry` seam (mirroring the `OrchestratorRegistry`). `direct` keeps F2's in-process path (the agnostic base validates in-process); `temporal_*` dispatches the whole job to a worker, restoring what F2 removed — assembled back into the **same** canonical report API-side, so the verdict wire is byte-identical across backends. The library-load implication is now flavor-conditional, not absolute. Plan + as-built: [`orchestrator-dispatched-validate.md`](orchestrator-dispatched-validate.md).
- **F3 — orchestrator-specific HTTP error handling via a new plugin seam, contributed as a mapper (not a raw FastAPI handler).** Core's `PluginRegistrar` gains a framework-agnostic contribution: `add_http_error_mapper(*, exc_type: type[Exception], to_error_report: Callable[[Exception], ErrorReport])`. The orchestrator plugin registers its transport-fault mapping (e.g. `temporalio.TemporalError → ErrorReport[transient, RUNTIME]`). `pipelex-api` iterates the registrar's mappers at app construction and wraps each into a FastAPI handler using its existing RFC 7807 + `DisclosureMode` rendering. **FastAPI/Starlette stays only in `pipelex-api`; core and the plugin import neither.** This grows the plugin contract by one optional capability → bump `PLUGIN_API_VERSION` and document it in the orchestrator SPI.

---

## 4. Image architecture (handles public + private plugins uniformly)

A **two-layer** build per flavor. This isolates the plugin-install complexity (private SSH, version-locking) into one place and keeps the env-config layer as trivial as it is today.

```
pipelex/pipelex-api:<ver>          (public base, orchestrator-agnostic, Docker Hub)
  │
  ├─ flavored base  = base + ONE plugin            (built once per flavor → private ECR)
  │     pipelex-api-temporal:<ver>   = base + pipelex-temporal   (git+ssh)
  │     pipelex-api-mistral:<ver>    = base + pipelex-mistralai-workflows (PyPI)
  │
  └─ env-config child = flavored base + COPY env TOMLs    (per env; stays config-only)
        pipelex-api-{dev,staging,prod}        (Temporal)
        pipelex-api-mistral-{dev,staging,prod}
```

**One parameterized install recipe across flavors.** The flavored-base Dockerfile takes a build arg `PLUGIN_SPEC` and always exposes a BuildKit SSH mount:

- PyPI plugin (Mistral): `PLUGIN_SPEC="pipelex-mistralai-workflows==X"` → plain install, SSH mount unused.
- Private plugin (Temporal): `PLUGIN_SPEC="pipelex-temporal @ git+ssh://git@github.com/Pipelex/pipelex-temporal.git@<ref>"` → install uses `--mount=type=ssh`, with the deploy key wired into the CI builder (`docker build --ssh default`). Never bake a key into a layer.

Install mechanics that bite (encode these in the Dockerfile):

- The base image's Python lives in a **uv project venv at `/app/.venv`**, run via `uv run uvicorn …`. Install into that venv (`cd /app && uv pip install …`), do **not** let the resolver swap the pinned `pipelex` already baked in (pin / `--no-deps` as appropriate).
- The base image **purges `git`/`build-essential`** in a late layer. Re-add `git` (+`openssh-client` for the private case) in the flavored-base layer before installing.
- **Version-lock is load-bearing.** A plugin imports `pipelex` internals deeply; the plugin ref and the base `pipelex` version are a coupled pair that bump together. Track the pair wherever the flavor repo records versions (e.g. `api-config.toml`).

Whether the flavored base is a *separately-published* ECR image or just an earlier stage in a single multi-stage Dockerfile is a minor call: publish it only if more than one downstream consumes it; otherwise a multi-stage build keeps it to one artifact. Either way the env-config child stays a pure `COPY` of TOMLs, exactly like `pipelex-api-hosted/Dockerfile` today.

---

## 5. Phased plan

Order matters: enabling changes in `pipelex` and `pipelex-temporal` must land before `pipelex-api` can consume the new seam.

### Phase A — Core enabling changes (`pipelex`, the `_plugins` worktree)

1. **D2 env-aware plugin config loader.** Add a reusable helper on `config_manager` (e.g. `load_plugin_config(*, name, schema)`) that resolves `name.toml` (packaged default of the calling plugin) → `name_{environment}.toml` → `name_override.toml` with deep-merge, mirroring `load_config`'s env layering (`pipelex/system/configuration/config_loader.py`).
2. **F3 HTTP-error-mapper seam.** Add `add_http_error_mapper(*, exc_type, to_error_report)` to `PluginRegistrar` (`pipelex/plugins/registrar.py`) plus a read accessor for the collected mappers. Use `ErrorReport` (core type) in the signature — **no FastAPI import**. Bump `PLUGIN_API_VERSION` (`pipelex/plugins/contract.py`) and add the capability to the orchestrator SPI doc (`docs/under-the-hood/orchestrator-plugins.md`).
3. Tests: env-layered plugin-config round-trip; registrar collects mappers; import-light boot still green (the seam adds no SDK/HTTP import).

**Acceptance:** `make agent-check` clean · `make tb` green · `make agent-test` green. Core still names no orchestrator and imports no FastAPI.

### Phase B — `pipelex-temporal` (additive)

1. Switch `load_temporal_config()` to the D2 helper; ship `temporal_{env}.toml` resolution (the packaged default `temporal.toml` stays).
2. In `TemporalPlugin.register()`, register the F3 mapper: `temporalio.TemporalError → ErrorReport` classified transient / `RUNTIME` (port the classification currently living in `pipelex-api`'s `handle_temporal_error`). Keep `register` import-light — the mapper closure may import `temporalio` lazily when first invoked, matching the existing thunk discipline.

**Acceptance:** `pipelex-temporal` `make agent-check` + `make agent-test` green against the Phase A `pipelex`.

### Phase C — `pipelex-api` decoupling (the big one)

Make the base orchestrator-agnostic. No `pipelex.temporal.*`, no `temporalio`, anywhere in `api/`.

1. **Execution (F1).** Rewrite `ApiRunner.start()` / `execute` to build `PipelexPipeRunInput(…, execution_mode=…)` and call `run_pipe_via_bridge`; read `workflow_id` off the output payload. Resolve `execution_mode` from a new `[api] execution_mode` config default, with an optional per-request override gated by a per-deployment policy (e.g. `[api] allow_request_execution_mode_override` and/or an allowlist). Delete `make_temporal_pipe_run` usage + import.
2. **Validate (F2).** Collapse `ApiRunner.validate()` to the single in-process path (`validate_bundles_in_process`). Delete the `temporal.is_enabled` branch and the `dispatch_dry_validate` / `DryValidateArg` imports. Document the library-load-on-API behavior change in `pipelex-api/docs/`.
3. **Exception handlers (F3).** Remove the `temporalio` import and the hardcoded `handle_temporal_error` registration from `api/exception_handlers.py`. At app construction (`api/main.py` → `register_exception_handlers`), iterate `registrar` HTTP-error mappers and register a FastAPI handler per `exc_type` that runs the mapper then renders via the existing RFC 7807 + `DisclosureMode` path. Keep `handle_pipelex_error` (it already covers `WorkflowExecutionError`); drop the explicit `WorkflowExecutionError` import/catch in `validate.py` (now unreachable — validate is DIRECT and never raises it).
4. **Deps.** Drop the `temporal` extra from `pyproject.toml` (`pipelex[mistralai,anthropic,google,…]==<ver>`, no `temporal`). The base depends on **no** orchestrator plugin.
5. Tests: update `tests/unit/test_exception_handlers.py`, `test_validate_*` to the agnostic shape (a synthetic plugin contributing a mapper proves the seam without importing `temporalio`).

**Acceptance:** `pipelex-api` test suite green with **no** `pipelex.temporal` / `temporalio` import in `api/`; `grep -rn "temporal" api/` returns only incidental prose. A direct-mode run + validate works with no orchestrator plugin installed.

### Phase D — `pipelex-api-hosted` (Temporal flavor)

1. Flavored base (`pipelex-api-temporal`): `FROM pipelex/pipelex-api:<ver>` + install `pipelex-temporal @ git+ssh://…@<ref>` per §4 (re-add `git`+`openssh-client`, SSH mount, version-locked to `<ver>`). Wire the deploy key into CI (`--ssh default`).
2. Config migration in the baked `.pipelex/pipelex_{env}.toml`:
   - Replace `[temporal] is_enabled = true` → `[plugins] boot_orchestrator = "temporal"`.
   - Add `[api] execution_mode = "temporal_fire_and_forget"` (or `temporal_blocking` per route semantics) + the override policy you want.
   - **Move** the connection tree (`temporal_config`, `worker_config`, `queue_options`, `search_attributes`) **out** of `pipelex_{env}.toml` into baked `.pipelex/temporal_{env}.toml` files (the D2 plugin-config file). The main `pipelex_{env}.toml` no longer carries any `[temporal.*]` keys (core would reject them).
3. The env-config child Dockerfile stays a `COPY` — now copying `pipelex_{env}.toml` **and** `temporal_{env}.toml`.

**Acceptance:** dev image boots with Temporal active; a run enqueues to Temporal Cloud; `PIPELEX_ENV` selects the right `temporal_{env}.toml`.

### Phase E — `pipelex-api-mistral` (Mistral flavor, new repo)

Scaffold mirroring `pipelex-api-hosted` conventions.

1. Flavored base (`pipelex-api-mistral`): `FROM pipelex/pipelex-api:<ver>` + `uv pip install pipelex-mistralai-workflows==X` (PyPI — no SSH, no `git` re-add needed).
2. Config in baked `.pipelex/pipelex_{env}.toml`: `[api] execution_mode = "mistral_native"`. **No** `boot_orchestrator` (per-call orchestrator), **no** plugin config file (the Mistral plugin self-loads none today).
3. Gated on `pipelex-mistralai-workflows` being published and on its in-flight `mistralai-2.x` work — coordinate, don't disrupt.

**Acceptance:** image boots with `mistral_native` dispatchable; a run routes through the Mistral orchestrator; no Temporal anything present.

### Phase F — `pipelex-worker` pin flip (from the existing cut-list)

Per the Phase 5 cut-list in [`TODOS.md`](../../TODOS.md): `pyproject.toml` `pipelex[dynamodb,s3,temporal]==X` → `pipelex[dynamodb,s3]==X` + `pipelex-temporal @ git+ssh://…@<ref>`; `Dockerfile` CMD `["pipelex","worker",…]` → `["pipelex-temporal","worker",…]`; `Makefile` `pipelex worker` → `pipelex-temporal worker`; set `boot_orchestrator=temporal` for the worker process. Land in the **same** commit as the `pipelex` pin bump.

### Checkpoints

- **Checkpoint 1 — after Phase B:** core + `pipelex-temporal` green together; the seam exists and the plugin contributes through it. Natural session boundary before the `pipelex-api` refactor.
- **Checkpoint 2 — after Phase C:** `pipelex-api` is agnostic and green with no orchestrator installed. THE gate — flavors are meaningless until the base is clean. Fan out `/code-review` on the `api/` diff.
- **Checkpoint 3 — after Phase D:** first real flavor boots end-to-end against Temporal Cloud (dev). Validates the whole chain before replicating for Mistral.

---

## 6. Per-repo agent handoff summary

| Repo | Change | Channel |
|---|---|---|
| `pipelex` (`_plugins`) | D2 env-aware plugin-config helper; F3 `add_http_error_mapper` seam + `PLUGIN_API_VERSION` bump; SPI doc | normal release |
| `pipelex-temporal` | use D2 helper; register F3 `TemporalError → ErrorReport` mapper | private git+ssh |
| `pipelex-api` | drop `temporal` extra; route execution through bridge (F1); validate DIRECT (F2); consume F3 mappers; remove all `pipelex.temporal`/`temporalio` imports | public Docker Hub |
| `pipelex-api-hosted` | flavored-base install of `pipelex-temporal` (git+ssh); `boot_orchestrator=temporal` + `[api] execution_mode` in `pipelex_{env}.toml`; connection tree → `temporal_{env}.toml` | private ECR |
| `pipelex-api-mistral` (new) | scaffold; flavored-base install of `pipelex-mistralai-workflows` (PyPI); `[api] execution_mode=mistral_native`, no boot gate | private ECR |
| `pipelex-worker` | pin `pipelex-temporal` (git+ssh); CLI → `pipelex-temporal worker`; `boot_orchestrator=temporal` | private |

---

## 7. Open items / risks to verify during execution

- **F3 — confirm transport faults are wrapped, or rely on the mapper.** Verify whether the Temporal orchestrator already wraps bare `temporalio` transport errors into `PipelexError`s (`TemporalServerError` etc.) before they reach HTTP. If it does, the F3 mapper is belt-and-suspenders; if not, it is the only thing keeping such errors off the catch-all 500. Either way the mapper makes the base correct without naming Temporal.
- **F1 — define the override policy precisely.** Decide the exact shape (`allow_request_execution_mode_override` bool vs a per-deployment allowlist of modes) and the default (recommend: override **off** on hosted flavors). A caller must never be able to force `direct` on a runner whose whole point is distributed execution.
- **F2 — quantify the library-load cost on the hosted runner.** Validate now loads the method library API-side. Confirm the hosted runner image/resources are sized for it, and document it in `pipelex-api`/`pipelex-api-hosted` docs.
- **Version-lock bookkeeping.** Record the (base `pipelex-api` version ⇄ plugin ref) pair in each flavor repo's version file so a bump can't drift them apart.
- **Mistral publish gating.** `pipelex-mistralai-workflows` must be published to PyPI and its `mistralai-2.x` work settled before Phase E.
- **Docs deploy.** The Temporal error pages left in core `docs/errors/` on purpose (type_uri dereference targets) still need a home decision when `pipelex-temporal` docs exist — tracked in the Phase 5 cut-over notes, not here.
