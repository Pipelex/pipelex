# Bug brief + e2e repro — the `/validate` dry-run sweep leaked nested controller sub-pipes to Temporal

> **Status:** bug FIXED (commit `3377babb` on `fix/Temporal-dry-run`); guarded by an in-process regression test. **This doc is the brief for adding a deployment-faithful RED scenario to the `temporal-e2e-validate` skill** — it is not yet added. Written for a cold start: everything needed is here.
>
> **Track:** part of the [distributed-execution](./README.md) track — the class of bug that only the true 3-process topology surfaces.

## 1. What the bug was

Running the **Pipelex API** (`../pipelex-api`) Temporal-enabled (`.pipelex/pipelex_override.toml` → `[temporal] is_enabled = true`) with a separate **Pipelex worker** (`../pipelex-worker`) up, calling the runner's `/validate` endpoint on a bundle containing a controller pipe returned **HTTP 422**:

```
ValidateBundleError (error_domain=input), 422
detail: "Dry run failed with 1 unexpected pipe failure(s):
  '<domain>.<batch_pipe>': ... status=DryRunStatus.FAILURE
  error_message=\"Dry run failed for pipe '<domain>.<batch_pipe>':
  Failed to execute workflow WfPipeRouter\""
```

The string **"Failed to execute workflow WfPipeRouter"** is produced only at `pipelex/temporal/tprl/workflow_caller.py` (the `(WorkflowAlreadyStartedError, RPCError)` branch of `WorkflowExecutor.execute_workflow`) — a **top-level** Temporal workflow dispatch from the submitter side. **A dry run should never reach that code.**

## 2. Root cause (one sentence)

`BundleValidator` builds a local in-process `PipeRouter` for the sweep but **never installs it as the active `get_pipe_router()` override**, so every nested controller sub-pipe (`pipe_controllers/sub_pipe.py`, `pipe_controllers/batch/pipe_batch.py` — all dispatch via `get_pipe_router()`) falls through to the **hub default**, which under a Temporal-enabled hub is the `TemporalPipeRouter` (wired in `pipelex/pipelex.py` when `get_config().temporal.is_enabled`). The top-level pipe ran in-process; its nested pipes leaked to Temporal.

**Why it 422s for a *standalone* `PipeBatch`/`PipeParallel` specifically:** the sweep dry-runs every pipe in the bundle individually. When it dry-runs a standalone batch pipe *directly*, the batch fans out over a mock list (`mock_inputs` mints ~3 items) and fires **N concurrent top-level Temporal dispatches with the same workflow id** (the id derives from the one shared `dry_run_pipeline_id`) → `WorkflowAlreadyStartedError` → `WorkflowExecutionError("Failed to execute workflow WfPipeRouter")` → the pipe is classified `FAILURE` → `DryRunError` → 422. A batch reached only *as a sub-pipe of a sequence* is a single serial dispatch — no collision — so it **silently round-trips Temporal and passes** (a false pass: still wrong, just not fatal).

## 3. The fix (already committed: `3377babb`)

Mirror the DIRECT-mode precedent in `pipelex/runtime_bridge/bridge.py::_run_direct`. In `pipelex/pipeline/bundle_validator.py`:

- keep the in-process router as `self._pipe_router` (don't discard it inside `PipeRun(...)`);
- wrap the per-pipe sweep loop in `validate_pipes` with `with scoped_pipe_router(self._pipe_router):`.

Now nested controllers resolve the in-process router; the whole sweep stays in-process regardless of backend.

**In-process regression guard (deterministic, no Temporal needed):**
`tests/integration/pipelex/pipeline/test_bundle_validator.py::TestBundleValidatorIntegration::test_standalone_batch_sweep_scopes_in_process_router` — installs a hub-default router that raises if reached, sweeps a standalone `PipeBatch`, asserts SUCCESS with the hub default never touched. (Verified RED without the scope.)

> ⚠️ A *separate* "secondary fix" to `dry_run_pipeline.py` (the graph step) was tried and **reverted** — it was misdiagnosed. See the correction block in [`/TODOS.md`](../../TODOS.md). Not relevant to this repro.

## 4. Why our PyTest suite didn't catch it (answer to "can in-process pytest reproduce it?")

**Partial confirm, with nuance — don't over-claim "impossible in-process":**

- The **leak itself** is reproducible in a single process with zero Temporal infrastructure — that's exactly what the committed regression test does (sentinel hub-default router). The **collision symptom** is *also* reproducible in-process in principle: the in-process Temporal test server (`--temporal-server none`/`time-skipping`) enforces the same workflow-id-reuse semantics, so concurrent same-id dispatches would still raise `WorkflowAlreadyStartedError`.
- So it escaped **not** because the topology can't show it, but because **no test crossed the seam "Temporal-enabled hub × the bundle-validation sweep":** the Temporal suite (`tests/integration/pipelex/temporal/`) exercises pipe *runs* via crate, never the validation *sweep*; the `BundleValidator` tests run under the default in-process hub, never the Temporal hub.
- Two reasons the **distributed (Mode 2) setup is still the right home** for a scenario:
  1. The silent **false-pass** shapes are invisible to a "does validate pass?" assertion — only an explicit "no Temporal dispatch happened" check (the sentinel test) or the standalone-batch collision shape exposes them.
  2. The **production symptom** (collision → 422 across a real API↔worker process boundary) matches the deployment topology exactly here, where a human actually hit it.

Net: the unit regression test guards the leak; the e2e scenario below guards the deployment-faithful symptom and documents the reproduction for the record.

## 5. The new scenario to add to `temporal-e2e-validate`

Lives under the skill at `.claude/skills/temporal-e2e-validate/`. Add this as a new scenario in `references/mode-2-tiers.md` (or a short new reference file).

**Which home?** This bug is **submitter-side** — the colliding top-level dispatches fire at *dispatch time*, regardless of whether the worker runs in the same process. So the true 3-process topology is the *deployment-faithful* home, **not the only one**: the same failure also reproduces under the classic in-process pytest harness. Treat Mode 2 here as the production-faithful demonstration (and the only thing that also exercises the genuinely cross-process surfaces — LibraryCrate propagation, serialization), and add the cheaper automated catch as a pytest companion (next subsection).

**Enabler that makes this clean:** `pipelex validate bundle` now has a `--temporal/--no-temporal` flag (added alongside the fix; parity with `pipelex run`). So the repro needs **no `pipelex_temporary_override.toml` juggling** — just pass `--temporal`. (The flag flips the boot's hub default to the Temporal router; with the fix, the sweep still stays in-process — which is the whole point being asserted.)

> **Forward-looking note (why the flag exists despite being a no-op for the sweep today):** once validation runs as a standalone Temporal activity ([`../dry-run-refactor/followup-temporal-validation-activity.md`](../dry-run-refactor/followup-temporal-validation-activity.md)), `--temporal` on `validate` stops being a no-op and becomes the switch that dispatches the sweep through that activity. Until then it only controls the boot, which is exactly what this scenario needs.

**Repro bundle — reuse an existing one, no new fixture needed:**
`tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds` already declares a **standalone `type = "PipeBatch"` pipe** (`batch_temporal_describe_topics`). When the sweep dry-runs that pipe directly, it fans out → the exact shape that 422'd in production.

### Prereqs
Temporal server + worker up, per `references/mode-2-setup.md` (read it first). The worker config is irrelevant to the leak — the leak is entirely submitter-side — but keep a worker up to mirror production (and so the first dispatch actually *starts*, yielding the true `WorkflowAlreadyStartedError` rather than an `RPCError`; both land in the same `except` branch, so both are RED, but the former matches production).

### GREEN — the fix in place (current `HEAD`)

```bash
# Server up (Mode 2). The boot connects to it; with the fix the sweep stays in-process,
# so the worker should receive NO workflow for this validate run.
timeout 120 .venv/bin/pipelex validate bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds \
  --temporal 2>&1 | tail -20
echo "EXIT=$?"
```

Expected: `EXIT=0`, `Successfully validated bundle ...`. Strong check: the worker session shows **no `WfPipeRouter` / `WfPipeRun` execution** for this run (it stayed idle) — `tmux capture-pane -t temporal-worker-router -p -S -200 | grep -i WfPipeRouter` returns nothing new.

### RED — temporarily revert the fix to prove the scenario bites

The fix is committed, so you must undo it in the working tree. **Surgical (preferred)** — neutralize just the scope in `pipelex/pipeline/bundle_validator.py`, inside `validate_pipes`:

```python
# change THIS:
with scoped_pipe_router(self._pipe_router):
    for pipe in sweepable_pipes:
        results[pipe.pipe_ref] = await self._classify_pipe(...)

# to THIS (drop the scope — the leak returns):
for pipe in sweepable_pipes:
    results[pipe.pipe_ref] = await self._classify_pipe(...)
```

(Alternative: `git revert --no-commit 3377babb` — but that also reverts the regression test + changelog; the surgical edit is cleaner.)

Re-run the GREEN command. Expected RED:

```
EXIT=1
Dry run failed with 1 unexpected pipe failure(s):
  'temporal_batch_test.batch_temporal_describe_topics': ... status=DryRunStatus.FAILURE
  error_message="... Failed to execute workflow WfPipeRouter"
```

The worker session will now show `WfPipeRouter` activity (the leak — validation dispatched to Temporal). **Restore the fix immediately:**

```bash
git checkout -- pipelex/pipeline/bundle_validator.py   # or: git revert --abort, if you used revert
```

### PASS criteria for the scenario
- GREEN run exits 0 **and** the worker received no workflow dispatch (validation stayed in-process under a Temporal-enabled boot).
- The documented RED procedure reproduces the `Failed to execute workflow WfPipeRouter` failure (sanity that the scenario actually exercises the leak path).

### Caveats to put in the scenario text
- **Shape matters.** Only a *standalone* `PipeBatch`/`PipeParallel` swept directly turns the leak fatal (concurrent same-id collision). A batch reached only as a sequence sub-pipe round-trips Temporal but passes — a false pass. `temporal_batch.mthds` has the standalone batch, so it's a valid RED trigger.
- **Worker up vs down both RED** (collision → `WorkflowAlreadyStartedError` vs no-worker → `RPCError`; same `except` branch). Keep the worker up to match production.
- **GREEN means "no dispatch happened."** Because the flag makes validation backend-agnostic, the strongest GREEN assertion is the worker-idle check, not just exit 0.

### Automated companion — a Mode-1 pytest (recommended alongside the Mode 2 scenario)

The Mode 2 scenario is agent-run, not CI-automated. Because this bug is submitter-side, the same catch can live as an ordinary pytest in the classic in-process Temporal harness (`tests/integration/pipelex/temporal/`, `--temporal-server none`/`local`, in-process worker) — fast, deterministic, runs in CI. That is the cheaper automated guard; Mode 2 remains the deployment-faithful demonstration. The three layers are complementary, not redundant:

| Layer | Where it runs | CI-automated | Cross-process surfaces (crate / serialization) | Status |
|---|---|---|---|---|
| Sentinel regression test (no Temporal) | plain pytest (`tests/integration/pipelex/pipeline/test_bundle_validator.py`) | ✅ | ✗ (deterministic stand-in for the hub default) | **exists** (`test_standalone_batch_sweep_scopes_in_process_router`) |
| **Mode-1 pytest (real Temporal, in-process server+worker)** | classic pytest temporal env | ✅ | ✗ (worker shares the process) | **proposed here** |
| Mode 2 scenario (3 separate processes) | the skill, agent-run | ✗ | ✓ | proposed in §5 |

Sketch of the Mode-1 pytest (author it in `tests/integration/pipelex/temporal/`, marked `temporal`, honoring `--temporal-server`):

- Boot/scope a **Temporal-enabled hub** so `get_pipe_router()`'s default is the real `TemporalPipeRouter` (mirror the existing temporal-suite fixtures that stand up the in-process server + worker).
- Run the real sweep — `BundleValidator().validate_pipes([...standalone PipeBatch...], ...)` — over `temporal_batch.mthds`'s `batch_temporal_describe_topics` (or an equivalent standalone `type = "PipeBatch"`).
- **Assert GREEN, strongly:** the sweep succeeds **and** no top-level workflow was started — e.g. spy on `pipelex.temporal.tprl.workflow_caller.WorkflowExecutor.execute_workflow` and assert it was never called (the deterministic analogue of the Mode 2 "worker-idle" check). This is what makes the fix's contract ("the sweep never reaches the Temporal router") an automated invariant, not just "validate didn't 422."
- Without the fix this test goes RED (the spy fires / a collision surfaces), exactly like the Mode 2 scenario.

This differs from the existing sentinel test in one meaningful way: it resolves the **real** `TemporalPipeRouter` as the hub default instead of a raising stand-in, so it also proves the *wiring* (config → hub default router) that the sentinel test deliberately bypasses.

## 6. Pointers

- Fix commit: `3377babb` — `fix(bundle-validator): prevent nested controller sub-pipes from leaking to Temporal during dry runs`.
- Fix site: `pipelex/pipeline/bundle_validator.py` (`__init__` keeps `self._pipe_router`; `validate_pipes` wraps the sweep in `scoped_pipe_router`). Precedent: `pipelex/runtime_bridge/bridge.py::_run_direct`.
- Hub wiring that makes the hub default Temporal: `pipelex/pipelex.py` (`set_pipe_router(make_temporal_pipe_router())` when `temporal.is_enabled`); resolution in `pipelex/hub.py::get_pipe_router` (contextvar override → else hub default).
- Leak sites: `pipelex/pipe_controllers/sub_pipe.py`, `pipelex/pipe_controllers/batch/pipe_batch.py` (`get_pipe_router().run(...)`).
- New CLI flag: `--temporal/--no-temporal` on `pipelex validate {bundle,pipe,method}` + `validate --all` (`pipelex/cli/commands/validate/`), guarded by `tests/unit/pipelex/cli/test_validate_temporal_flag.py`.
- In-process regression test: `tests/integration/pipelex/pipeline/test_bundle_validator.py::TestBundleValidatorIntegration::test_standalone_batch_sweep_scopes_in_process_router`.
- Skill: `.claude/skills/temporal-e2e-validate/SKILL.md` + `references/mode-2-setup.md` + `references/mode-2-tiers.md`.
