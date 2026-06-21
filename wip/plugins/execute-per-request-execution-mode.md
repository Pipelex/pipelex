# Plan — `/execute` honors per-request `execution_mode` (extend F1)

**Status:** ready-to-execute plan for a fresh session. Design is locked; nothing coded yet. This is **Plan 2 of 2** — its sibling is `wip/plugins/orchestrator-dispatched-validate.md` (run **that one first**; this one is independent and can follow). It **extends locked decision F1** of the orchestrator-agnostic-runner effort (tracker: `_plugins/TODOS.md`; parent plan: `_plugins/wip/plugins/orchestrator-agnostic-runner-and-flavors.md`).

> **START HERE (cold start).** Read this whole doc. This is a **single-repo change in `pipelex-api`** — no core (`pipelex`) and no `pipelex-temporal` change. It converts `POST /execute` from the boot-global pipe-run hub slot to the **per-call `OrchestratorRegistry`** (the same seam `/start` already uses), so `/execute` honors a per-request `execution_mode` (policy-gated), exactly like `/start`. Begin on the branch named in §"Cross-repo state".

---

## 1. The ask + locked decisions

**The ask (user):** make `/execute` honor a per-request `execution_mode`, for consistency with `/start`. Today `/start` resolves the mode per request through the `OrchestratorRegistry`, but `/execute` runs through the **boot-global** `get_pipe_run()` hub slot and ignores any requested mode. Unify them.

**Locked decisions:**

- **Convert `/execute` to the per-call `OrchestratorRegistry`** (the `/start` family), so `execution_mode` (not `boot_orchestrator`) is the single source of truth for top-level dispatch backend. `boot_orchestrator` narrows to its real job — the *execution stack* used wherever the pipe actually runs (worker-side, and the in-process scoping inside `DirectOrchestrator`).
- **`/execute` honors a per-request override**, gated by the existing deployment policy (`allow_request_execution_mode_override`), **symmetric with `/start`**. The user chose this explicitly over keeping the asymmetry.
- **Reject fire-and-forget on `/execute`.** `/execute` is synchronous (it returns the full output); `temporal_fire_and_forget` is meaningless for it. Resolve the mode, then refuse a fire-and-forget resolution with a clear 4xx ("`/execute` is synchronous; use `/start` for fire-and-forget"). (Alternative — coerce f&f→blocking — is listed in §"Open sub-decisions"; default is reject.)
- **Keep it a separate change from `/validate`.** `/validate` adds a *new* seam; `/execute` *reuses* the existing one. They share only `resolve_execution_mode` (already shipped). Do not bundle them.

**Why this is the cleaner direction (context for the cold session):** the asymmetry is *incidental*, not principled. Phase C had to move `/start` to the registry (it needs per-request mode, the override policy, fire-and-forget, and a `workflow_id` return). `/execute` was *already* orchestrator-agnostic through the boot slot (`get_pipe_run()` returns whatever's installed; the base imports no `temporalio`), so Phase C had no forcing reason to touch it. This plan finishes that unification. The boot slots do **not** go away — they remain the execution stack on workers and for in-process runs; this only changes how the top-level `/execute` *entry* selects a backend.

---

## 2. Current state

All anchors in `pipelex-api/api/routes/pipelex/pipeline.py` unless noted.

- **`/execute` route** (`340-373`): `async def execute(request)` calls `_parse_request(request)` and **discards the extras** — line `361`: `run_request, _extras = await _parse_request(request)` — then calls `runner.execute(...)` (`363-370`) **without** any `requested_execution_mode`. So the wire **already parses** `PipelineApiExtras.execution_mode`; `/execute` simply throws it away.
- **`ApiRunner.execute` is NOT overridden.** `ApiRunner(PipelexMTHDSProtocol)` (line `67`) overrides `start` (`79`) and `validate` (`182`) but **not** `execute` — so `/execute` falls through to the base `PipelexMTHDSProtocol.execute` in core `_plugins/pipelex/pipeline/runner.py:112`.
- **The base `execute`** (core `runner.py:112-206+`) does `pipeline_run_setup(...)` → `effective_pipe_run = self._pipe_run or get_pipe_run()` → `pipe_output = await effective_pipe_run.run(pipe_job, delivery_assignment=…)` → wraps `pipe_output` into `PipelexRunResultExecute`. `get_pipe_run()` is the **boot-global** hub slot (Temporal claims it only when `boot_orchestrator == "temporal"`; else in-process). No `resolve_execution_mode`, no registry.
- **`/start` (the model to mirror)** — `ApiRunner.start` (`79-180`): `resolve_execution_mode(requested_execution_mode, config=get_api_config())` (`122`) → `pipeline_run_setup(...)` (rich `PipeJob`) → `orchestrator = get_orchestrator_registry().get_optional(mode=execution_mode)` (`170`) → `MissingOrchestratorError` if absent (`172`) → `run_output = await orchestrator.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)` (`173`) → returns `PipelexRunResultStart(..., workflow_id=run_output.workflow_id)`. The `/start` route passes `requested_execution_mode=extras.execution_mode` (`424`).
- **`resolve_execution_mode`** — `pipelex-api/api/api_config.py:81-99`: `resolve_execution_mode(requested, *, config) -> PipelexExecutionMode`. Deployment default wins unless the caller supplied a *different* mode **and** `config.allow_request_execution_mode_override` is true; a forbidden override raises **403** (`EXECUTION_MODE_OVERRIDE_FORBIDDEN`). `ApiConfig` (`40-53`) + `api.toml` (base: `execution_mode = "direct"`, `allow_request_execution_mode_override = false`).
- **The orchestrators already return the full output.** `_plugins/pipelex/runtime_bridge/direct_orchestrator.py`: `DirectOrchestrator.run` returns `serialize_completed_output(pipe_output=…, workflow_id=None)`. `/start` only reads `.workflow_id`; `/execute` will read the **output** off the same `PipelexPipeRunOutput`. `PipelexExecutionMode`: `DIRECT`, `TEMPORAL_BLOCKING`, `TEMPORAL_FIRE_AND_FORGET`, `MISTRAL_NATIVE` (`_plugins/pipelex/runtime_bridge/execution_mode.py:4-27`).

For full orientation on the two dispatch seams (per-call registry vs boot-global hub slots), see §3 "Background" of the sibling plan `wip/plugins/orchestrator-dispatched-validate.md`.

---

## 3. The design (locked)

A **single-repo override in `pipelex-api`**, mirroring `ApiRunner.start`. No core or `pipelex-temporal` change — the `DirectOrchestrator` / `TemporalBlockingOrchestrator` / `MistralNativeOrchestrator` in the registry already do everything needed.

- **Override `ApiRunner.execute`** (`@override`, alongside `start` and `validate`) with a `requested_execution_mode: PipelexExecutionMode | None = None` parameter. Body mirrors `start`:
    - `execution_mode = resolve_execution_mode(requested_execution_mode, config=get_api_config())` — **first**, so a forbidden per-request override 403s before any library load / run setup (exactly like `start`).
    - **Reject fire-and-forget:** if `execution_mode` resolves to `TEMPORAL_FIRE_AND_FORGET` (use a `match`/`is_*` on the enum — do not `==`-compare per the StrEnum standard), refuse with a 4xx (`/execute` is synchronous). See §"Open sub-decisions" for the coerce-to-blocking alternative.
    - `pipe_job, resolved_pipeline_run_id, _ = await pipeline_run_setup(...)` — build the rich `PipeJob` as `start` does.
    - `orchestrator = get_orchestrator_registry().get_optional(mode=execution_mode)`; `MissingOrchestratorError(mode=...)` if `None`.
    - `run_output = await orchestrator.run(pipe_job=pipe_job, delivery_assignment=None)` — `/execute` is synchronous, no delivery webhooks.
    - **Map `run_output` (`PipelexPipeRunOutput`) → `PipelexRunResultExecute`** (the protocol's execute result wrapping the full pipe output). This mapping is the one integration detail to verify (the orchestrator returns a *serialized* `PipelexPipeRunOutput` via `serialize_completed_output`, whereas the base `execute` wraps the raw `pipe_output`); confirm `PipelexPipeRunOutput` carries everything `PipelexRunResultExecute` needs and write the conversion. **This is the "clean vs more-complex-than-expected" hinge** — check it early.
- **Route** (`execute`, `340-373`): stop discarding extras. Parse like `/start` does (`run_request, extras = await _parse_request(request)`), then pass `requested_execution_mode=extras.execution_mode` into `runner.execute(...)`. No new wire field — `/execute` simply starts honoring the `execution_mode` extra it already parses.
- **Base `execute` stays untouched** in core (`runner.py:112`) — the local/CLI runtime legitimately uses the boot slot (it is not mode-dispatched). Only `ApiRunner` overrides, mirroring how it overrides `start`/`validate`.

**Behavior shift to call out (changelog + docs):** `/execute`'s backend is now selected by `execution_mode` (resolved from `api.toml` + optional policy-gated per-request override), **not** by `boot_orchestrator`. For a correctly-configured deployment these already agree (a Temporal deployment that runs `/start` distributed sets `execution_mode = "temporal_blocking"`), so the real-world delta is ~nil — but it removes the two-knobs-can-silently-disagree footgun and makes `execution_mode` authoritative. The base `api.toml` keeps `allow_request_execution_mode_override = false`, so per-request override only takes effect where a deployment opts in.

---

## 4. Phase + checkpoint

Single contained phase (one repo, one commit).

### Phase E0 — `pipelex-api` (branch off `refactor/orchestrator-agnostic-base` @ `a39841e`)

- Add the `ApiRunner.execute` override + fire-and-forget rejection + the `PipelexPipeRunOutput → PipelexRunResultExecute` mapping; rewire the `/execute` route to thread `extras.execution_mode`.
- Tests (see §"Testing").
- Docs: changelog entry (`/execute` now honors `execution_mode`, rejects fire-and-forget); document the dual-knob model (`execution_mode` authoritative for top-level dispatch; `boot_orchestrator` = execution stack) where `/execute`/`execution_mode` is described — likely `pipelex-api/docs/` and, if a section exists, the relevant `docs/specs/` doc (see §"Spec/conformance").
- Gates: `make agent-check`, `make agent-test`.

> **Checkpoint E-A** (the gate for `/execute`): `/execute` resolves and dispatches by `execution_mode`, honors the policy-gated override symmetrically with `/start`, rejects fire-and-forget, all gates green, docs + changelog updated. Clean-context `/code-review` on the `pipelex-api` diff. Capture an as-built (final signature, the output-mapping decision, test evidence).

---

## 5. Cross-repo state, pins, gates

- **Branch:** `pipelex-api` → `refactor/orchestrator-agnostic-base` @ `a39841e` (clean). This is the only repo touched.
- **Pins:** `pipelex-api/pyproject.toml:84-85` pins `pipelex = { path = "../_plugins", editable = true }`, so the core orchestrators/registry are live without a republish. No `pipelex-temporal` dependency is added (the `TemporalBlockingOrchestrator` is exercised by its own repo's tests; the API change is testable with `DirectOrchestrator` + a stub).
- **Gates:** `make agent-check`, `make agent-test` (in `pipelex-api`). If a `docs/specs/` heading is touched, run `make check-spec-links` (in `conformance/`).

---

## 6. Spec / conformance

- **No spec pins `/execute`'s backend-selection today.** The `/validate` verdict spec (`docs/specs/pipelex-mthds-protocol.md`) doesn't cover `/execute`; `/execute` dispatch lives in `pipelex-platform-api.md` / `pipelex-hosted-config.md`, where the HTTP arm is Phase-3-deferred and per-request override is not yet detailed. So this is **low conformance risk** and adds **no new wire field** (the `execution_mode` extra already exists; `/execute` just stops ignoring it).
- **Add documentation** of the new behavior: `/execute` honors a policy-gated per-request `execution_mode` and rejects fire-and-forget; `execution_mode` is authoritative for top-level dispatch while `boot_orchestrator` selects the execution stack. Put it where `/execute` / `execution_mode` is described (a `pipelex-api/docs/` page, and the hosted-config spec if you extend it). If you add or edit a spec heading, wire a `> Verified by:` link to a test and a matching `pytest.mark.spec(...)`, then `make check-spec-links`.
- **Conformance:** there is **no** `/execute` conformance module yet (deferred with the HTTP arm). Don't invent the deferred HTTP conformance arm here; cover the behavior with `pipelex-api`'s own tests (§"Testing"). If you later add a conformance surface for `/execute`'s mode-selection, link it bidirectionally.

---

## 7. Testing

In `pipelex-api` (no Temporal needed):

- **Direct dispatch:** `/execute` with `execution_mode` unset (or `direct`) runs in-process via `DirectOrchestrator` and returns the full output — equivalent result to today's boot-slot path on the direct base.
- **Per-request override, policy on:** with `allow_request_execution_mode_override = true`, a requested mode is honored; with it `false`, a *different* requested mode 403s (`EXECUTION_MODE_OVERRIDE_FORBIDDEN`) — reuse/mirror the existing `/start` override-policy tests.
- **Fire-and-forget rejection:** a resolved `temporal_fire_and_forget` on `/execute` returns the chosen 4xx, not a hang or a silent coerce (unless the coerce alternative is chosen — then assert blocking semantics).
- **Missing orchestrator:** a mode with no registered orchestrator raises `MissingOrchestratorError` with the install hint.
- **Output mapping:** assert the `PipelexPipeRunOutput → PipelexRunResultExecute` mapping preserves the full output (the integration hinge from §3). Use `DirectOrchestrator` (or a stub orchestrator returning a known `PipelexPipeRunOutput`).

---

## 8. Open sub-decisions for the implementing session

- **Fire-and-forget on `/execute`: reject (default) vs coerce-to-blocking.** Reject is more honest (you asked for something incompatible with a synchronous endpoint). Coerce-to-blocking is more lenient (execute always waits anyway, so f&f could just mean `temporal_blocking` here). Plan defaults to **reject** with a clear 4xx; flip only with a reason.
- **Output mapping shape.** Confirm `PipelexPipeRunOutput` (from `serialize_completed_output`) carries everything `PipelexRunResultExecute` needs. If it doesn't, decide whether to enrich the orchestrator output or to keep a thin execute-specific adapter — and note it in the as-built. This determines whether the change stays "clean" or grows.
- **Deployment-config coherence.** Note for Phase D (hosted Temporal flavor, in the parent plan): the hosted runner's `api.toml execution_mode` must be set coherently (it already is for `/start`); after this change it also governs `/execute`. `boot_orchestrator` remains for the execution stack. No code change here — just a deployment note so the two knobs are set with intent.
