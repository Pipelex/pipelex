# Doctor bootstrap refactor — follow-up fixes

Cold-start brief for a session that lands the code-review findings on top of the doctor bootstrap refactor (branch `fix/Log-target`, staged but not yet committed at the time this plan was written).

## What this plan is for

A recent refactor (see "Background context" below) extracted a `setup_doctor_runtime` helper from `check_models` so that both the human `pipelex doctor` and the agent `pipelex-agent doctor` go through the same hub + log bootstrap, with stderr-pinning overrides for the agent path. A high-effort code review against that staged diff surfaced 13 findings. None block the original fix from landing, but several are real regressions of doctor's diagnostic UX and a couple of pre-existing bugs were surfaced and should be addressed.

This document is the playbook for landing those fixes.

## Background context (read this first if you're cold-starting)

### The bug that started everything

`pipelex-agent doctor --format json` used to be the only `pipelex-agent` subcommand that did NOT go through `make_pipelex_for_agent_cli` (the factory in `pipelex/cli/agent_cli/commands/agent_cli_factory.py`). The factory pins `console_log_target` and `console_print_target` to stderr via `Pipelex.make(config_overrides=...)` so the JSON envelope on stdout stays parseable for downstream consumers like `mthds-js`'s `PipelexRunner` doing `JSON.parse(stdout)`. Doctor instead imported `check_*` helpers from `pipelex/cli/commands/doctor_cmd.py` directly, and `check_models` internally called `log.configure(log_config=get_config().pipelex.log_config)` — honoring the user's raw `console_log_target` literally. A user with `console_log_target = "stdout"` and a raised pipelex log level would see verbose log lines land on stdout BEFORE the JSON envelope, breaking `json.loads(stdout)`.

### The refactor that fixed it (the diff this plan builds on)

Five files changed:

- `pipelex/cli/agent_cli/commands/agent_cli_factory.py`
  - New exported `AGENT_CLI_STDERR_LOG_FIELDS: dict[str, Any] = {"console_log_target": STDERR, "console_print_target": STDERR}` — canonical leaf dict for "for any agent-CLI invocation, both Rich-managed channels go to stderr."
  - `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES` now composes that constant (the `Pipelex.make(config_overrides=...)` shape: `{"pipelex": {"log_config": AGENT_CLI_STDERR_LOG_FIELDS}}`).
  - New `apply_agent_cli_output_discipline()` helper packages the post-init defense-in-depth tail (`PrettyPrinter.mode = SILENT` + `get_pipelex_hub().set_console_print_target(STDERR)`).
  - `make_pipelex_for_agent_cli` calls `apply_agent_cli_output_discipline()` instead of inlining the two lines.
- `pipelex/cli/commands/doctor_cmd.py`
  - New `setup_doctor_runtime(log_config_overrides: dict[str, Any] | None = None) -> None` helper — owns the `PipelexHub()` + `set_pipelex_hub` + `setup_config(config_cls=PipelexConfig)` + `log.configure(log_config=...)` sequence.
  - Applies `model_copy(update=log_config_overrides)` to the loaded `log_config` if overrides are given.
  - `check_models` no longer does the hub/log setup itself (assumes the helper ran).
  - `do_doctor_cmd` calls `setup_doctor_runtime()` (no overrides) before the `check_*` calls.
- `pipelex/cli/agent_cli/commands/doctor_cmd.py`
  - `agent_doctor_cmd` calls `setup_doctor_runtime(log_config_overrides=AGENT_CLI_STDERR_LOG_FIELDS)` then `apply_agent_cli_output_discipline()` at the top of the existing `try:` block.
- `tests/unit/pipelex/cli/test_agent_doctor_cmd.py`
  - New autouse fixture `_mock_doctor_bootstrap` mocks both helpers so existing tests don't load real config or call `log.configure` (once-per-process).
  - New regression test `test_bootstrap_pins_console_targets_to_stderr` asserts `setup_doctor_runtime` is called with `AGENT_CLI_STDERR_LOG_FIELDS`.
- `tests/unit/pipelex/cli/test_doctor_cmd.py`
  - Existing test stubs `setup_doctor_runtime` so the human-doctor unit test doesn't run the real bootstrap.

The original plan for the refactor itself lives at `/Users/lchoquel/.claude/plans/option-1-seems-memoized-crystal.md` — useful background reading if you need to understand why the shape is what it is. The longer-form context doc for the underlying console-targets work is `wip/console-targets-and-agent-cli-stdout.md`.

### Reference files and key paths

| Concern | File | Key lines |
|---|---|---|
| Agent CLI output policy | `pipelex/cli/agent_cli/commands/agent_cli_factory.py` | `AGENT_CLI_STDERR_LOG_FIELDS` (57), `apply_agent_cli_output_discipline` (67-76), `make_pipelex_for_agent_cli` (post-init at 188-192) |
| Bootstrap helper | `pipelex/cli/commands/doctor_cmd.py` | `setup_doctor_runtime` (716-749) |
| Human doctor entry | `pipelex/cli/commands/doctor_cmd.py` | `doctor_cmd` (806), `do_doctor_cmd` (830-873) |
| Agent doctor entry | `pipelex/cli/agent_cli/commands/doctor_cmd.py` | `agent_doctor_cmd` (90-232), bootstrap call at 127-128, except boundary at 148 |
| `check_models` (now pure) | `pipelex/cli/commands/doctor_cmd.py` | 752-803 |
| Full Pipelex init (the analogue) | `pipelex/pipelex.py` | `__init__` 111-119 — `setup_config` → `log_config = get_config().pipelex.log_config` → `set_console_print_target` → `log.configure` |
| Hub `setup_config` | `pipelex/hub.py` | 114-124 — calls `model_validate` BEFORE `set_config` |
| `log.configure` once-per-process | `pipelex/tools/log/log.py` | 73-110 — raises `RuntimeError` on second call |
| `ConfigLoader.load_config` | `pipelex/system/configuration/config_loader.py` | 195-249 — calls `ensure_global_config_exists` unconditionally |
| `ensure_global_config_exists` | `pipelex/system/configuration/config_loader.py` | 139-168 — materializes `~/.pipelex/` if absent |
| `report_validation_error` | `pipelex/core/validation.py` | 11 — calls `get_config().migration` |

## Findings to fix

Findings are grouped by fix so that a single change addresses related items. Each group lists every finding it resolves. Severity reflects the most severe item in the group.

### Group 1 — Reorder bootstrap so it runs AFTER filesystem-only checks  **[medium]**

**Resolves:** Group A — silent installer (`~/.pipelex/` materialized before `check_config_files`).

**Problem.** `do_doctor_cmd` and `agent_doctor_cmd` both call `setup_doctor_runtime()` before any `check_*`. `setup_doctor_runtime` → `pipelex_hub.setup_config` → `config_manager.load_config` → `ensure_global_config_exists` (config_loader.py:139-168) silently creates `~/.pipelex/` from kit templates on a fresh machine. Then `check_config_files` reports "all configs present" instead of "missing — run `pipelex init config`." The diagnostic became a side-effecting installer.

**Fix.** Only `check_models` needs the hub + configured log. The other four checks (`check_config_files`, `check_telemetry_config`, `check_backend_credentials`, `check_deck_sync` for the human path) read from disk independently. Move the bootstrap call so it runs just before `check_models`.

In `pipelex/cli/commands/doctor_cmd.py:do_doctor_cmd` (around line 869), the call sequence becomes:

```python
config_location = gather_config_location()

config_healthy, config_missing_count, config_message = check_config_files()
telemetry_healthy, telemetry_message = check_telemetry_config()
backends_healthy, backend_credential_reports, backends_message = check_backend_credentials()

# Bootstrap the runtime check_models depends on. Done AFTER the filesystem-only
# checks so a fresh machine still gets the "missing config — run init" diagnostic
# (setup_config materializes ~/.pipelex/ as a side effect of load_config).
setup_doctor_runtime()

models_healthy, models_message, backend_file_reports = check_models()
deck_healthy, deck_report, deck_message = check_deck_sync()
```

In `pipelex/cli/agent_cli/commands/doctor_cmd.py:agent_doctor_cmd`, the same shape — keep `apply_agent_cli_output_discipline()` early (it's the stdout-pin), but defer `setup_doctor_runtime` until just before `check_models`:

```python
# Pin output discipline immediately so any check_* logging stays on stderr.
apply_agent_cli_output_discipline()

# Compute config_dir from --global as before...
config_dir = config_manager.global_config_dir if global_ else None
# ... gather config_location ...

config_healthy, config_missing_count, config_message = check_config_files(config_dir=config_dir)
telemetry_healthy, telemetry_message = check_telemetry_config(config_dir=config_dir)
backends_healthy, backend_credential_reports, backends_message = check_backend_credentials(config_dir=config_dir)

# Bootstrap just before check_models (the only check that needs the hub).
setup_doctor_runtime(log_config_overrides=AGENT_CLI_STDERR_LOG_FIELDS)
models_healthy, models_message, backend_file_reports = check_models(config_dir=config_dir)
```

**Watch out for:** `apply_agent_cli_output_discipline()` calls `get_pipelex_hub()` which raises if no hub is set. Without the early `setup_doctor_runtime()`, the very first call to `get_pipelex_hub()` will fail. Two options:
- (a) Move `apply_agent_cli_output_discipline()` to AFTER `setup_doctor_runtime()` (keeps stdout protected from the moment a hub exists; the early `check_*` calls don't emit through the hub).
- (b) Keep `apply_agent_cli_output_discipline()` early but lazy-init a minimal hub for output discipline (no setup_config). Adds complexity — not recommended.

Pick (a). The early `check_*` functions read from disk and don't emit through Rich, so stdout stays clean even without the discipline applied yet.

**Test update.** The new test `test_bootstrap_pins_console_targets_to_stderr` (test_agent_doctor_cmd.py:146-184) asserts `setup_doctor_runtime` is called — that still holds with the new ordering, but verify the test's mocked check_* return shapes still cover the path that reaches `setup_doctor_runtime`.

---

### Group 2 — Thread `config_dir` through `setup_doctor_runtime` for `--global`  **[medium]**

**Resolves:** Group B — `--global` honored by `check_*` but not by hub load.

**Problem.** `agent_doctor_cmd --global` sets `config_dir = config_manager.global_config_dir` and passes it to each `check_*`. But `setup_doctor_runtime` calls `pipelex_hub.setup_config(config_cls=PipelexConfig)` with no `config_dir` — `PipelexHub.setup_config` (hub.py:114-124) has no such parameter — and `config_manager.load_config` (config_loader.py:195-249) always merges global + project layers. Then `check_models` calls `is_pipelex_gateway_enabled()` and `ModelManager.setup()` which both read from `config_manager.backends_file_path` / `get_config()` — all layered. So `--global` produces inconsistent results: file checks point at global; gateway probe and model-deck validation read the project-layered hub.

**Fix.** Add a `config_dir: Path | None = None` parameter to `setup_doctor_runtime`. When provided, the hub load must scope to that dir alone (no layering).

This requires a small change in two places:

1. `pipelex/system/configuration/config_loader.py:load_config` — accept a `config_dir: Path | None = None` override that, when given, replaces the default project+global layering with a single-dir load.
2. `pipelex/hub.py:PipelexHub.setup_config` — accept and pass through `config_dir`.
3. `pipelex/cli/commands/doctor_cmd.py:setup_doctor_runtime` — accept `config_dir`, pass it to `setup_config`.
4. `pipelex/cli/agent_cli/commands/doctor_cmd.py:agent_doctor_cmd` — pass `config_dir` when `--global` is set.

**Alternative shape if the load_config signature change is too invasive.** Add a narrower `force_single_dir: Path | None = None` parameter on `setup_doctor_runtime` that short-circuits to a manual `PipelexConfig.model_validate(load_toml_from_path(force_single_dir / "pipelex.toml"))` and `set_config(...)` path, bypassing `load_config` entirely. Uglier but localized.

Prefer the first approach. The `config_dir` override is also independently useful for other diagnostic flows.

**Note.** Also re-examine the layered behavior of `is_pipelex_gateway_enabled()` and `ModelManager.setup()` when called from `check_models` with `config_dir=global`. Even with `setup_doctor_runtime(config_dir=...)`, `check_models` may still hit `config_manager.backends_file_path` (a property that always layers). If yes, those internal calls inside `check_models` also need a `config_dir` override path. Audit before claiming the fix complete.

---

### Group 3 — Fix `report_validation_error` masking the original ValidationError  **[low, pre-existing]**

**Resolves:** Group C — opaque `RuntimeError("Config instance is not set")` instead of the friendly `PipelexConfigError`.

**Problem.** Inside `setup_doctor_runtime`'s ValidationError handler:

```python
except ValidationError as validation_error:
    validation_error_msg = report_validation_error(category="config", validation_error=validation_error)
    msg = f"Could not setup config because of: {validation_error_msg}"
    raise PipelexConfigError(msg) from validation_error
```

`report_validation_error` (`pipelex/core/validation.py:11`) calls `get_config().migration` to look up migration hints. But `PipelexHub.setup_config` (hub.py:124) calls `model_validate` BEFORE `set_config`, so on `ValidationError` the hub's `_config` stays `None`. `get_config().migration` then raises `RuntimeError('Config instance is not set...')` — the friendly `PipelexConfigError` translation never runs. User sees the opaque RuntimeError.

This is **pre-existing** — same masking lived inside `check_models` before the refactor. The refactor relocates the call site but doesn't fix the underlying bug.

**Fix.** `report_validation_error` shouldn't depend on `get_config()` for migration hints during config-validation diagnosis. Two options:

- (a) Make `report_validation_error` resilient to "no config yet": catch the RuntimeError when accessing `get_config().migration` and fall back to a no-migration-hint output. This is the minimal fix.
- (b) Refactor `report_validation_error` to accept migration hints as a parameter, and have the caller decide how to source them. Cleaner separation, larger surface.

Pick (a). Add a guarded read inside `report_validation_error`:

```python
try:
    migration = get_config().migration
except RuntimeError:
    migration = None
# ... use migration if not None ...
```

**Verify** that `migration` is the only `get_config()` access in `report_validation_error`. If there are others, guard them all.

---

### Group 4 — Add `set_console_print_target` to `setup_doctor_runtime`  **[low, pre-existing]**

**Resolves:** Group D — human doctor's `console_print_target` ignored; resolves Group G — `apply_agent_cli_output_discipline` "redundant" docstring becoming load-bearing on the doctor path.

**Problem.** `Pipelex.__init__` (pipelex.py:117-119) does:

```python
log_config = get_config().pipelex.log_config
self.pipelex_hub.set_console_print_target(target=log_config.console_print_target)
log.configure(log_config=log_config)
```

`setup_doctor_runtime` mirrors only `log.configure`, not `set_console_print_target`. So for the human doctor, `get_console()` falls back to `Console(stderr=True)` (hub.py:225-229), silently ignoring `console_print_target = "stdout"` set in `pipelex.toml`. The agent doctor side-steps the bug because `apply_agent_cli_output_discipline()` hard-codes STDERR — but that's load-bearing, not the "defense-in-depth" the docstring claims.

**Fix.** In `setup_doctor_runtime`, after `log_config` is resolved but before `log.configure`, add the `set_console_print_target` call:

```python
log_config = get_config().pipelex.log_config
if log_config_overrides is not None:
    log_config = log_config.model_copy(update=log_config_overrides)
get_pipelex_hub().set_console_print_target(target=log_config.console_print_target)
log.configure(log_config=log_config)
```

Effect:
- Human doctor: `console_print_target` from user config is now applied to the hub — `display_health_report`'s panels go to the configured target instead of always stderr.
- Agent doctor: the override dict's `console_print_target = STDERR` flows through `model_copy` and into `set_console_print_target`, so the hub is pinned to stderr at bootstrap time — making `apply_agent_cli_output_discipline()` genuinely redundant defense-in-depth (matching the docstring).

After this change, also **update the docstring** on `apply_agent_cli_output_discipline` (agent_cli_factory.py:67-76) to remove the "redundant" framing or to acknowledge that the redundancy is true on both paths only after this fix lands.

---

### Group 5 — Pin pipelex package log level in the agent doctor  **[low]**

**Resolves:** Group E — agent doctor never calls `log.set_level_for_package("pipelex", WARNING)`.

**Problem.** The factory `make_pipelex_for_agent_cli` (agent_cli_factory.py:190) calls `log.set_level_for_package("pipelex", log_level)` to hard-pin the pipelex package log level to WARNING. The agent doctor doesn't — it inherits whatever `package_log_levels.pipelex` the user set in their config (commonly VERBOSE/DEBUG in dev setups). So `check_models` → `models_manager.setup` emits verbose log lines via backend_library.py:111/123/138/161/225 and model_deck.py:719+ that other agent CLI commands suppress. Stdout JSON stays clean (good), but stderr gets noisier than the rest of the agent CLI surface.

**Fix.** In `agent_doctor_cmd`, immediately after `setup_doctor_runtime` (or fold into `apply_agent_cli_output_discipline` — see "Design choice" below), add:

```python
from pipelex.tools.log.log_levels import LogLevel
log.set_level_for_package("pipelex", LogLevel.WARNING)
```

**Design choice.** Two reasonable shapes:

- (a) Add the call directly in `agent_doctor_cmd`, alongside `setup_doctor_runtime` and `apply_agent_cli_output_discipline`. Minimal, but the agent CLI's "output discipline" is now spread across three call sites in `agent_doctor_cmd` (and similar future commands).
- (b) Extend `apply_agent_cli_output_discipline` to accept `log_level: LogLevel = LogLevel.WARNING` and call `log.set_level_for_package` itself. Then `agent_doctor_cmd` just calls `apply_agent_cli_output_discipline()` and gets the full agent-CLI policy (silent pretty-print, stderr console, warning floor) in one line. The factory then also passes through its `log_level` parameter.

Pick (b). It makes `apply_agent_cli_output_discipline` actually match its name. The factory's `make_pipelex_for_agent_cli` already has a `log_level` parameter (defaulting to WARNING) — pass it through.

```python
def apply_agent_cli_output_discipline(log_level: LogLevel = LogLevel.WARNING) -> None:
    log.set_level_for_package("pipelex", log_level)
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    get_pipelex_hub().set_console_print_target(target=ConsoleTarget.STDERR)
```

Then in the factory:
```python
log.redirect_to_stderr()
apply_agent_cli_output_discipline(log_level=log_level)
```

And in `agent_doctor_cmd`:
```python
apply_agent_cli_output_discipline()  # default WARNING is fine for doctor
```

---

### Group 6 — Freeze `AGENT_CLI_STDERR_LOG_FIELDS` against mutation  **[low, future-risk]**

**Resolves:** Group F — shared mutable dict.

**Problem.** `AGENT_CLI_STDERR_LOG_FIELDS` (agent_cli_factory.py:57) is a module-level mutable dict. `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES['pipelex']['log_config']` aliases the same object. Both current consumers (`deep_update` in config_loader; `model_copy(update=...)` in setup_doctor_runtime) are read-only on the source — verified — so no live bug. But the contract is fragile against future contributors mutating it.

**Fix.** Wrap in `types.MappingProxyType` so accidental mutation raises immediately:

```python
from types import MappingProxyType

AGENT_CLI_STDERR_LOG_FIELDS: Mapping[str, Any] = MappingProxyType({
    "console_log_target": ConsoleTarget.STDERR,
    "console_print_target": ConsoleTarget.STDERR,
})
```

**Watch out for:** the existing test `test_bootstrap_pins_console_targets_to_stderr` does `assert AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"] is ConsoleTarget.STDERR` — that still works with `MappingProxyType` (membership lookup is fine). The `_AGENT_CLI_STDERR_CONSOLE_OVERRIDES` dict also remains valid as a normal dict containing a frozen leaf — `deep_update` reads the leaf, doesn't mutate it.

Also verify that `log_config.model_copy(update=AGENT_CLI_STDERR_LOG_FIELDS)` accepts a `Mapping` (Pydantic's signature accepts `Mapping[str, Any]`).

---

### Group 7 — Validate the overrides dict on the way in  **[low, future-risk]**

**Resolves:** Group H — `model_copy(update=...)` bypasses validation.

**Problem.** Pydantic v2 `model_copy(update=...)` does NOT re-validate the merged fields. A future caller passing `log_config_overrides={"console_log_target": "stderr"}` (bare string instead of `ConsoleTarget.STDERR`) would silently break match/case dispatch in `make_rich_handler` (log_config.py:71-81), which uses class patterns requiring `isinstance(target, ConsoleTarget)`.

**Fix.** Replace `model_copy(update=...)` with `model_validate(...|...)`:

```python
log_config = get_config().pipelex.log_config
if log_config_overrides is not None:
    log_config = LogConfig.model_validate({**log_config.model_dump(), **log_config_overrides})
```

This re-runs the LogConfig validators, surfacing wrong types loudly. Marginal cost on a single doctor invocation is fine.

**Alternative (stronger).** Define a typed `LogConfigOverrides(BaseModel)` with optional fields, accept it as the parameter type, and assemble the merged `LogConfig` from `log_config.model_dump() | overrides.model_dump(exclude_none=True)`. More boilerplate; pick only if Group 6's `MappingProxyType` doesn't give enough type-safety.

---

### Group 8 — Tighten the test contract  **[low]**

**Resolves:** Group I — `test_bootstrap_pins_console_targets_to_stderr` doesn't assert `apply_agent_cli_output_discipline`; Group J — `test_do_doctor_cmd_delegates_layered_resolution_to_checks` doesn't assert `setup_doctor_runtime`.

**Fix in `tests/unit/pipelex/cli/test_agent_doctor_cmd.py`.** Modify `test_bootstrap_pins_console_targets_to_stderr` (line ~146) to also capture and assert on the discipline mock:

```python
mock_setup = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
mock_discipline = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.apply_agent_cli_output_discipline")
# ... existing check_* mocks ...
agent_doctor_cmd(output_format=CliOutputFormat.JSON)
mock_setup.assert_called_once_with(log_config_overrides=AGENT_CLI_STDERR_LOG_FIELDS)
mock_discipline.assert_called_once()
```

**Fix in `tests/unit/pipelex/cli/test_doctor_cmd.py`.** Capture and assert on `setup_doctor_runtime`:

```python
mock_setup = mocker.patch("pipelex.cli.commands.doctor_cmd.setup_doctor_runtime")
# ... existing check_* mocks and assertions ...
mock_setup.assert_called_once_with()
```

**Note on Group 1 interaction.** If Group 1's reordering is implemented (bootstrap moved to AFTER the filesystem checks), the existing assertion order in `test_do_doctor_cmd_delegates_layered_resolution_to_checks` is unaffected — but consider adding a call-order assertion (`mocker.call_args_list` comparison) to bind the ordering contract.

---

### Group 9 — Address the once-per-process `log.configure` risk  **[low, future-risk]**

**Resolves:** Group K — `log.configure` once-per-process now reachable unconditionally; Group L — window between bootstrap and discipline (overlapping concern about robust idempotence).

**Problem.** `log.configure` (tools/log/log.py:73-110) raises `RuntimeError("LogConfig is already set...")` on a second call. The refactor moved this from inside `check_models` (only reached after backend files were healthy) to unconditional in `setup_doctor_runtime`. No current code path triggers a double-call — verified — but library embedding or in-process test interleaving with `Pipelex.make()` would crash with an opaque RuntimeError.

**Fix.** In `setup_doctor_runtime`, guard the `log.configure` call. Two options:

- (a) Check whether the log is already configured and skip:
  ```python
  if log._log_config_instance is None:
      log.configure(log_config=log_config)
  ```
  Accesses a private attribute; ugly.

- (b) Add a public `log.is_configured() -> bool` (or `log.configure_if_unset(log_config)`) helper to `pipelex/tools/log/log.py` and call it. Cleaner.

Pick (b). Add to `Log` class (or whatever the singleton class is) in `tools/log/log.py`:

```python
def configure_if_unset(self, log_config: LogConfig) -> bool:
    """Configure logging unless already configured. Returns True if configuration was applied."""
    if self._log_config_instance is not None:
        return False
    self.configure(log_config=log_config)
    return True
```

Then `setup_doctor_runtime` calls `log.configure_if_unset(log_config=log_config)`.

**Consider:** if the log is already configured with DIFFERENT targets than the doctor needs (e.g. some embedding process configured it for stdout), what's the right behavior? Option: when `configure_if_unset` returns False AND we needed an override, log a single warning to the existing handler so the operator sees a hint. Out of scope for this fix — leave a `# TODO` if the override path needs special handling.

---

### Group 10 — Document the doctor-path contract on `apply_agent_cli_output_discipline`  **[low, docs]**

**Resolves:** Group G if Group 4 is NOT taken; otherwise no-op after Group 4.

If Group 4 is implemented (move `set_console_print_target` into `setup_doctor_runtime`), the existing "redundant" framing on the discipline function becomes true on both paths. Adjust the docstring to match.

If Group 4 is NOT taken for some reason, the docstring needs a hard rewrite:

```python
def apply_agent_cli_output_discipline(log_level: LogLevel = LogLevel.WARNING) -> None:
    """Pin pretty-print silence, pipelex log level, and hub console target to stderr.

    Called from two paths with different responsibilities:
    - Full-init path (make_pipelex_for_agent_cli): redundant defense-in-depth.
      Pipelex.__init__ already pinned the hub console via set_console_print_target
      from the loaded log_config (whose console_print_target was overridden to STDERR).
    - Doctor-only path (agent_doctor_cmd): LOAD-BEARING for console pinning.
      setup_doctor_runtime does not call set_console_print_target — this function
      is the only thing pinning get_pipelex_hub().set_console_print_target(STDERR).
      Removing this call would break the stdout-JSON contract for the doctor
      command.
    """
```

Group 4 is preferable; reach for the docstring rewrite only if Group 4 is blocked.

## Suggested fix order

Land the fixes in this order (each PR or commit, depending on convention):

1. **Group 3** (report_validation_error masking) — pre-existing bug; fixes the user-facing error message for the most common doctor-broken-config scenario. Smallest surface, no behavior change for healthy configs.
2. **Group 4** (set_console_print_target in setup_doctor_runtime) — pre-existing; resolves Group 10 docstring drift as a side effect.
3. **Group 1** (reorder bootstrap after filesystem checks) — the most user-visible regression of the refactor (silent installer on fresh machines). Test impact: minimal, since the autouse fixture in test_agent_doctor_cmd.py already mocks the bootstrap.
4. **Group 5** (fold log.set_level_for_package into apply_agent_cli_output_discipline) — small, cleanup-style, makes the discipline helper match its name.
5. **Group 2** (config_dir override for setup_doctor_runtime + load_config + setup_config) — biggest surface (touches config_loader, hub, both doctors). Land separately so the diff is reviewable.
6. **Group 8** (test contract assertions) — purely test changes, can ride alongside Groups 1/4/5.
7. **Group 9** (log.configure_if_unset) — defensive; can land any time.
8. **Group 6** (MappingProxyType freeze) — defensive; can land any time.
9. **Group 7** (validate overrides on merge) — defensive; can land any time.

## Verification

For each group, run:

- `make agent-check` — lint, format, pyright, mypy.
- Targeted tests:
  - `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ tests/e2e/pipelex/cli/`
- `make tb` — boot test. The existing boot test already invokes `pipelex-agent doctor --format json` and validates the JSON envelope — confirms Groups 1, 2, 4, 5 don't break the contract.

**Manual reproductions:**

- **Group 1 (silent installer)** — Remove `~/.pipelex/`. Run `.venv/bin/pipelex doctor`. Before the fix: reports "all configs healthy" (after silent creation). After: reports "missing config — run `pipelex init config`."
- **Group 2 (--global)** — In a project that has `.pipelex/pipelex.toml` enabling Gateway, with global `~/.pipelex/pipelex.toml` disabling it, run `.venv/bin/pipelex-agent doctor --global --format json`. Before: gateway probe fires using project (layered) config. After: gateway probe respects `--global`, returns global-only result.
- **Group 3 (validation error masking)** — Edit `~/.pipelex/pipelex.toml` to have a wrong-type field (e.g. `level_pipelex = 42`). Run `.venv/bin/pipelex doctor`. Before: "Unexpected error: Config instance is not set...". After: "Configuration validation failed: <pydantic detail>" with migration hint section if applicable.
- **Group 4 (console_print_target)** — Set `console_print_target = "stdout"` in pipelex.toml. Run `.venv/bin/pipelex doctor 2>/dev/null` (suppress stderr). Before: empty stdout (panels went to stderr). After: panels appear on stdout.
- **Group 5 (log level)** — Set `[pipelex.log_config.package_log_levels] pipelex = "VERBOSE"`. Run `.venv/bin/pipelex-agent doctor --format json 2>&1 1>/dev/null | head -5`. Before: lots of verbose log lines on stderr from check_models internals. After: only WARNING+ on stderr, same as `pipelex-agent run`.

## Out of scope for this plan

- The pre-existing global mutable hub pattern (`set_pipelex_hub(PipelexHub())`) — relocated by the refactor but not introduced by it. Threading a `hub` parameter through `check_*` / `get_config()` / `is_pipelex_gateway_enabled()` is a much bigger surface area change that deserves its own design.
- Doctor's overall structure (one-file-per-check vs single 1000-line module). Worth revisiting but not gated on the bootstrap fixes.

## Pointers for the next session

- The active branch is `fix/Log-target`. The refactor that this plan builds on is currently STAGED (not committed). Before starting these fixes, decide whether to:
  - (a) Commit the refactor as-is first, then land each fix group as its own commit/PR (cleaner history).
  - (b) Amend the refactor commit with these fixes included (one big PR).
- The /code-review skill is what surfaced these findings — it runs 5 finder angles + verification + a sweep. Re-running it after the fixes is a reasonable validation step.
- Memory: there are no stored memories about the doctor module or this refactor. Feel free to write follow-up memories if any of the fixes reveal additional invariants worth remembering across sessions.
