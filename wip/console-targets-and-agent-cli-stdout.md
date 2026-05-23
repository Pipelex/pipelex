# Console targets — partial revert + agent CLI stdout hardening

> **Status:** In progress on branch `fix/Log-target` (commit `ac858de8`). The current commit overshot the fix; this doc captures the partial revert that needs to land on top of it AND the deeper improvement for the agent CLI's stdout contract.
>
> **Cold-start prerequisite:** read `pipelex/tools/log/log.py:91`, `pipelex/hub.py:137-148`, `pipelex/cli/agent_cli/commands/agent_cli_factory.py:118-122`, `pipelex/cli/agent_cli/commands/agent_output.py` (where `agent_success` writes to stdout), and `pipelex/tools/misc/pretty.py:214` (the bare `Console()` instantiation).

## TL;DR

We have two independent knobs in `[pipelex.log_config]`:

- `console_log_target` — controls the `RichHandler` attached to Python's logging system. **Logs are diagnostics → stderr.** Flipping the default to `stderr` is correct and stays.
- `console_print_target` — controls the hub's `_console` returned by `get_console()`. This console is used by the main `pipelex` CLI for human-facing **data tables** (`pipelex show backends`, `pipelex show models`, `pipelex which`, `pipelex doctor`). **Data → stdout.** Flipping the default to `stderr` was an over-correction and must be reverted.

The actual bug ("logs polluting stdout breaks downstream JSON parsers like `mthds-js`'s `PipelexRunner`") was about logs, not prints. The log-target flip alone fixes it.

Separately, the agent CLI's stdout channel is a strict JSON contract for downstream tooling. It deserves explicit, defense-in-depth hardening at the factory level so a user override in `~/.pipelex/pipelex.toml` cannot re-pollute it.

## Part 1 — Partial revert on `fix/Log-target`

### What stays

In all three TOML files, **keep** `console_log_target = "stderr"`:

- `pipelex/pipelex.toml:73`
- `pipelex/kit/configs/pipelex.toml:164`
- `.pipelex/pipelex.toml:164`

Rationale: logs are diagnostics, they belong on stderr per 12-factor/Unix convention. This matches the stated intent of PR #452 ("default to stderr for outputs happening before initialization"). Empirically this is what surfaces the original bug — the failing case in `tests/e2e/agent_cli/test_stdout_is_clean_json.py` is a `log.debug(...)` call from `pipelex/system/telemetry/telemetry_factory.py:77` routed through the `RichHandler`, which obeys `console_log_target`.

### What reverts

In all three TOML files, **flip back** `console_print_target = "stdout"`:

- `pipelex/pipelex.toml:74` → `console_print_target = "stdout"`
- `pipelex/kit/configs/pipelex.toml:165` → `console_print_target = "stdout"`
- `.pipelex/pipelex.toml:165` → `console_print_target = "stdout"`

Rationale: confirmed user-facing regression. With the post-flip tree:

```
$ .venv/bin/pipelex show backends > out.txt 2> err.txt
$ wc -c out.txt err.txt
   0 out.txt
4110 err.txt
```

The entire backends table now lands on stderr. Same regression for `pipelex show models <backend>`, `pipelex which <code>`, `pipelex doctor`, and especially `pipelex show models <backend> --flat` whose docstring explicitly advertises it as "easy to copy-paste into configuration files".

The breakage is real because `pipelex show backends` (and friends) route through `get_console()` → `pipelex_hub._console` → controlled by `console_print_target`. See `pipelex/cli/commands/show_cmd.py:96` and the `pipelex_hub.set_console_print_target(...)` call at `pipelex/pipelex.py:118` driven by the config value.

### What changes in tests

`tests/unit/pipelex/tools/test_log_config_defaults.py` (already on the branch): widen the assertion to pin both targets to their intended values, so neither knob can be flipped silently in either direction:

```python
assert log_config.console_log_target == ConsoleTarget.STDERR  # logs are diagnostics
assert log_config.console_print_target == ConsoleTarget.STDOUT  # prints are data
```

Also extend the test to additionally validate the **kit template** (`pipelex/kit/configs/pipelex.toml`) — currently a partial revert of just the kit template (the file `pipelex init` copies to `~/.pipelex/`) would pass this test silently. Either add a second test or parametrize over both `(package_default, kit_template)` paths.

`tests/e2e/agent_cli/test_stdout_is_clean_json.py` (already on the branch): no changes needed — it surfaces the LOG-target bug via the `RichHandler`, and the log target stays `stderr` post-revert. The test stays green and stays meaningful.

### What changes in the changelog

Rewrite the `## [Unreleased]` entry to narrow the scope. Replace the current single bullet with:

```markdown
### Fixed

- **`console_log_target` package default is now `stderr` (was `stdout`).** Logs now stay off the data channel by default, matching the intent of PR #452 ("default to stderr for outputs happening before initialization"). Downstream tooling that parses `pipelex` / `pipelex-agent` stdout as JSON (e.g. `mthds-js`'s `PipelexRunner`) is no longer at risk of stdout pollution from package-level logs — the bug was latent for stock installs because the agent-CLI JSON paths happen not to log at INFO+, but surfaced for anyone who raised `package_log_levels.pipelex` to DEBUG or added a setup-time log on the command path. Same flip applied to the kit template (`pipelex/kit/configs/pipelex.toml`) that `pipelex init` copies to `~/.pipelex/`. **Note:** `console_print_target` is intentionally left at `stdout` — the main `pipelex` CLI emits human-facing tables (`show backends`, `show models`, `which`, `doctor`) via that channel, and downstream piping (`pipelex show backends > out.txt`) must keep working.
```

Drop the migration sentence that said "anyone who was capturing stdout to collect logs should switch to capturing stderr" — it's no longer true at this scope (logs were on stdout already only by virtue of `console_log_target = "stdout"`; same flip). Keep the framing as a `Fixed`, not a `Breaking`, because no user behavior that *should have worked* gets broken.

### Commit shape

One commit on `fix/Log-target`:

```
fix(logs): keep console_print_target on stdout (logs to stderr, prints to stdout)

Walks back the print_target half of ac858de8 — that flip broke
`pipelex show backends > out.txt` (empty file). Log target stays on
stderr (the actual fix for stdout-as-JSON-channel pollution); print
target reverts to stdout because the main pipelex CLI's human-facing
tables go through get_console() and must remain redirectable.
```

Then run `make agent-check && make agent-test` and force-push the branch (history-rewrite is fine here since the PR isn't merged yet).

## Part 2 — Agent CLI stdout hardening (the deeper fix)

> Why this is its own piece of work: the partial revert above restores correctness for stock installs, but the agent CLI's stdout-as-JSON-channel contract is too important to leave at the mercy of the user's `~/.pipelex/pipelex.toml`. A user override of `console_print_target = "stderr"` shouldn't break the agent CLI's data channel either way, and a hypothetical override of `console_log_target = "stdout"` must NOT re-pollute the agent CLI's stdout. The defense should live in the factory, not depend on the config defaults staying lucky.

### The contract we want

For every `pipelex-agent <command>` invocation:

| Channel | What goes there | Enforcement |
|---|---|---|
| **stdout** | ONLY the structured success envelope (JSON via `--format json`, or markdown via `--format markdown`). Nothing else. | `agent_success` / `agent_success_formatted` use bare `print(...)` to stdout — that's it. No log handler, no hub console, no `pretty_print` ever writes to stdout. |
| **stderr** | Logs (any level), all `get_console().print(...)` output (banners, deck notices, plugin list tables), all `pretty_print(...)` output (currently silenced via `PrettyPrinter.mode = PrettyPrintMode.SILENT`), structured error envelopes via `agent_error`. | Factory forces all three subsystems to stderr at boot, regardless of user config. |

The contract must hold:

- Regardless of `console_log_target` / `console_print_target` in the user's config.
- Regardless of `package_log_levels.pipelex` raising the verbosity.
- Regardless of any `get_console().print(...)` call site added in the future on the agent CLI's setup or command path.

### Current state (`make_pipelex_for_agent_cli`, `pipelex/cli/agent_cli/commands/agent_cli_factory.py:118-122`)

```python
# Suppress Rich pretty-printing and INFO/DEV/DEBUG log noise so that agent
# commands only emit structured JSON.  Warnings and errors still reach stderr.
PrettyPrinter.mode = PrettyPrintMode.SILENT
log.set_level_for_package("pipelex", log_level)
log.redirect_to_stderr()
return pipelex_instance
```

- ✅ `PrettyPrinter.mode = SILENT` neutralizes `pretty_print(...)` entirely (the bare `Console()` at `pretty.py:214` would have hit stdout — silencing the printer is the simplest defense).
- ✅ `log.redirect_to_stderr()` forces `RichHandler.console = Console(file=sys.stderr)` regardless of `console_log_target`.
- ❌ **Missing:** no symmetric `pipelex_hub.set_console_print_target(ConsoleTarget.STDERR)` call. The hub's `_console` is whatever the user's `console_print_target` says — which, after Part 1, defaults to stdout. So any `get_console().print(...)` reached during agent CLI setup or command execution writes to stdout. That's a JSON-channel pollution risk.

### Where `get_console()` is reached on the agent CLI path

Grep `get_console` across the codebase. Today the call sites include:

- `pipelex/cli/_cli.py:111` — banner in `app_callback` (main CLI only, the agent CLI has its own callback in `_agent_cli.py` which does not print the banner — verify).
- `pipelex/cli/deck_notice.py:34` — first-run deck notice. Triggered from `Pipelex.make()` setup paths. Could fire under the agent CLI.
- `pipelex/plugins/openai/openai_list.py`, `anthropic_list.py`, `google_list.py`, `mistral_list.py`, `bedrock_list.py` — backend list tables. Reachable from `pipelex show models <backend>` (main CLI) but NOT directly from agent CLI commands today — verify.
- `pipelex/cli/error_handlers.py` — error panels for various exception types. Used by the main CLI, not the agent CLI (agent CLI uses `agent_error()` instead).

The risk surface today is small — primarily `deck_notice` and any future setup-time addition. But "small" is not "zero", and the contract is too important to depend on a static-analysis snapshot.

### The fix

Add ONE line to `make_pipelex_for_agent_cli` (after Pipelex init, alongside the existing log redirect):

```python
from pipelex.hub import get_pipelex_hub
from pipelex.system.console_target import ConsoleTarget

# (after PrettyPrinter.mode = SILENT and before/after log.redirect_to_stderr())
get_pipelex_hub().set_console_print_target(target=ConsoleTarget.STDERR)
```

This makes `get_console()` return a stderr-bound Console for the entire agent CLI process lifetime, regardless of what the user's config said. Symmetric to `log.redirect_to_stderr()`. Together with the existing `PrettyPrinter.mode = SILENT`, every diagnostic output channel is pinned to stderr at the boundary.

Confirm the hub-access import path: today the file imports `Pipelex`, not the hub directly. Find the canonical import (it's likely `from pipelex.hub import get_pipelex_hub` — verify in `pipelex/hub.py`).

### Test coverage

Add a new test (or extend `tests/e2e/agent_cli/test_stdout_is_clean_json.py`) that pins the defense:

**Test: agent CLI ignores user override of `console_print_target = "stderr"`** — wait, this would actually trivially pass since the override IS stderr. The real test is the **inverse**:

**Test: agent CLI keeps stdout clean even when user overrides BOTH targets to stdout.**

```python
def test_agent_cli_resists_user_override_to_stdout(
    self,
    hermetic_home: Path,
    offline_subprocess_env: dict[str, str],
) -> None:
    """Defense-in-depth: even with `console_log_target = "stdout"` AND
    `console_print_target = "stdout"` in the user's pipelex.toml, the agent
    CLI must keep its stdout channel clean for JSON consumers.
    """
    pipelex_toml = hermetic_home / ".pipelex" / "pipelex.toml"
    _set_pipelex_package_log_level_to_debug(pipelex_toml)
    _set_console_targets(pipelex_toml, log_target="stdout", print_target="stdout")

    result = subprocess.run(
        [str(PIPELEX_AGENT_BIN), "--log-level", "debug", "models", "--format", "json"],
        env=offline_subprocess_env, cwd=str(hermetic_home),
        capture_output=True, text=True, check=False, timeout=120,
    )

    assert result.returncode == 0, ...
    payload = json.loads(result.stdout)  # must still parse cleanly
    assert payload.get("success") is True
```

This is the test that pins the contract end-to-end. The helper `_set_console_targets` rewrites the two TOML keys (similar to the existing `_set_pipelex_package_log_level_to_debug`). Watch out for the helper-fragility class flagged in the code review (use anchored regex or a tomlkit round-trip rather than `startswith`).

Optionally also parametrize the test across multiple JSON-emitting agent commands (`models`, `check-model`, `validate bundle --format json --dry-run`, `doctor --format json`) so a future setup-path `get_console()` addition on any one of them surfaces immediately.

### Companion: audit `get_console()` call sites for "data vs diagnostic"

This is the larger architectural cleanup, NOT in scope for this PR but worth a follow-up issue:

`get_console()` today is used for both:

- **Data** that users pipe to files (`pipelex show backends`, `pipelex show models`, `pipelex which`) — should write to stdout.
- **Diagnostics** that users want on stderr (banners, deck notices, error panels) — should write to stderr.

Mixing the two in one knob is the root cause of the current confusion. The cleanest long-term shape is to split the hub into two consoles:

- `hub.get_data_console()` — pinned to stdout. Used by `show backends`, `show models`, `which`, `doctor`, `show config`, `show pipe`. Always redirectable to a file.
- `hub.get_diag_console()` — pinned to stderr. Used by banner, deck notice, error panels, anything that's "talking to the human about the run".

`pretty_print` would also pick one of the two (probably `data` for `show pipe`, `show config`; or expose both flavors). The `console_print_target` config knob then either goes away entirely (the split is hardcoded) or is renamed and re-scoped to only the diag console (which would be weird since stderr is the only sensible default).

That's a bigger PR. Out of scope for `fix/Log-target`. File as a follow-up.

## Acceptance criteria

For Part 1 (partial revert) — must hold before re-pushing `fix/Log-target`:

- [ ] `console_log_target = "stderr"` in all three TOML files.
- [ ] `console_print_target = "stdout"` in all three TOML files.
- [ ] `pipelex show backends > /tmp/out.txt && [ -s /tmp/out.txt ]` (non-empty stdout).
- [ ] `pipelex-agent --log-level debug models --format json | jq .success` returns `true` (stdout still clean JSON).
- [ ] Unit test pins both targets (log=stderr, print=stdout); covers package default AND kit template paths.
- [ ] E2E test still passes — surfaces the log-target bug via `log.debug` → RichHandler → stderr.
- [ ] CHANGELOG entry narrowed to scope (logs only).
- [ ] `make agent-check && make agent-test` clean.

For Part 2 (agent CLI hardening) — must hold before merging the follow-up PR:

- [ ] `make_pipelex_for_agent_cli` calls `get_pipelex_hub().set_console_print_target(ConsoleTarget.STDERR)` alongside `log.redirect_to_stderr()`.
- [ ] New E2E test pins the contract under adversarial user overrides (both targets set to stdout, package log level DEBUG, --log-level debug).
- [ ] (Optional but recommended) E2E test parametrized across `models`, `check-model`, `doctor`, `validate bundle` — all JSON-emitting agent commands.
- [ ] Docstring of `make_pipelex_for_agent_cli` updated to explicitly call out the stdout-channel contract.

## How to start (cold)

1. `git checkout fix/Log-target && git log --oneline -3` — confirm at `ac858de8`.
2. Run the regression check first to internalize what's broken:
   ```
   .venv/bin/pipelex show backends > /tmp/out.txt 2> /tmp/err.txt
   wc -c /tmp/out.txt /tmp/err.txt  # expect 0 out, ~4k err
   ```
3. Do Part 1 (partial revert + test + changelog) as one commit. Push.
4. Open a fresh branch `feature/agent-cli-stdout-defense` off `dev` (after Part 1 lands) for Part 2.
5. Implement Part 2 (one-line hub call + new E2E test + docstring update). Push as a separate PR.

## References

- Original bug commit: `ac858de8` "fix: route console logs and prints to stderr by default"
- The PR that introduced the targetable knobs: `dd0c9d266` "feature/JSONContent" (PR #452, 2025-11-18) — stated intent was stderr defaults; the package default ended up flipped to stdout.
- The PR that propagated the wrong default into the kit template: `9580406c` "Feature/chicago" (PR #706, 2026-02-25).
- Downstream JSON consumer that motivated the fix: `mthds-js`'s `PipelexRunner` — does `JSON.parse(stdout)` on `pipelex-agent models --format json`, `check-model --format json`, etc.
- Agent CLI authoring conventions: `pipelex/cli/agent_cli/CLAUDE.md`.
