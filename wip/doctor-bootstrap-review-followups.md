# Doctor bootstrap — code-review follow-ups

Cold-start brief for the next session that lands the 15 findings surfaced by `/code-review xhigh` on top of the doctor-bootstrap follow-up fixes (branch `fix/Log-target`, staged but not yet committed at the time this plan was written).

## What this plan is for

The branch `fix/Log-target` already lands one commit (6e44d2f2 — the original stderr enforcement fix) and has 9 files staged on top implementing the 10 fix groups from `wip/doctor-bootstrap-followups.md`. A `/code-review xhigh` pass against the staged changes surfaced 15 new findings. Several are real bugs the user will hit; several are correctness gaps the prior plan partially addressed; the rest are robustness/contract concerns.

This document is the playbook for verifying each finding and, if confirmed, landing the fix.

## Background context (read this first if you're cold-starting)

### Where we are in git

- Branch: `fix/Log-target`, 1 commit ahead of `origin/fix/Log-target` (6e44d2f2 "fix: enforce stderr for agent CLI logging and output discipline").
- 9 files staged (not committed): the implementation of `wip/doctor-bootstrap-followups.md`'s 10 groups, plus the plan doc itself.
- The user has not yet committed the staged work; you can choose to commit it as-is (cleaner history) or bundle in these new fixes too (one bigger PR). Default recommendation: commit the staged work first, then land each group below as its own commit.

### What's staged (the diff this review covers)

The 9 staged files:

- `pipelex/cli/agent_cli/commands/agent_cli_factory.py` — `AGENT_CLI_STDERR_LOG_FIELDS` wrapped in `MappingProxyType`, `apply_agent_cli_output_discipline` now takes `log_level` and pins the pipelex log floor, `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES` now does `dict(AGENT_CLI_STDERR_LOG_FIELDS)` at module load.
- `pipelex/cli/agent_cli/commands/doctor_cmd.py` — filesystem checks now run BEFORE `setup_doctor_runtime`; bootstrap call threads `config_dir` for `--global`.
- `pipelex/cli/commands/doctor_cmd.py` — `setup_doctor_runtime` extended to accept `config_dir` + use `LogConfig.model_validate({**dump, **overrides})` + call `set_console_print_target` mirroring `Pipelex.__init__` + call `log.configure_if_unset`; `do_doctor_cmd` also reordered to run file checks first.
- `pipelex/core/validation.py` — guarded `migration_config = get_config().migration` with `try/except RuntimeError`.
- `pipelex/hub.py` — `setup_config` accepts `config_dir`.
- `pipelex/system/configuration/config_loader.py` — `load_config(config_dir=...)` takes IF branch that bypasses layering AND skips `ensure_global_config_exists()`.
- `pipelex/tools/log/log.py` — new `configure_if_unset` / `is_configured`.
- `tests/unit/pipelex/cli/test_agent_doctor_cmd.py` — `test_bootstrap_pins_console_targets_to_stderr` now also asserts `apply_agent_cli_output_discipline` is called.
- `tests/unit/pipelex/cli/test_doctor_cmd.py` — `test_do_doctor_cmd_delegates_layered_resolution_to_checks` now also asserts `setup_doctor_runtime` is called once with no args.

### Reference files for these fixes

| Concern | File | Key lines |
|---|---|---|
| Friendly validation translation | `pipelex/core/validation.py` | `log.verbose` at 22 and 35 (unguarded); `try/except RuntimeError` at 14-17 |
| Doctor bootstrap helper | `pipelex/cli/commands/doctor_cmd.py` | `setup_doctor_runtime` at 716-749; `check_config_files` at 107-146 (`load_config()` on 135); `check_models` at 752+ (gateway probe at 797-798); `do_doctor_cmd` at 856-896 |
| Agent doctor entry | `pipelex/cli/agent_cli/commands/doctor_cmd.py` | `agent_doctor_cmd` at 92-240; bootstrap call at 149-150; except boundary at 153-155 |
| Agent CLI factory | `pipelex/cli/agent_cli/commands/agent_cli_factory.py` | `AGENT_CLI_STDERR_LOG_FIELDS` at 57-64; `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES` at 66-69; `apply_agent_cli_output_discipline` at 78-100; factory body 102+; `log.redirect_to_stderr()` at 214 |
| Config loading | `pipelex/system/configuration/config_loader.py` | `load_config` 195-258 — IF branch skips `ensure_global_config_exists` (the else at 245 is the only call site); `backends_file_path` property at 119-122 (always layered) |
| Hub setup | `pipelex/hub.py` | `setup_config(..., config_dir=...)` at 114-127; `get_optional_instance` at 93-95; `get_required_config` at 212-227 |
| Log helpers | `pipelex/tools/log/log.py` | `is_configured` at 73-75; `configure_if_unset` at 77-94; `configure` at 96+ (raises on second call); `redirect_to_stderr` at 158+ |
| Gateway probe | `pipelex/system/pipelex_service/pipelex_service_config.py` | `is_pipelex_gateway_enabled()` at 45-71 — uses `config_manager.backends_file_path` (layered) when no path passed |

### Verification command

For most findings, `make agent-check && .venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ tests/unit/pipelex/system/ tests/unit/pipelex/tools/` is the smoke test. The current branch passes all of these — any new test added must keep them green.

## Findings to verify and fix

Each entry below names the finding, the smallest verification step (a command or a manual repro), and the fix. Severity reflects user-visible impact.

---

### Group A — Friendly error path regression (the big one)  **[high]**

These four findings stem from the same root cause: with the new "filesystem checks first" ordering, `setup_doctor_runtime` may now raise `PipelexConfigError` AFTER several `check_*` functions have already populated partial results. The downstream error reporting path was not updated to handle this.

#### A1 — `log.verbose` in `report_validation_error` raises RuntimeError before bootstrap

**Finding.** `pipelex/core/validation.py` calls `log.verbose(...)` at line 22 and ~line 35. Both calls go through `LogDispatch.dispatch` which dereferences `self._log_config` — that property raises `RuntimeError("LogConfig is not set...")` when `log.configure` hasn't run yet. With the new ordering, `check_config_files` catches `ValidationError` BEFORE `setup_doctor_runtime` runs, calls `report_validation_error`, hits `log.verbose`, blows up. The outer `except Exception` in `agent_doctor_cmd` (or the `except Exception` wrapping `do_doctor_cmd`) converts it to "Health check failed unexpectedly: LogConfig is not set" / "Unexpected error: LogConfig is not set" — losing the friendly migration-aware report that the refactor was specifically built to expose.

**Verify.**

1. Read `pipelex/tools/log/log_dispatch.py` and confirm `LogDispatch._log_config` raises RuntimeError when `_log_config_instance is None`.
2. Reproduce manually: edit `~/.pipelex/pipelex.toml` to add a bogus field (e.g. `nonsense_field = "boom"` at the top level); run `.venv/bin/pipelex-agent doctor --format json 2>&1 | head -20`. Observe "Health check failed unexpectedly: LogConfig is not set" instead of a structured validation error.

**Fix.** Guard the two `log.verbose` calls in `validation.py` with `log.is_configured()` (the helper added in Group 9 of the prior plan exists for exactly this):

```python
if log.is_configured():
    log.verbose(validation_error_analysis.missing_fields, title="Missing fields")
# ... same for the second one
```

Or simpler: just drop both `log.verbose` calls. They emit internal analysis data that the user-facing report already conveys.

Pick the drop. Verbose logs are not load-bearing here.

**Test.** Add a unit test under `tests/unit/pipelex/core/test_validation.py` that calls `report_validation_error` with no hub/log configured and asserts it returns a non-empty string (no RuntimeError).

---

#### A2 — `do_doctor_cmd` has no `try/except` around `setup_doctor_runtime`

**Finding.** Human `do_doctor_cmd` at `pipelex/cli/commands/doctor_cmd.py:856-896` invokes `setup_doctor_runtime()` directly. If it raises `PipelexConfigError` (its documented expected failure mode), Python prints an uncaught traceback. Before the reorder, `setup_doctor_runtime` ran first so the crash happened cleanly; after the reorder, the file checks have already populated partial tuples and the user sees a half-assembled report + a traceback.

The outer `doctor_cmd` (calling `do_doctor_cmd`) DOES have an `except Exception` arm, but the message ("Unexpected error: ...") doesn't distinguish translated config errors from anything else.

**Verify.** Same repro as A1, but `.venv/bin/pipelex doctor` (no `pipelex-agent`). Observe the traceback shape: either an uncaught traceback (if `doctor_cmd`'s wrapper doesn't catch PipelexConfigError) or the generic "Unexpected error" prefix masking a documented translation.

**Fix.** In `do_doctor_cmd`, short-circuit on broken config: if `config_healthy` is False, skip `setup_doctor_runtime` and `check_models`, render the partial report with models marked `(not run — fix config first)`. Concretely:

```python
config_healthy, config_missing_count, config_message = check_config_files()
telemetry_healthy, telemetry_message = check_telemetry_config()
backends_healthy, backend_credential_reports, backends_message = check_backend_credentials()

if config_healthy:
    setup_doctor_runtime()
    models_healthy, models_message, backend_file_reports = check_models()
    deck_healthy, deck_report, deck_message = check_deck_sync()
else:
    models_healthy = False
    models_message = "skipped — fix config errors first"
    backend_file_reports = {}
    deck_healthy = False
    deck_report = ...  # empty stub
    deck_message = "skipped — fix config errors first"
```

Apply the same pattern to `agent_doctor_cmd` (resolves A4 below).

---

#### A3 — `PipelexConfigError` mis-labelled as "Health check failed unexpectedly"

**Finding.** Even when `setup_doctor_runtime` raises `PipelexConfigError` legitimately (a config that passes `check_config_files`'s shape check but fails some other validation), the bare `except Exception` in `agent_doctor_cmd:153-155` wraps it with `"Health check failed unexpectedly: ..."`. PipelexConfigError carries a translated/friendly message; the prefix mislabels a documented failure as unexpected.

**Verify.** Look at `agent_doctor_cmd`'s except block. Confirm there's no `except PipelexConfigError` arm above the generic one.

**Fix.** Add a specific arm:

```python
except PipelexConfigError as exc:
    agent_error(exc.message, "PipelexConfigError", cause=exc)
except Exception as exc:  # noqa: BLE001
    agent_error(f"Health check failed unexpectedly: {exc}", type(exc).__name__, cause=exc)
```

`PipelexConfigError` is imported via `from pipelex.base_exceptions import PipelexConfigError`. If A2's short-circuit is applied, this arm may become dead — keep it anyway as defense-in-depth for the partial-config case (valid shape, broken contents).

---

#### A4 — Cascading failure discards partial check results

**Finding.** When `check_config_files` returns unhealthy and `setup_doctor_runtime` later raises, the bare `except Exception` discards all the structured tuples gathered so far (`config_message`, `telemetry_message`, `backend_credential_reports`, etc.). The user wanted triage; gets one line.

**Verify.** Same repro as A1. Confirm the JSON envelope on stderr contains only an `error` payload, not the per-check breakdown.

**Fix.** A2's short-circuit pattern resolves this on the agent side too: when `config_healthy` is False, skip `setup_doctor_runtime` AND `check_models`, mark models as `"healthy": false, "message": "skipped — fix config errors first"`, render the partial report. The user sees the full triage report with one section explicitly marked "not run."

**Test update.** Add a regression test under `tests/unit/pipelex/cli/test_agent_doctor_cmd.py` that mocks `check_config_files` to return `(False, 1, "validation failed")` and asserts:

- `setup_doctor_runtime` is NOT called
- The output JSON includes a `models` section with `healthy=False` and a "skipped" message
- The output JSON still includes `recommended_actions` from the config error

---

### Group B — Finish threading `config_dir` through the doctor  **[medium]**

The prior plan's Group 2 threaded `config_dir` through `setup_doctor_runtime` → `setup_config` → `load_config`. But two call sites inside `check_config_files` and `check_models` still bypass it.

#### B1 — `check_config_files` validates via layered `load_config()` even under `--global`

**Finding.** `pipelex/cli/commands/doctor_cmd.py:135` calls `config_manager.load_config()` with no `config_dir`. The inline comment on 126-128 admits this divergence is "acceptable for a diagnostic check" — but `load_config` now accepts `config_dir` and threading it through makes the diagnostic honor what `--global` requested.

Secondary problem: that same `load_config()` call (no config_dir) takes the ELSE branch which DOES call `ensure_global_config_exists()`. So `check_config_files` still silently materializes `~/.pipelex/` on a fresh machine — partially undoing the silent-installer fix.

**Verify.** Manually: wipe `~/.pipelex/`, create a project `.pipelex/pipelex.toml` only, run `.venv/bin/pipelex doctor`. Check whether `~/.pipelex/` exists after the run. Confirm it does (bug present).

**Fix.** Thread `config_dir` into the validation step:

```python
# In check_config_files, line 135 area
config = config_manager.load_config(config_dir=config_dir)
```

This bypasses layering AND skips `ensure_global_config_exists` when `--global` is set. For the no-`--global` case (config_dir=None), behavior is unchanged.

Update the inline comment on lines 126-128 to reflect the change.

---

#### B2 — `check_models` calls `is_pipelex_gateway_enabled()` and `load_pipelex_service_config_if_exists` without config_dir

**Finding.** `pipelex/cli/commands/doctor_cmd.py:797-798`:

```python
if is_pipelex_gateway_enabled():  # uses config_manager.backends_file_path (layered)
    pipelex_service_config = load_pipelex_service_config_if_exists(
        config_dir=config_manager.global_config_dir  # always global, ignores --global flag intent
    )
```

So `--global` is honored at the hub level (good) but bypassed by these probes. In a project with a project-local backends.toml disabling gateway, `--global` reports gateway-disabled even though global config enables it. The prior plan's Group 2 acknowledged this as "audit before claiming the fix complete."

**Verify.** Read `pipelex/system/pipelex_service/pipelex_service_config.py:45-71` — confirm `is_pipelex_gateway_enabled()` accepts an optional `backends_file_path` argument. If not, this is a bigger change.

**Fix.**

1. Add a `config_dir: Path | None = None` parameter to `is_pipelex_gateway_enabled()`. When set, derive `backends_file_path` from `config_dir / "inference" / "backends.toml"` instead of `config_manager.backends_file_path`.
2. In `check_models`, replace lines 797-798:

```python
if is_pipelex_gateway_enabled(config_dir=config_dir):
    pipelex_service_config = load_pipelex_service_config_if_exists(
        config_dir=config_dir or config_manager.global_config_dir
    )
```

3. Search for other callers of `is_pipelex_gateway_enabled` (grep) and confirm none break with the new optional param.

---

### Group C — Embed-safe log channel pinning  **[medium, future-risk]**

When `log.configure_if_unset` no-ops (something already called `log.configure`), the doctor's STDERR override on `console_log_target` is silently dropped. There's no current production trigger (each `pipelex-agent` subprocess is fresh), but the wire is hot for embedders.

#### C1 — `configure_if_unset` returning False silently leaves rich_handler on stdout

**Finding.** `setup_doctor_runtime` at line 766 calls `log.configure_if_unset(log_config=log_config)` but does not check the return value. If it returns False (already configured), the rich_handler keeps the prior `console_log_target` (potentially stdout) while the hub's print target is freshly set to STDERR (line 765). Channels diverge.

**Verify.** Write a one-off Python script:

```python
from pipelex.tools.log.log import log
from pipelex.tools.log.log_config import LogConfig
# Configure log somehow (mock or real)
# Then call setup_doctor_runtime with stderr overrides
# Inspect log.rich_handler.console — does it point at stderr?
```

If `log.rich_handler.console.file` is sys.stdout after the call, the bug is confirmed.

**Fix.** Two options:

(a) Have `setup_doctor_runtime` inspect the return and call `log.redirect_to_stderr()` when overrides demand stderr but `configure_if_unset` no-oped. The cleanest signal: when `log_config_overrides is not None` AND `log.configure_if_unset(...)` returned False, call `log.redirect_to_stderr()`. This re-applies the override surgically without re-configuring.

(b) Extend `configure_if_unset` to apply a subset of "safe to re-apply" fields even when already configured — specifically `console_log_target` (via rich_handler.console swap) and `package_log_levels`. More invasive.

Pick (a). It's a one-line guard.

```python
applied = log.configure_if_unset(log_config=log_config)
if not applied and log_config_overrides is not None:
    # configure_if_unset is a no-op when log was already configured; surgically swap the
    # rich_handler's console so the override on console_log_target still takes effect.
    if log_config.console_log_target == ConsoleTarget.STDERR:
        log.redirect_to_stderr()
```

This requires importing `ConsoleTarget` into `doctor_cmd.py`.

---

#### C2 — `agent_doctor_cmd` never calls `log.redirect_to_stderr()`

**Finding.** The factory path (`make_pipelex_for_agent_cli`) does `log.redirect_to_stderr()` immediately before `apply_agent_cli_output_discipline()` (agent_cli_factory.py:214). The doctor path only calls the discipline helper. So even apart from C1's `configure_if_unset` quirk, the doctor lacks the factory's defense-in-depth for stderr redirection.

**Verify.** Read both call sites. Confirm asymmetry.

**Fix.** Fold the redirect into `apply_agent_cli_output_discipline` so both entry points are symmetric:

```python
def apply_agent_cli_output_discipline(log_level: LogLevel = LogLevel.WARNING) -> None:
    log.set_level_for_package("pipelex", log_level)
    log.redirect_to_stderr()  # NEW — was only on the factory path
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    get_pipelex_hub().set_console_print_target(target=ConsoleTarget.STDERR)
```

Then remove the now-duplicated `log.redirect_to_stderr()` line in `make_pipelex_for_agent_cli`.

**Caveat.** `log.redirect_to_stderr()` raises if `rich_handler is None`. In the doctor path with `configure_if_unset` no-op, `rich_handler` exists (set by the prior `configure`). With a fresh `configure`, it also exists. The only failure mode is "log was never configured at all" — which can't happen here because `setup_doctor_runtime` always calls `configure_if_unset` before the discipline helper runs. Safe.

Cross-check: `redirect_to_stderr` raises if `self.rich_handler is None` — verify the new flow ensures it's set before `apply_agent_cli_output_discipline` is called.

---

#### C3 — `apply_agent_cli_output_discipline` demotes pipelex log level unconditionally

**Finding.** `agent_cli_factory.py:97` runs `log.set_level_for_package("pipelex", log_level)` even when `configure_if_unset` no-oped (meaning an embedder deliberately set the level higher). This contradicts the "respect prior config" policy implied by `configure_if_unset`.

**Verify.** Trace: embedder sets `logging.getLogger("pipelex").setLevel(logging.DEBUG)`. Run agent_doctor_cmd. Confirm pipelex logger ends up at WARNING (set by discipline call).

**Fix.** Pass the "did we configure log" signal down. In `setup_doctor_runtime`:

```python
applied = log.configure_if_unset(log_config=log_config)
return applied  # NEW return value
```

In `agent_doctor_cmd`:

```python
log_was_configured_by_us = setup_doctor_runtime(log_config_overrides=..., config_dir=...)
apply_agent_cli_output_discipline(
    log_level=LogLevel.WARNING if log_was_configured_by_us else None,
)
```

And in `apply_agent_cli_output_discipline`:

```python
def apply_agent_cli_output_discipline(log_level: LogLevel | None = LogLevel.WARNING) -> None:
    if log_level is not None:
        log.set_level_for_package("pipelex", log_level)
    log.redirect_to_stderr()
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    get_pipelex_hub().set_console_print_target(target=ConsoleTarget.STDERR)
```

The factory still passes its `log_level` parameter (always non-None in that flow).

Lower-priority: if `setup_doctor_runtime`'s return type complicates other callers, alternative is to add a separate `log.was_configured_by_us` boolean on the Log class. Pick the return value — less coupling.

---

### Group D — Hardening / cleanup  **[low, future-risk]**

#### D1 — Broad `except RuntimeError` in `validation.py`

**Finding.** The new guard catches ALL RuntimeError — including "PipelexHub is not initialized" (hub.py:101) and any future RuntimeError from `get_config()` or `.migration` access. Could mask real bugs across all callers of `report_validation_error`.

**Verify.** Read `pipelex/hub.py:93-95` — confirm `get_optional_instance()` exists.

**Fix.** Replace try/except with a non-raising helper. Two options:

(a) Add `get_optional_config()` to `PipelexHub`:

```python
def get_optional_config(self) -> ConfigRoot | None:
    return self._config
```

Then in `validation.py`:

```python
pipelex_hub = PipelexHub.get_optional_instance()
config = pipelex_hub.get_optional_config() if pipelex_hub is not None else None
migration_config = config.migration if config is not None else None
```

(b) Cheaper: tighten the catch to the specific error type. `RuntimeError` isn't subclassed here, so the cheapest fix is the helper approach.

Pick (a). Aligns with project rule "Don't add try/except speculatively."

---

#### D2 — Stale comments about materialization side-effect

**Finding.** The comments at `pipelex/cli/agent_cli/commands/doctor_cmd.py:137-140` and `pipelex/cli/commands/doctor_cmd.py:884-887` justify the new ordering by claiming `setup_doctor_runtime` materializes `~/.pipelex/` as a side effect — true for the no-`--global` path but FALSE for `--global` (which skips `ensure_global_config_exists`).

**Verify.** Re-read both comments.

**Fix.** Update both comments to acknowledge that materialization only happens on the layered (`config_dir=None`) path. Suggest the right install command in the diagnostic message when `--global` reports missing files on a fresh machine.

---

#### D3 — `dict(AGENT_CLI_STDERR_LOG_FIELDS)` is a shallow copy; "alias" claim is broken

**Finding.** `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES["pipelex"]["log_config"] = dict(AGENT_CLI_STDERR_LOG_FIELDS)` at agent_cli_factory.py:75 creates a separate mutable dict. The MappingProxyType freeze on AGENT_CLI_STDERR_LOG_FIELDS gives false security — a future contributor mutating the inner dict succeeds and diverges from the canonical frozen Mapping.

**Verify.** In a Python REPL:

```python
from pipelex.cli.agent_cli.commands.agent_cli_factory import (
    AGENT_CLI_STDERR_LOG_FIELDS,
    _AGENT_CLI_STDERR_CONSOLE_OVERRIDES,
)
# This succeeds — divergence!
_AGENT_CLI_STDERR_CONSOLE_OVERRIDES["pipelex"]["log_config"]["console_log_target"] = "stdout"
print(AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"])  # still STDERR
print(_AGENT_CLI_STDERR_CONSOLE_OVERRIDES["pipelex"]["log_config"]["console_log_target"])  # "stdout"
```

**Fix.** Two options:

(a) Freeze the inner dict too: `MappingProxyType(dict(AGENT_CLI_STDERR_LOG_FIELDS))`. But then deep_update can't recurse into it (it checks `isinstance(value, dict)`). Need to also extend `deep_update` to handle `Mapping`.

(b) Extend `deep_update` to recurse into any `Mapping`, then `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES["pipelex"]["log_config"]` can be the frozen AGENT_CLI_STDERR_LOG_FIELDS directly.

Pick (b). One signature change in `pipelex/tools/misc/json_utils.py:235`:

```python
def deep_update(target_dict: dict[str, Any], updates: Mapping[str, Any]):
    for key, value in updates.items():
        if isinstance(value, Mapping) and key in target_dict and isinstance(target_dict[key], dict):
            deep_update(target_dict[key], value)
        else:
            target_dict[key] = (
                dict(value) if isinstance(value, Mapping) and not isinstance(value, dict) else value
            )
```

The `dict(value)` conversion on leaf-assignment prevents the merged target_dict from holding a MappingProxyType (which would surprise downstream code that expects a plain dict).

Then in agent_cli_factory.py:

```python
_AGENT_CLI_STDERR_CONSOLE_OVERRIDES: dict[str, Any] = {
    "pipelex": {"log_config": AGENT_CLI_STDERR_LOG_FIELDS},  # back to direct alias
}
```

**Verify after fix.** Add a unit test under `tests/unit/pipelex/tools/misc/test_json_utils.py` that calls `deep_update` with a MappingProxyType leaf and confirms the resulting dict has a plain `dict` at that key, not the proxy.

---

#### D4 — `LogConfig.model_validate({**dump, **overrides})` round-trip is brittle

**Finding.** The round-trip re-runs `validate_package_log_levels` on already-LogLevel enum values, relying on `LogLevel(LogLevel.WARNING)` working via StrEnum self-idempotency. A future change to LogLevel could silently break doctor at this single call site.

**Verify.** Read `pipelex/tools/log/log_config.py:126-132` (the field validator). Confirm `transform_dict_str_to_enum` declared signature.

**Fix.** Switch to a typed overrides shape. Define in `agent_cli_factory.py` (or a shared location):

```python
class LogConfigOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    console_log_target: ConsoleTarget | None = None
    console_print_target: ConsoleTarget | None = None
```

Then `AGENT_CLI_STDERR_LOG_FIELDS` becomes `AGENT_CLI_STDERR_LOG_OVERRIDES = LogConfigOverrides(console_log_target=ConsoleTarget.STDERR, console_print_target=ConsoleTarget.STDERR)`. `setup_doctor_runtime` takes `log_config_overrides: LogConfigOverrides | None`. Merge becomes `log_config.model_copy(update=overrides.model_dump(exclude_none=True))` — back to the old non-revalidating model_copy.

Larger surface. Alternative: keep model_validate but use `model_dump(mode="json")` for round-trip safety. Simpler but doesn't fix the validator-re-run concern.

Pick the typed overrides shape. The migration is small and adds real type safety.

**Caveat.** Test `test_bootstrap_pins_console_targets_to_stderr` currently does `AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"]` — would need to become `AGENT_CLI_STDERR_LOG_OVERRIDES.console_log_target`. Acceptable.

---

#### D5 — `log.is_configured()` is dead code

**Finding.** The new public method is declared at `pipelex/tools/log/log.py:73-75` but no caller. If A1 is fixed by guarding `log.verbose` with `log.is_configured()`, this becomes load-bearing. If A1 is fixed by dropping the `log.verbose` calls, `is_configured` should be deleted.

**Verify.** `grep -r "is_configured" pipelex/ tests/`.

**Fix.** Depends on A1's choice. If A1 drops the log.verbose calls, also delete `is_configured` here. If A1 guards them, keep it AND add the test (D6 below).

---

#### D6 — No unit tests for `configure_if_unset` / `is_configured`

**Finding.** The new helpers are load-bearing for the doctor path but have no pinning tests. A future refactor could silently invert the guard.

**Verify.** `ls tests/unit/pipelex/tools/log/` — confirm no test covers these methods.

**Fix.** Add `tests/unit/pipelex/tools/log/test_log_idempotence.py` (one test class) covering:

- `configure_if_unset` returns True on a fresh `Log()` instance AND applies the config.
- `configure_if_unset` returns False after a prior `configure` AND does NOT raise.
- `is_configured` returns False before configure, True after.
- After `log.reset()`, `configure_if_unset` returns True again.

Use a fresh `Log()` (not the module-global singleton) to avoid state leak across tests.

---

## Suggested fix order

Land in this order, one commit per group:

1. **Group A** (friendly error path regression) — highest user impact. The A1/A2/A4 fixes together restore the friendly translation that the refactor was meant to expose. Single commit.
2. **Group B** (finish config_dir threading) — finishes the prior plan's Group 2. Single commit.
3. **Group C** (embed-safe log channel pinning) — important for any future embedding context, plus the asymmetry with the factory is a code smell to clean up. Single commit folding C1+C2+C3.
4. **Group D** — defensive cleanup. Each subgroup can be its own commit or bundled. D5+D6 ride alongside D1's decision.

Recommended commit messages (in order):

- `fix(doctor): preserve friendly validation translation across new check ordering`
- `fix(doctor): thread config_dir through check_config_files and gateway probe`
- `fix(agent-cli): make stderr pinning embed-safe for prior log configurations`
- `refactor(doctor): tighten error guards and freeze override leaves`

## Verification

For each group:

```bash
make agent-check
.venv/bin/pytest -n auto \
  -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
  -o log_level=WARNING --tb=short -q \
  tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ \
  tests/unit/pipelex/system/ tests/unit/pipelex/tools/ \
  tests/unit/pipelex/core/
make tb  # boot test — exercises agent-doctor end-to-end
```

Manual repros to run by hand after the full set lands:

- **A1/A2/A3/A4** — Edit `~/.pipelex/pipelex.toml` to add a clearly invalid field (e.g. `level_pipelex = 42`). Run both `pipelex doctor` and `pipelex-agent doctor --format json`. Confirm:
  - Human doctor shows the structured per-check report with the config check marked failed and the models check marked "skipped — fix config errors first."
  - Agent doctor produces a structured JSON envelope (NOT an "unexpected error") with the same shape.
  - The validation error message includes the migration hint when applicable.

- **B1** — Wipe `~/.pipelex/`, create only a project `.pipelex/pipelex.toml`, run `pipelex doctor`. Confirm `~/.pipelex/` is NOT created as a side effect.

- **B2** — In a project with backends.toml disabling gateway and a global with backends.toml enabling it, run `pipelex-agent doctor --global`. Confirm the gateway-enabled state is reported (not project-layered).

- **C1/C2** — Python script:
  ```python
  from pipelex import Pipelex
  Pipelex.make()  # configures log with user's targets
  from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
  agent_doctor_cmd(output_format=CliOutputFormat.JSON)
  # Inspect: are log lines on stderr? Did the doctor's JSON envelope on stdout stay clean?
  ```

- **D3** — REPL test above (try mutating `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES`; after the fix, AGENT_CLI_STDERR_LOG_FIELDS should still be frozen AND the deep_update should still recurse).

## Out of scope for this plan

- The pre-existing `set_pipelex_hub(PipelexHub())` BEFORE `setup_config` succeeds — leaves an empty hub if validation raises. Pre-existing risk, not introduced by this refactor or the prior plan.
- Threading `--log-level` through `pipelex-agent doctor` (currently hardcoded to WARNING via the discipline helper). The CLI surface for the agent doctor doesn't expose it; out of scope until a user asks for it.
- CHANGELOG entries for the doctor bootstrap refactor — should be addressed when the branch lands, not as part of this fix plan.

## Pointers for the next session

- Branch is still `fix/Log-target`. 9 files are STAGED on top of the 6e44d2f2 commit at the time of writing. Decide whether to:
  - (a) Commit the staged work as one commit, then land each group below as a separate commit.
  - (b) Bundle these fixes into the same staged set and produce one big commit.
  - Recommended: (a) — cleaner history; each group has a clear motivation.
- The `/code-review` skill found these — re-running it after each group is a reasonable validation step.
- Memory: feedback memories about avoiding mocking, integration test discipline, and security-perimeter testing apply. No new memories needed unless something surprising surfaces during implementation.
