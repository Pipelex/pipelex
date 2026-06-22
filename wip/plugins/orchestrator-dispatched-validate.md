# Plan — orchestrator-dispatched `/validate` (reverse/extend F2)

> **⚠️ SUPERSEDED (2026-06-22) by [`orchestration-mode-and-delivery-split.md`](orchestration-mode-and-delivery-split.md).** This plan was implemented (V0–V3, committed across all three repos) on top of the **flat** `PipelexExecutionMode` enum, and registered the bundle validator under **both** temporal modes (`temporal_blocking` + `temporal_fire_and_forget`) — a double-registration that existed only because the flat enum lacked a delivery axis. The orchestration-mode/delivery split (now DONE, incl. Phase 4 — the `pipelex-mistralai-workflows` migration) **removed that flatness**: delivery became a `DeliveryMode` parameter to `OrchestratorProtocol.run`, the two Temporal orchestrators collapsed into one registered **once** under `"temporal"`, and the `/validate` double-registration collapsed to a single `"temporal"` validator. The orchestrator-dispatched `/validate` mechanism this plan built still stands; only the keying changed (open `orchestration_mode` token, single registration). Read the split plan for the current surface; this doc is kept for history. (The "nothing coded yet" status below is itself stale — this plan was completed; see its sibling `execute-per-request-execution-mode.md` for the as-built cross-references.)

**Status:** ready-to-execute plan for a fresh session. Design is locked (decisions below); nothing coded yet. This is **Plan 1 of 2** — its sibling is `wip/plugins/execute-per-request-execution-mode.md` (run this one first). It **reverses/extends locked decision F2** of the orchestrator-agnostic-runner effort (tracker: `_plugins/TODOS.md`; parent plan: `_plugins/wip/plugins/orchestrator-agnostic-runner-and-flavors.md`).

> **START HERE (cold start).** Read this whole doc, then §"Current state" and §"Background". Begin on the branches named in §"Cross-repo state". The work spans `pipelex` (core seam) → `pipelex-temporal` (wire the surviving validate machinery into the seam) → `pipelex-api` (mode-aware dispatch + route). Mistral is a gated follow-up (do **not** build it). Same one-commit-per-checkpoint / clean-context-`/code-review` discipline as the rest of the effort.

---

## 1. The ask + locked decisions

**The ask (user, verbatim intent):** make `/validate` dispatchable through the active orchestrator, the way `/start` runs a pipe — instead of always validating in-process on the API runner.

1. **Temporal flavor** → `/validate` can dispatch the surviving `act_dry_validate` activity to a worker (restore the behavior F2 removed).
2. **Do both** → keep the in-process path for the agnostic base / `direct` mode AND add the dispatched path for orchestrator flavors. Validate becomes `execution_mode`-aware: `direct` → in-process; `temporal_*` → worker activity. The base validates in-process because it has no worker — expected.
3. **Mistral flavor** → the seam must be **generic across orchestrators**, not Temporal-specific, so a Mistral validate arm can be added later.

**Locked decisions (do not re-litigate):**

- **A — Verdict as value (return a union).** The seam **returns** the verdict, it does not raise it. Valid → the canonical report; invalid → the structured invalid report. Respect the existing `/validate` contracts in `docs/specs/` and `conformance/` and their spirit (200-always for any produced verdict; non-2xx = no verdict).
- **B — Seam returns the assembled report.** The worker returns the raw artifact bundle (`DryValidateResult`); the **orchestrator plugin** (running in-API) assembles the canonical report via core `build_validation_report`. The API route stays thin and uniform. (Revisit only if this turns out materially more complex than the in-route assembly alternative — see §"Open sub-decisions".)
- **C — Mistral deferred** as a follow-up (gated on its own `mistralai-2.x` work). Build the generic seam now so Mistral slots in later.
- **D — Reuse `PipelexExecutionMode`.** Validate is inherently blocking, so `temporal_blocking` and `temporal_fire_and_forget` collapse for validate: the Temporal plugin registers the **same** validator under **both** temporal modes. `/validate` reuses `resolve_execution_mode` + the override policy wholesale.
- **Per-call, presence-based, NOT boot-gated.** Validate dispatch joins the **per-call registry family** (like `/start`), not the boot-global hub-slot family (like `/execute` today). The validator is registered **unconditionally** by the plugin (exactly how `pipelex-temporal` already registers its run orchestrators); only hub-slot *claiming* is `boot_orchestrator`-gated, and validate claims no slot. This resolves the brief's old open question #5: `dispatch_dry_validate` needs only a reachable Temporal client + a worker with the validate workflow registered — **not** a runner booted-as-Temporal.

---

## 2. Current state (post-Phase C — the thing we are reversing)

Phase C made `pipelex-api` orchestrator-agnostic (`pipelex-api` tip `a39841e` on `refactor/orchestrator-agnostic-base`). As part of it, **F2** collapsed `/validate` to a single in-process path. F2 verbatim (from the parent plan, §3):

> **F2 — Validate always DIRECT in-process.** Drop the Temporal validate branch entirely; `ApiRunner.validate()` always calls `validate_bundles_in_process(...)`. Removes the `pipelex.temporal` imports (`dispatch_dry_validate` / `DryValidateArg`). Behavior change to call out at handoff: the API runner now loads the method library to validate, which the prior D10/D14 design deliberately pushed onto the worker. Acceptable per decision; note the resource/isolation implication on the hosted runner in that repo's docs.

So today:

- `pipelex-api/api/routes/pipelex/pipeline.py` `ApiRunner.validate` (lines `182-217`) calls only `validate_bundles_in_process(...)` — always in-process, loads the method library on the runner, **no `execution_mode` awareness**. Docstring at line `73` and the route comment at `190-193` assert "always DIRECT in-process (F2)" — **these are the sentences to edit.**
- The route `api/routes/pipelex/validate.py` (lines `141-201`) catches only `ValidateBundleError` (its old `WorkflowExecutionError` catch was removed).
- **The worker machinery survives intact and tested in `pipelex-temporal`, just orphaned** (no longer called by the API): `pipelex_temporal/tprl_pipe/{act_dry_validate,wf_dry_validate,dry_validate_dispatch}.py`, plus unit + in-memory-Temporal integration tests. **This is a re-wiring, not a rebuild.**
- **Phase C dropped `pipelex-api`'s dependency on `pipelex-temporal` entirely.** `pipelex-api/pyproject.toml` deps are now just `pipelex`, `mthds`, `fastapi`, `pyjwt`, `uvicorn`. The agnostic base must stay temporal-free **even in tests** (see §"Testing").

The old dual-path `ApiRunner.validate` (the exact code to mirror) is one commit back: `git -C pipelex-api show a39841e^:api/routes/pipelex/pipeline.py`. Its Temporal arm dispatched **first** (`dispatch_dry_validate(DryValidateArg(mthds_contents, mthds_sources, allow_signatures))`) so every failure surfaced through the worker's `validate_bundle` cascade with the same categorized `ValidateBundleError` identity the direct path raises; then it parsed blueprints **cheaply (no library)** via `PipelexInterpreter.make_pipelex_bundle_blueprint(...)` and assembled the canonical report via `build_validation_report(blueprints=…, pipe_io_contracts=result.pipe_io_contracts, dry_run_result=result.dry_run_outputs, pending_signatures=result.pending_signatures, graph_spec=result.graph_spec)`. The route's old arm caught `WorkflowExecutionError`, recovered the `ValidateBundleError` report (→ 200 invalid) or re-raised a genuine fault (→ 5xx). **Mirror this split**, but as a returned verdict (decision A), not an exception.

---

## 3. Background — the two existing dispatch seams (cold-start orientation)

The runner already has **two** orchestration mechanisms. Validate joins the first.

**(a) Per-call `OrchestratorRegistry`** (the model validate mirrors), all in core under `_plugins/pipelex/` (a worktree of `pipelex`):

- `pipelex/plugins/orchestrator_registry.py:21` — `OrchestratorProtocol.run(self, *, pipe_job, delivery_assignment) -> PipelexPipeRunOutput` (single-method `@runtime_checkable` Protocol).
- `pipelex/plugins/orchestrator_registry.py:24-42` — `OrchestratorRegistry(orchestrators: dict[PipelexExecutionMode, OrchestratorProtocol])` with `get_optional(*, mode) -> OrchestratorProtocol | None` and `has(*, mode) -> bool`.
- `pipelex/plugins/registrar.py:163-173` — `PluginRegistrar.add_orchestrator(*, mode, orchestrator)` (uses an internal `_add` helper that fail-louds on duplicates).
- `pipelex/plugins/direct/direct_plugin.py:18-19` — core `DirectOrchestratorPlugin.register` calls `registrar.add_orchestrator(mode=DIRECT, orchestrator=DirectOrchestrator())`; wired unconditionally via `pipelex/plugins/builtins.py:27-28`.
- `pipelex/pipelex.py:391-395` — registries are built **once at boot** from the registrar and stored on the hub; `:206` shows `boot_orchestrator` is a separate boot-global string (claims hub slots) — orthogonal to per-call mode dispatch.
- `pipelex/runtime_bridge/bridge.py:92-95` — per-call dispatch: `get_orchestrator_registry().get_optional(mode=...)` → `MissingOrchestratorError` if absent (no silent fallback) → `orchestrator.run(...)`.
- `pipelex/runtime_bridge/execution_mode.py:4-27` — `PipelexExecutionMode`: `DIRECT`, `TEMPORAL_BLOCKING`, `TEMPORAL_FIRE_AND_FORGET`, `MISTRAL_NATIVE`.
- `pipelex/runtime_bridge/exceptions.py:9-40` — `MissingOrchestratorError` (carries a per-mode pip-install hint).
- `pipelex/runtime_bridge/direct_orchestrator.py` — `DirectOrchestrator.run` returns `serialize_completed_output(pipe_output=…, workflow_id=None)`; scopes an in-process router so nested sub-pipes stay in-process even inside a Temporal worker.
- `pipelex-temporal/pipelex_temporal/temporal_plugin.py:126-147` — `TemporalPlugin.register` adds the run orchestrators **unconditionally** under `TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET`; `claim_*` hub slots only `if boot_orchestrator == "temporal"`. Entry point: `[project.entry-points."pipelex.plugins"] temporal = "pipelex_temporal.temporal_plugin:TemporalPlugin"`.

**(b) Boot-global hub slots** — `get_pipe_run()` / `get_pipe_router()` etc., claimed at boot when `boot_orchestrator == "temporal"`. This is what `/execute` uses today (sibling plan converts it to (a)). Validate does **not** touch this.

**Core validate building blocks** (reused as-is, all under `_plugins/pipelex/`):

- `pipelex/pipeline/validate_in_process.py:44-51` — `async validate_bundles_in_process(*, mthds_contents, mthds_sources=None, library_dirs=None, allow_signatures=False, log_context="validate") -> PipelexValidationReport`. Loads + tears down the method library internally (heavy, lifecycle-managed). Raises `ValidateBundleError` on an invalid bundle.
- `pipelex/pipeline/validation_report.py:63-94` — `build_validation_report(*, blueprints, pipe_io_contracts, dry_run_result, pending_signatures, graph_spec=None) -> PipelexValidationReport`. The single assembly point.
- `pipelex/pipeline/validation_report.py:29-60` — `PipelexValidationReport` (extends the neutral `ValidationReport`; `is_valid: Literal[True]` is the valid-arm discriminant; Pipelex-branded envelope).
- `pipelex/pipeline/exceptions.py:72-161` — `ValidateBundleError`; `.to_error_report()` (line `129`) → `ErrorReport` with `validation_errors` populated.
- `pipelex/base_exceptions.py:309-349` — `ErrorReport` (`validation_errors: list[ValidationErrorItem] | None`); `:269-307` `ValidationErrorItem`.
- `pipelex/core/interpreter/interpreter.py` — `PipelexInterpreter.make_pipelex_bundle_blueprint(*, mthds_content, mthds_source)` (cheap parse, no library).

**Surviving Temporal validate machinery** (in `pipelex-temporal`, reused as-is):

- `pipelex_temporal/tprl_pipe/act_dry_validate.py:62-74` — `DryValidateArg(mthds_contents, mthds_sources, allow_signatures, pipe_code)` (plain `BaseModel`, no `temporalio`); `:77-98` — `DryValidateResult(dry_run_outputs, graph_spec, pending_signatures, pipe_io_contracts)`. **These fields map 1:1 onto `build_validation_report`.**
- `pipelex_temporal/tprl_pipe/dry_validate_dispatch.py:22-66` — `async dispatch_dry_validate(arg, *, task_queue=None, should_auto_connect_temporal=True) -> DryValidateResult`. Needs a reachable Temporal client + a worker with `WfDryValidate`/`act_dry_validate` registered; **not** boot-as-Temporal. An invalid bundle comes back as `WorkflowExecutionError` carrying the recovered `ErrorReport` (`error_type == "ValidateBundleError"`); a genuine fault recovers no such report.
- Tests to mirror: `tests/unit/pipelex_temporal/test_dry_validate_dispatch.py`, `tests/integration/pipelex_temporal/test_dry_validate_activity_in_memory.py`, `tests/integration/pipelex_temporal/test_validate_sweep_stays_in_process.py`.

---

## 4. The design (locked)

A new **generic, per-call validate seam**, mirroring the orchestrator seam exactly. Core declares the contract (SDK-agnostic core types only); the plugin implements it; the API resolves the mode and dispatches. **The Temporal wire payloads (`DryValidateArg`/`DryValidateResult`) stay in `pipelex-temporal`** — the seam never exposes them, so no payload migration to core is needed.

### 4.1 Core seam (proposed names — finalize in implementation)

- **Verdict union** (core types only): `BundleValidationVerdict = PipelexValidationReport | ErrorReport`. Valid arm = `PipelexValidationReport`; invalid arm = `ErrorReport` (carrying `validation_errors`). This is exactly what the route already maps to the wire (`ValidReport` / `_invalid_report_response`). Discriminate in the route by `isinstance(verdict, PipelexValidationReport)`.
- **Protocol** `BundleValidatorProtocol` (e.g. `pipelex/plugins/bundle_validator_registry.py`):

  ```
  async def validate_bundles(
      self, *, mthds_contents, mthds_sources, allow_signatures, library_dirs,
  ) -> BundleValidationVerdict: ...
  ```

  Returns the verdict (valid report | invalid `ErrorReport`); **raises only** for no-verdict infra faults (→ global 5xx). Note: `library_dirs` is host context the **in-process** arm needs; the Temporal arm ignores it (the worker loads its own library).
- **Registry** `BundleValidatorRegistry(validators: dict[PipelexExecutionMode, BundleValidatorProtocol])` with `get_optional(*, mode)` / `has(*, mode)` — copy `OrchestratorRegistry`.
- **Registrar** `PluginRegistrar.add_bundle_validator(*, mode, validator)` — copy `add_orchestrator` (reuse the `_add` dup-guard helper).
- **Hub** `get_bundle_validator_registry()` + boot wiring in `pipelex/pipelex.py` next to the orchestrator registry (built once at boot from the registrar).
- **Missing-validator error** `MissingBundleValidatorError(mode=...)` — copy `MissingOrchestratorError`, with a per-mode install hint.
- **Core direct impl** `DirectBundleValidator` (registered by the core `direct` plugin, alongside `DirectOrchestrator`): calls `validate_bundles_in_process(mthds_contents=…, mthds_sources=…, library_dirs=…, allow_signatures=…, log_context="API validate")`; **catches `ValidateBundleError` → returns `exc.to_error_report()`**; returns the `PipelexValidationReport` on success. Any other exception propagates (→ 5xx). This gives the agnostic base in-process validate "for free" via the same seam.

### 4.2 Temporal impl (in `pipelex-temporal`)

- **`TemporalBundleValidator`** (implements `BundleValidatorProtocol`): builds `DryValidateArg(mthds_contents, mthds_sources, allow_signatures)` (ignores `library_dirs`) → `await dispatch_dry_validate(arg)`. On success (`DryValidateResult`): parse blueprints cheaply with `mthds_sources` threaded (so success-path `bundle_blueprint.source` matches the failure path), then `build_validation_report(blueprints=…, pipe_io_contracts=result.pipe_io_contracts, dry_run_result=result.dry_run_outputs, pending_signatures=result.pending_signatures, graph_spec=result.graph_spec)` → return the `PipelexValidationReport`. On `WorkflowExecutionError`: recover the `ErrorReport`; if it is a validation verdict (`error_type == ValidateBundleError.__name__`) → **return** the `ErrorReport` (invalid verdict); otherwise **re-raise** (genuine fault → 5xx).
- **Register it unconditionally** in `TemporalPlugin.register` under **both** `TEMPORAL_BLOCKING` and `TEMPORAL_FIRE_AND_FORGET` (decision D), right next to the existing `add_orchestrator` calls (which are already unconditional). Claims no hub slot.

### 4.3 API dispatch + route (in `pipelex-api`)

- The dispatch lives on `ApiRunner` (mirrors how `ApiRunner.start` resolves the mode and dispatches), but **returns the verdict union** so the route maps it as a value (decision A). Suggested shape: a method `ApiRunner.validate_verdict(*, mthds_contents, mthds_sources, allow_signatures, requested_execution_mode) -> BundleValidationVerdict` that does `resolve_execution_mode(...)` → `get_bundle_validator_registry().get_optional(mode=...)` (→ `MissingBundleValidatorError` if absent) → `validator.validate_bundles(mthds_contents=…, mthds_sources=…, allow_signatures=…, library_dirs=self.library_dirs)`. Keep `ApiRunner` as the holder of library config (unchanged `self.library_dirs` sourcing).
- **The protocol method** `ApiRunner.validate(...) -> PipelexValidationReport` (the `PipelexMTHDSProtocol` `@override`) stays raise-based for protocol conformance: it can delegate to `validate_verdict` and re-raise on the `ErrorReport` arm. The **route uses `validate_verdict`** for the verdict-as-value mapping. (If nothing besides the route calls the protocol `validate`, the cold session may simplify — confirm first.)
- **Route** `validate.py` (`141-201`): replace the `try/except ValidateBundleError` with: resolve render formats (unchanged) → `verdict = await ApiRunner(...).validate_verdict(..., requested_execution_mode=request_data.execution_mode_or_equivalent)` → `if isinstance(verdict, PipelexValidationReport): return <ValidReport built as today>` else `return _invalid_report_response(verdict, requested_formats=...)`. Genuine faults propagate to the global `problem+json` handler. **`ValidReport` / `InvalidReport` / `_invalid_report_response` are unchanged** (`validate.py:79-138, 204-228`) — only the control flow changes from catch-exception to match-on-returned-verdict.
- Wire the `execution_mode` extra into the validate request shape if not already present (the `/validate` request must carry the optional per-request mode the same way `/start` does, gated by `resolve_execution_mode`'s policy). Confirm `ValidateRequest` vs `PipelineApiExtras` and thread it consistently.

### 4.4 Why the wire contract is preserved (conformance-neutral)

The valid/invalid wire arms (`ValidReport`, `InvalidReport`), the 200-always verdict contract, and the structured `validation_errors[]` are **identical** regardless of backend. The dispatched arm assembles the **same** `PipelexValidationReport` via the **same** `build_validation_report`, and surfaces the **same** `ValidateBundleError`-derived `ErrorReport` on invalid. So the existing `/validate` conformance must pass **unchanged** — that byte-identity is the acceptance bar (§"Testing").

---

## 5. Phased implementation + checkpoints

Each phase lands in its own repo on its own branch, one commit per checkpoint. Cut new branches from the named tips.

### Phase V0 — core seam (`pipelex`, in `_plugins/`, branch off `refactor/Plugins-4`)

- Add the protocol, registry, registrar method, hub getter, boot wiring, `MissingBundleValidatorError`, the `BundleValidationVerdict` type, and `DirectBundleValidator` (registered by the `direct` plugin). Mirror the orchestrator seam file-for-file.
- Gates: `make agent-check`, `make tb` (boot/config sanity — the new registry must build at boot), `make agent-test`.

### Phase V1 — Temporal validator (`pipelex-temporal`, branch off `refactor/own-temporal-config` @ `6d9adff`)

- Implement `TemporalBundleValidator`; register it unconditionally under both temporal modes. Reuse `dispatch_dry_validate` / `DryValidateResult` as-is.
- Add an in-memory-Temporal integration test (mirror `test_dry_validate_activity_in_memory.py`): the validator returns an assembled `PipelexValidationReport` for a valid bundle and an `ErrorReport` (with `validation_errors`) for an invalid one; a genuine fault re-raises.
- Gates: `make agent-check`, `make agent-test`.

> **Checkpoint V-A** (MAJOR boundary, natural session break): core + `pipelex-temporal` green together; the seam exists and the Temporal plugin contributes through it, verified against the in-memory Temporal env. The base still has no idea Temporal exists. Fan out a clean-context `/code-review` on the core seam diff + the `pipelex-temporal` diff.

### Phase V2 — API dispatch + route + F2 reversal (`pipelex-api`, branch off `refactor/orchestrator-agnostic-base` @ `a39841e`)

- Add `ApiRunner.validate_verdict`, rewire the route to verdict-as-value, thread `execution_mode` into the validate request, keep `ValidReport`/`InvalidReport`/`_invalid_report_response` unchanged.
- Reverse the F2 prose: the docstring at `pipeline.py:73` and the route comment at `190-193`; restore the dual-backend description in `pipelex-api/docs/pipe-validate.md` (the runner-sizing/library-load note becomes flavor-conditional, not absolute).
- Gates: `make agent-check`, `make agent-test`. **Keep `pipelex-temporal` out of `pipelex-api`'s deps** — test the dispatch+route+verdict-mapping with a **stub** `BundleValidatorProtocol` registered for a test mode (no temporal import). The real Temporal arm is covered in V1.

### Phase V3 — bookkeeping + spec/conformance

- Update the parent plan's **F2** decision (mark it reversed/extended; point to this doc) in `_plugins/wip/plugins/orchestrator-agnostic-runner-and-flavors.md`, and the Phase C as-built note in `_plugins/TODOS.md`. Add a `CHANGELOG.md` entry (dual-backend `/validate`).
- `docs/specs/`: the verdict contract does **not** change. Optionally add one clarifying sentence that the verdict is backend-independent (in-process **or** orchestrator-dispatched) to `pipelex-mthds-protocol.md` "Validation status codes" (`130-151`) and/or `command-surface-map.md` row 6 — **only if** added with a `> Verified by:` link + a matching `pytest.mark.spec(...)`. If you touch any spec heading, run `make check-spec-links` (in `conformance/`).
- `conformance/`: the existing `/validate` tests (`tests/pipelex_api/test_validate_{valid,diagnostic,render}.py`, `tests/pipelex_agent/test_validate_{envelope,errors}.py`, the `validate-error-qa/` corpus) must pass **unchanged** against the in-process (`direct`) arm. A conformance test of the **dispatched** arm needs Temporal in the conformance env — **defer** it (note the gap explicitly, like the other deferred HTTP arms; the in-memory coverage in V1 is the safety net meanwhile).

> **Checkpoint V-B** (THE gate for validate): `pipelex-api` dispatches validate by mode, the route returns verdict-as-value, F2 prose reversed, all gates green in all three repos, existing `/validate` conformance green unchanged, `make check-spec-links` green if specs touched. Clean-context `/code-review` on the `pipelex-api` diff. Capture an as-built (final names, signatures, divergences, test evidence).

### Phase V-Mistral — DEFERRED (decision C)

- Add a `MistralBundleValidator` later (genuine dispatch mirroring Temporal **or** an in-process passthrough — decide then). Gated on `pipelex-mistralai-workflows`' `mistralai-2.x` work. The generic seam means this lands without touching core or the API.

---

## 6. Cross-repo state, pins, gates

**Branches / tips (verified 2026-06-21):**

- `_plugins` (pipelex core worktree): `refactor/Plugins-4` (this doc is the only dirty file — it overwrites the prior brief).
- `pipelex-api`: `refactor/orchestrator-agnostic-base` @ `a39841e` (clean).
- `pipelex-temporal`: `refactor/own-temporal-config` @ `6d9adff` (clean). **Private** (`LicenseRef-Proprietary` + `Private :: Do Not Upload`) — install via `git+ssh`, never PyPI.
- `pipelex-mistralai-workflows`: `feature/Mistral-native` (deferred — ignore).

**Editable pins (local dev):** `pipelex-api/pyproject.toml:84-85` and `pipelex-temporal/pyproject.toml` both pin `pipelex = { path = "../_plugins", editable = true }`. So a core (`_plugins`) edit is live in both immediately. **`pipelex-api` does not depend on `pipelex-temporal`** (Phase C dropped it) — for any *manual* end-to-end check of the Temporal arm in the API, install `pipelex-temporal` as an editable **dev-only** extra; never add it to the base runtime deps.

**Gates:** core `_plugins` → `make agent-check` / `make tb` / `make agent-test`. `pipelex-api` and `pipelex-temporal` → `make agent-check` / `make agent-test`. `conformance` → `make check-spec-links` (+ its pytest suite for the `/validate` arm).

---

## 7. Testing

- **Core (V0):** unit-test the registry + `DirectBundleValidator` (valid → report; invalid bundle → `ErrorReport` with `validation_errors`; missing mode → `MissingBundleValidatorError`). `make tb` must stay green (boot builds the new registry).
- **Temporal (V1):** in-memory-Temporal integration test of `TemporalBundleValidator` (valid → assembled report; invalid → `ErrorReport`; genuine fault → re-raise). Mirror the existing in-memory validate tests.
- **API (V2):** dispatch+route+verdict-mapping tested against a **stub** validator (no temporal). Assert: `direct` → in-process verdict; a stubbed temporal-mode validator's returned `ErrorReport` → 200 `InvalidReport`; a stubbed raised fault → 5xx; missing-mode → `MissingBundleValidatorError`.
- **Conformance (V3):** existing `/validate` suite green **unchanged** (byte-identical verdicts) = the acceptance bar. Dispatched-arm conformance deferred (note the gap).

---

## 8. Open sub-decisions for the implementing session

- **Final names/locations** for the seam (`BundleValidator*`, file homes). Proposed above; confirm against the orchestrator-seam layout.
- **Decision B sanity check:** if in-plugin assembly (Temporal arm calls `build_validation_report`) proves more tangled than expected, the fallback is in-route assembly (route gets `DryValidateResult` and assembles) — but that would re-expose worker payloads to the API, so prefer in-plugin. Flag if you hit friction.
- **Protocol `validate` fate:** keep as a raise-based conformance wrapper delegating to `validate_verdict`, or simplify if the route is its only caller. Confirm callers first.
- **`execution_mode` on the validate request:** confirm the request model/extras plumbing matches `/start`'s, and that the override policy (403 on forbidden override) applies identically.

---

## 9. Progress / as-built (live)

> Appended at each checkpoint. Final names, divergences, test evidence — enough to cold-resume.

### Phase V0 — core seam — DONE (uncommitted at Checkpoint V-A)

Mirrors the orchestrator seam file-for-file. Final names/locations:

- `pipelex/plugins/bundle_validator_registry.py` — `BundleValidatorProtocol` (`@runtime_checkable`, single async `validate_bundles(*, mthds_contents, mthds_sources, allow_signatures, library_dirs)`), `BundleValidatorRegistry` (`get_optional` / `has` / `modes`), and the `BundleValidationVerdict` type alias.
- `pipelex/pipeline/direct_bundle_validator.py` — `DirectBundleValidator` (calls `validate_bundles_in_process(..., log_context="API validate")`; catches `ValidateBundleError` → returns `exc.to_error_report()`; other exceptions propagate).
- `pipelex/plugins/exceptions.py` — `DuplicateBundleValidatorError`. `pipelex/plugins/registrar.py` — `bundle_validators` store + `_bundle_validator_sources` + `add_bundle_validator` (reuses the `_add` dup-guard). `pipelex/plugins/direct/direct_plugin.py` — registers `DirectBundleValidator` under DIRECT alongside `DirectOrchestrator`.
- `pipelex/runtime_bridge/exceptions.py` — `MissingBundleValidatorError(mode=...)` (per-mode install hint, mirrors `MissingOrchestratorError`). `pipelex/hub.py` — field + setter + getter + module `get_bundle_validator_registry()`. `pipelex/pipelex.py` — boot wiring `set_bundle_validator_registry(BundleValidatorRegistry(plugin_registrar.bundle_validators))` next to the orchestrator registry.

**Divergence from §4.1 (the only one, forced by `reportImportCycles = true`):** the verdict's valid arm is typed at the **MTHDS-protocol base `ValidationReport`** (a leaf type), NOT the concrete `PipelexValidationReport`. Naming the concrete envelope from the hub-reachable registry closes a real import cycle (`hub → bundle_validator_registry → validation_report → bundle_validator → pipe_run → hub`) — pyright follows `TYPE_CHECKING` edges, so the cycle gates. This mirrors how the orchestrator seam returns the leaf `PipelexPipeRunOutput`, and is brand-correct (the generic seam speaks the protocol report; the Pipelex envelope is recovered at the API edge). `DirectBundleValidator` still returns the precise `PipelexValidationReport | ErrorReport` (a covariant narrowing); the API route recovers the precise valid arm for its `isinstance(verdict, PipelexValidationReport)` narrowing. Acceptance note for V2: `ApiRunner.validate_verdict` will narrow/cast the protocol's `ValidationReport` valid arm back to `PipelexValidationReport` (single documented point).

Tests: `tests/unit/pipelex/plugins/test_bundle_validator_registry.py` (registrar+registry+dup), `tests/unit/pipelex/pipeline/test_direct_bundle_validator.py` (verdict-as-value branches, mocked sweep), `tests/unit/pipelex/runtime_bridge/test_missing_bundle_validator_error.py` (per-mode hints). Gates: `make agent-check` green, `make tb` green, `make agent-test` green.

### Phase V1 — Temporal validator — DONE (uncommitted at Checkpoint V-A)

- `pipelex-temporal/pipelex_temporal/temporal_bundle_validator.py` — `TemporalBundleValidator` (import-light; `temporalio` + dispatch/wire/exception types resolved lazily inside `validate_bundles`, mirroring the orchestrators). Dispatches `dispatch_dry_validate(DryValidateArg(...))`; on success parses blueprints cheaply (`PipelexInterpreter.make_pipelex_bundle_blueprint`, threading `mthds_sources`) → `build_validation_report(...)`; on `WorkflowExecutionError` recovers the report and **returns** it iff `error_type == ValidateBundleError.__name__` (invalid verdict), else **re-raises** (genuine fault → 5xx). `library_dirs` ignored (worker loads its own library). Copied verbatim from the old dual-path `ApiRunner.validate` Temporal arm, but as a returned verdict (decision A).
- `temporal_plugin.py` — registers the SAME instance under **both** `TEMPORAL_BLOCKING` and `TEMPORAL_FIRE_AND_FORGET` (decision D), unconditionally, claims no hub slot.

Tests: `tests/integration/pipelex_temporal/test_temporal_bundle_validator_in_memory.py` (real worker, in-memory server: valid → assembled `PipelexValidationReport`; invalid → `ErrorReport` verdict; patches `is_temporal_boot_active` + `get_temporal_client` to route the validator's own `dispatch_dry_validate` through the in-memory env), `tests/unit/pipelex_temporal/test_temporal_bundle_validator.py` (verdict-vs-fault branching, mocked dispatch). Gates: `make agent-check` green, `make agent-test` green.

**Deferred observation:** dispatched `/validate` effectively requires `boot_orchestrator == "temporal"` (the reused executor's `is_temporal_boot_active()` guard), slightly at odds with the plan's decision #5 "not a runner booted-as-Temporal" — but identical to the run orchestrators' behavior, pre-existing, out of scope. Captured in [`validate-dispatch-requires-boot-active.md`](validate-dispatch-requires-boot-active.md).

> **Checkpoint V-A closed.** Core green + `pipelex-temporal` green together; the seam exists and the Temporal plugin contributes through it (verified against the in-memory Temporal env). Clean-context `/code-review` on both diffs: **zero findings, no fixes** (core: 3 independent passes; temporal: each flagged path verified against ground truth). One latent observation deferred ([`validate-verdict-subclass-parity-divergence.md`](validate-verdict-subclass-parity-divergence.md) — the `error_type` string-equality predicate, copied verbatim from the old route, would diverge from the direct arm's `except` only if a `ValidateBundleError` subclass is ever introduced; none exists). Commits: core `de709eea4`, `pipelex-temporal` `459e04d` (branch `feature/Orchestrator-dispatched-validate` in each).

### Phase V2 — API dispatch + route + F2 reversal — DONE (`pipelex-api`)

- `api/routes/pipelex/pipeline.py` — **dropped the `ApiRunner.validate` `@override`** (its only caller was the route; the parity test uses the base `PipelexMTHDSProtocol.validate`) and added **`ApiRunner.validate_verdict(*, mthds_contents, mthds_sources, allow_signatures, requested_execution_mode) -> PipelexValidationReport | ErrorReport`**. Mirrors `start`: `resolve_execution_mode(...)` FIRST (forbidden override → 403 before any dispatch) → `get_bundle_validator_registry().get_optional(mode=…)` (→ `MissingBundleValidatorError` if absent) → `validator.validate_bundles(..., library_dirs=…)`. The seam's valid arm is typed at the protocol-level `ValidationReport`, so `validate_verdict` recovers the concrete `PipelexValidationReport` with a single documented `cast` — the only narrowing point.
- `api/routes/pipelex/validate.py` — route rewired to **verdict-as-value**: `verdict = await ApiRunner().validate_verdict(...)`; `if not isinstance(verdict, PipelexValidationReport): return _invalid_report_response(verdict, ...)` else build `ValidReport`. Removed the `try/except ValidateBundleError`. Added `execution_mode: PipelexExecutionMode | None` to `ValidateRequest` (same plumbing as `/start`). `ValidReport`/`InvalidReport`/`_invalid_report_response` unchanged.
- **F2 prose reversed:** the `ApiRunner` class docstring, the `validate_verdict` docstring, the route docstring, and `docs/pipe-validate.md` ("Where validation runs" + the resource note + the 403 in the no-verdict list) now describe `execution_mode`-aware dual-backend validation (flavor-conditional library load) instead of "always DIRECT in-process."

**Sub-decision resolved (Protocol `validate` fate):** dropped, not kept as a raise-based wrapper. The route is the only `ApiRunner.validate` caller and switches to `validate_verdict`; re-raising from the returned `ErrorReport` would fabricate an exception no consumer catches (the original `ValidateBundleError` was already converted to a report by the validator). `ApiRunner` inherits the base `PipelexMTHDSProtocol.validate` (in-process — a sensible agnostic-base fallback, unused in practice).

Tests: `tests/unit/test_validate_dispatch.py` (NEW — stub validator for a non-direct mode proves registry dispatch + verdict mapping; invalid `ErrorReport` → 200, raised fault → 5xx, `MissingBundleValidatorError`, forbidden override → 403; no `temporalio` import). Three tests in `test_validate_errors.py` that mocked the removed `ApiRunner.validate` were re-pointed at `validate_verdict` (verdict-as-value: invalid arms now **return** the `ErrorReport`, the fault arm still **raises**) — the wire output is byte-identical. All other `/validate` tests (envelope, render, parity, conformance, allow_signatures) pass **unchanged** against the real direct arm. Gates: `make agent-check` green, `make agent-test` green (full suite).

### Phase V3 — bookkeeping + spec/conformance — DONE

- Parent plan F2 marked **REVERSED / EXTENDED** in [`orchestrator-agnostic-runner-and-flavors.md`](orchestrator-agnostic-runner-and-flavors.md) and in `_plugins/TODOS.md` (locked-decisions F2 + Phase C as-built). `pipelex-api` `CHANGELOG.md` `[Unreleased]`: the F2 "always DIRECT" bullet was rewritten in place (F2 never shipped) to the dual-backend verdict-as-value `/validate`; the `execution_mode` config bullet now names `/v1/validate` alongside `/v1/start`.
- **Spec / conformance:** no spec heading touched — the verdict contract (200-always, `is_valid` discriminant, structured `validation_errors[]`) is **unchanged**, and no spec or conformance test asserts the backend, so `make check-spec-links` is not needed. The direct-arm verdict wire is proven byte-identical by the `pipelex-api` suite (`test_validate_*`, `test_protocol_parity`, `test_protocol_conformance`, all green). The separate `conformance/` repo's live-wire `/validate` suite (`test_validate_{valid,diagnostic,render}.py`) is therefore expected green unchanged; a conformance test of the **dispatched** arm needs Temporal in the conformance env and is **deferred** (the V1 in-memory coverage is the safety net), exactly as the other deferred HTTP arms.

> **Checkpoint V-B — THE gate for validate.** `pipelex-api` dispatches validate by mode, the route returns verdict-as-value, F2 prose reversed across code + docs + trackers, all gates green in all three repos, existing `/validate` conformance green unchanged. Clean-context `/code-review` on the `pipelex-api` diff pending at this checkpoint.
