# Handoff: non-interactive `pipelex init --yes` mode

Untracked scratch note (in `wip/`, not gitignored — delete when done). Written from a cocode session that hit the downstream symptom. pipelex version in play: 0.31.0.

## Why we want this

Downstream repos need CI to initialize Pipelex **without** interactive prompts and **without** vendoring a full `.pipelex/` config tree into their repo. Today that's impossible: `pipelex init` is interactive end-to-end.

The concrete trigger: cocode CI started failing with `Pipelex must be initialized before running the tests` after cocode de-vendored its `.pipelex/` config (cocode commit `1dd8831`). cocode's `tests/conftest.py` gates the session on Pipelex's `check_is_initialized()`. On CI there's no global `~/.pipelex/` and (after de-vendoring) no project `.pipelex/`, so the gate aborts the run. Locally it passed only because the dev had a global config.

Important: `--disable-inference` does **not** help here. It skips the *gateway terms* check and swaps in a mock content generator — it never bypassed *initialization* (the presence of config files). Pipelex's own CI sidesteps the problem only because pipelex **vendors its full `.pipelex/` tree in-repo**. We don't want every downstream repo to carry (and keep in sync) a vendored config just to run CI.

**Stopgap already applied in cocode** (to be reverted once this lands): re-vendored a minimal `.pipelex/` CI config (pipelex.toml, plxt.toml, `inference/` backends+deck+routing), force-added past the gitignore. See the "Downstream follow-up" section.

## Goal

Add a non-interactive `pipelex init --yes` (`-y`) that materializes a complete, valid config with zero prompts and exit 0 — such that `check_is_initialized()` returns True — suitable for CI and automation.

## What already exists (good news — it's mostly plumbing)

- `init` CLI command: `pipelex/cli/_cli.py:158` (`init_command`) → calls `init_cmd(focus=focus, local=local)`. No `--yes` exposed yet.
- `init_cmd`: `pipelex/cli/commands/init/command.py:466`. Already takes `skip_confirmation: bool` — but that only gates the **final** "Continue with initialization?" confirm (`command.py:545-563`). It does **not** gate the backend/routing/credentials prompts.
- Pattern to mirror: `update_command` already has `--yes/-y` (`_cli.py:209`) threaded into `update_cmd(yes=...)`. Copy that shape.
- `init_cmd(focus=InitFocus.CONFIG, skip_confirmation=True)` is already called non-interactively from doctor (`doctor_cmd.py:1028,1048`).

**Key insight:** every interactive prompt site already carries a sensible `default=`. So `--yes` is well-bounded: short-circuit each prompt to its existing default instead of asking. The defaults already encode the "yes" answer.

## Prompt sites to short-circuit under `--yes`

Each must return its `default` (or computed default) without prompting:

- `command.py:249` — `Confirm.ask("Continue with initialization?", default=True)`. Verify it isn't reached when `assume_yes` (today it's the `skip_confirmation` path).
- `ui/backends_ui.py:188` — `Prompt.ask("Enter your choices", default=default_str)`. First-time default is `"1"` = `pipelex_gateway` (`backends_ui.py:177-184`). Under `--yes`: accept `default_str` (and the computed `default_indices`) directly.
- `ui/routing_ui.py:63` and `:150` — `Prompt.ask(..., default=...)`. Accept defaults.
- `routing.py:74` — `Confirm.ask("Would you like to create it?", default=True)`. Accept True.
- `credentials.py:140` — `Prompt.ask(var, default="", password=True)`. Under `--yes`: **skip the prompt loop entirely** (default `""` already means "skip, set later" — the UI even says so at `credentials.py:128`). Creds come from env in CI.
- `ide_extension.py:109` — `Confirm.ask(... install IDE extension ...)`. Under `--yes`: default to **No** (don't install in CI). Confirm its current default.
- `ui/gateway_ui.py:107` — `Confirm.ask(...)` gateway terms. **Legal decision — do not silently accept ToS.** See below.

## Recommended implementation

1. Add `--yes/-y` typer option on `init_command` (`_cli.py:158`), mirroring `update_command:209`. Pass it as `assume_yes` into `init_cmd`.
2. Thread `assume_yes` into `init_cmd` and down to the UI helpers (`backends_ui`, `routing_ui`, `routing`, `credentials`, `ide_extension`, `gateway_ui`). Centralize with a tiny helper, e.g. `ask_or_default(assume_yes, ask_fn, default)`, so each site reads cleanly.
3. Reconcile with `skip_confirmation`: cleanest is to introduce `assume_yes` and have it **subsume** `skip_confirmation` (assume_yes ⇒ skip the final confirm too). Update the doctor callsites (`doctor_cmd.py:1028,1048`) accordingly.
4. Credentials under `--yes`: skip the loop; don't write blank entries to `.env`.
5. **High-value optional:** auto-enable `assume_yes` when non-interactive — `not sys.stdin.isatty()` or a CI env var (`GITHUB_ACTIONS`/`CI`, already detected via `runtime_manager`/`shared_pytest_plugins.py`). Then CI "just works" even without the flag, and a closed stdin never hangs.

## Gateway terms — handle deliberately

Do **not** auto-accept the Pipelex Gateway ToS just because `--yes` was passed. Options, pick one:
- In CI mode (`runtime_manager.is_ci_testing` / `IntegrationMode.CI`) terms are already skipped for the *test run*; for `init --yes` itself, leave the gateway **enabled but unaccepted** and let the CI test path (which uses mock inference) proceed — it never calls the gateway.
- Or require a separate explicit opt-in for acceptance: `--accept-terms` flag or `PIPELEX_ACCEPT_TERMS=1` env. `--yes` alone should not constitute legal acceptance.

## Resulting config must satisfy `check_is_initialized()`

`pipelex/system/configuration/config_check.py:12-18` requires all of: `pipelex.toml`, `plxt.toml`, the backends file (`config_manager.backends_file_path`), and the routing-profiles file (`config_manager.routing_profiles_file_path`) — resolvable in project or global dir. `--yes` must produce all of them. Default backend = `pipelex_gateway`; default routing profile; telemetry default (decide: accept default vs. disable in non-interactive — check the telemetry default).

## Acceptance criteria

In an environment with **no** global `~/.pipelex/` and **no** project `.pipelex/`:
- `pipelex init --yes --local` → exit 0, **zero prompts**, creates `.pipelex/` such that `python -c "from pipelex.system.configuration.config_check import check_is_initialized; assert check_is_initialized()"` passes.
- `pipelex init --yes` (global) → same for `~/.pipelex/`.
- Runs with stdin closed / non-tty must not hang.
- Gateway ToS is **not** silently accepted (assert).
- The existing interactive `pipelex init` flow is unchanged.

## Tests / conformance

- Unit-test `init_cmd(assume_yes=True)` in a tmp config dir (monkeypatch the config dirs). Patch `Confirm.ask`/`Prompt.ask` to **raise** if called, proving no prompts fire; assert the files exist and `check_is_initialized()` is True.
- The init CLI is a cross-repo surface — there's likely a spec in the workspace `docs/specs/` with a paired test in the `conformance/` repo (see workspace CLAUDE.md). Add the `--yes` flag to that spec section, add a conformance test, and run `conformance/scripts/check-spec-links.py`.

## Downstream follow-up (don't lose this)

Once `init --yes` ships and pipelex is re-released + re-pinned:
- **cocode:** revert the stopgap — remove the re-vendored `.pipelex/` config (currently staged on branch `release/v0.7.0`), and instead either add a CI step `pipelex init --yes --local` before `make gha-tests` in `.github/workflows/tests-check.yml`, **or** rely on auto-init-when-non-tty/CI if you implement option 5 (then cocode's conftest can call an init helper rather than just gating).
- Audit other repos that vendor `.pipelex/` purely for CI (e.g. `methods/`, `test-bed/`, `pipelex-api-deploy/`) — they can adopt the same `init --yes` pattern.

## Files likely to touch

- `pipelex/cli/_cli.py` — `init_command`: add `--yes/-y`, pass through.
- `pipelex/cli/commands/init/command.py` — `init_cmd`: accept `assume_yes`, thread it, reconcile `skip_confirmation`.
- `pipelex/cli/commands/init/ui/backends_ui.py` — short-circuit to default selection.
- `pipelex/cli/commands/init/ui/routing_ui.py` — short-circuit to defaults.
- `pipelex/cli/commands/init/routing.py` — `Confirm` default.
- `pipelex/cli/commands/init/credentials.py` — skip the loop under `assume_yes`.
- `pipelex/cli/commands/init/ide_extension.py` — default No under `assume_yes`.
- `pipelex/cli/commands/init/ui/gateway_ui.py` — terms handling (deliberate).
- `pipelex/cli/commands/doctor_cmd.py` — update callsites if `skip_confirmation` is folded into `assume_yes`.
- Tests + `docs/specs/` + `conformance/`.
