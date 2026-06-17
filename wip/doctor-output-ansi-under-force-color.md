# `pipelex doctor` — ANSI in captured output under `FORCE_COLOR`, and whether to offer a plain mode

**Status:** deferred to a follow-up PR — investigation done, decision pending. **Low priority.**
**Origin:** surfaced while bringing `pipelex-worker` onto the keyword-only branch pin (PR #23). Its `pipelex doctor` config-health smoke test failed because the captured output contained ANSI codes that defeated a section regex.

## TL;DR (corrected conclusion)

**This is not a pipelex defect.** `pipelex doctor` already honors rich's standard, env-driven color detection: when stdout is not a TTY it emits **plain text**, and it respects both `NO_COLOR` and `FORCE_COLOR`. The ANSI codes we saw in captured `doctor` output came from **`FORCE_COLOR=3` set in the agent/session environment**, which rich (correctly) obeys even when stdout is piped. In a vanilla CI/piped context with no `FORCE_COLOR`, `doctor` output is already plain and the worker's original regex would have matched.

So there is **likely nothing to fix in pipelex**. The only open question is an optional ergonomics one (below).

## Evidence

`pipelex doctor` run against the pipelex-worker `.pipelex/` config, output redirected to a file (non-TTY), counting ANSI escape sequences (`\x1b[…m`):

| Condition | ANSI escapes | `Configuration Files ✓` regex matches? |
| --- | ---: | --- |
| `FORCE_COLOR=3` set (this agent env) | 114 | no |
| `FORCE_COLOR` unset, piped (vanilla CI-like) | 0 | **yes** |
| `FORCE_COLOR` unset + `NO_COLOR=1` | 0 | yes |

With `FORCE_COLOR` set, adding `NO_COLOR=1` dropped the color codes but left bold/reset (`\x1b[1m`/`\x1b[0m`) — rich still considers the stream a terminal, so it keeps non-color styling. That residual reset between `Configuration Files` and the `✓` is what broke the regex.

The console is built without any `force_terminal`: `pipelex/cli/commands/doctor_cmd.py` renders via `get_console()`, which in `pipelex/hub.py` returns a plain `Console(file=sys.stdout)` / `Console(stderr=True)`. Rich's env-driven detection does the rest. (For contrast, `pipelex/tools/misc/pretty.py` already pins `force_terminal=False` on its export consoles — the right call for capture.)

## What we already did (no further action needed for it)

`pipelex-worker/tests/test_config_health.py` now strips ANSI before matching (PR #23). That is a good **defensive** fix and should stay regardless of the decision below: agent/CI runners sometimes set `FORCE_COLOR`, and a smoke test that asserts on captured CLI text should normalize ANSI so it isn't hostage to the runner's color env.

## The genuine (optional) question for the next PR

Should a **diagnostic** command like `pipelex doctor` — whose output is frequently captured (CI smoke tests, support bundles, log scrapers) — produce deterministic plain output even when `FORCE_COLOR` is set in the environment?

- **(a) Do nothing.** Current behavior is standard and idiomatic; consumers that capture `doctor` output normalize ANSI themselves (the worker now does). **Recommended baseline** unless we get bitten again.
- **(b) Add a `--plain` / `--no-color` flag** to `doctor` (and perhaps other diagnostic commands) that forces a non-styled console for the command's duration — e.g. `Console(file=sys.stdout, no_color=True, force_terminal=False)`. Small, self-contained, nicer for CI/scripting; lets callers get clean output without env juggling. Pick this if we want first-class machine-friendly diagnostics.
- **(c) Make `doctor` ignore `FORCE_COLOR` and key purely off `isatty`.** **Rejected** — it overrides the user's explicit `FORCE_COLOR` and is surprising.

**Recommendation:** ship **(a)** as the baseline (i.e. nothing), and reach for **(b)** only if/when we want first-class capturable diagnostics or hit this again.

## Where to look if we do (b)

- `pipelex/cli/commands/doctor_cmd.py` — the doctor command; renders via `get_console()` with rich markup.
- `pipelex/hub.py` — `get_console()` (~`:255`), `set_console_print_target` / `set_console` (~`:148`). A `--plain` flag would set a `Console(no_color=True, force_terminal=False, file=sys.stdout)` on the hub for the command, then restore.
- `pipelex/cli/agent_cli/commands/doctor_cmd.py` — the agent-CLI twin; keep behavior consistent if we add a flag.
- Precedent for capture-safe consoles: `pipelex/tools/misc/pretty.py` (`force_terminal=False`).
