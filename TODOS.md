# Agent CLI logging-discipline hardening — TODOS

## Context (read this first on a cold start)

**Branch:** `release/v0.30.1`
**Working dir:** `/Users/lchoquel/repos/Pipelex/pipelex`

### What this work is about

A reviewer flagged a real bug at `pipelex/cli/agent_cli/commands/agent_cli_factory.py:75` (pre-fix line number): the agent CLI's `package_log_levels` override only pinned `pipelex = OFF`, but `deep_update` deep-merges it into the user config. Third-party loggers (anthropic, httpx, botocore, openai, ...) configured at INFO/WARNING in `pipelex/pipelex.toml` kept emitting through the root's `RichHandler` (now pointing at stderr) — corrupting the JSON error envelope that downstream parsers (e.g. `mthds-js`'s `PipelexRunner`) expect.

### What's been done in the current session

First pass tried to enumerate every third-party logger (brittle list). User pushed back: "Listing feels like an uphill battle — do we control enough of the logging config to just cut off all logs to stdout and stderr regardless of what package sends them?"

Second pass landed the correct fix: `logging.disable(LOGGING_LEVEL_OFF)` as a process-global cutoff called at the start of `make_pipelex_for_agent_cli` and `agent_doctor_cmd`. Records get filtered in `Logger.isEnabledFor` BEFORE any per-logger level check — no list to maintain.

Files modified in this session (staged, not committed):

- `pipelex/cli/agent_cli/commands/agent_cli_factory.py` — added `silence_logging_for_agent_cli()`; simplified `apply_agent_cli_output_discipline()`; simplified `AGENT_CLI_STDERR_LOG_FIELDS` back to `{pipelex: OFF}`
- `pipelex/cli/agent_cli/commands/doctor_cmd.py` — wired `silence_logging_for_agent_cli` at top of `agent_doctor_cmd`
- `tests/e2e/agent_cli/test_stdout_is_clean_json.py` — added the third-party-logger leak regression test; refactored `_set_package_log_level` helper
- `tests/unit/pipelex/cli/test_agent_cli_factory_init_overrides.py` — updated for the new design
- `tests/unit/pipelex/cli/test_agent_cli_factory_suppression.py` — replaced per-logger level assertion with `isEnabledFor` checks
- `tests/unit/pipelex/cli/test_agent_cli_output_discipline.py` — renamed test class, added `silence_logging_for_agent_cli` regression
- `tests/unit/pipelex/cli/test_agent_doctor_cmd.py` — stubbed `silence_logging_for_agent_cli` in the bootstrap fixture

State: `make agent-check` clean. Targeted unit/integration/e2e tests pass (1541 pass / 1 skip).

### Why we have more TODOs

A `/code-review` pass found 15 findings. After triage with the user, 6 actionable items remain (rest are skipped or made moot by the structural fix). Decisions are baked into the steps below.

### Key references

- The source-of-truth docstring for the cutoff is `pipelex/cli/agent_cli/commands/agent_cli_factory.py:95` (`silence_logging_for_agent_cli`).
- The comment block at `pipelex/cli/agent_cli/commands/agent_cli_factory.py:32-83` explains why the listing approach was abandoned and how the four knobs in `AGENT_CLI_STDERR_LOG_FIELDS` relate to the global cutoff.
- The e2e regression test for the original third-party leak: `tests/e2e/agent_cli/test_stdout_is_clean_json.py::test_models_json_stdout_and_stderr_stay_clean_under_third_party_logger_enabled`.

---

## Phase 1 — Structural fix (the biggest change)

Single architectural shift: every agent CLI command must traverse `app_callback` in `pipelex/cli/agent_cli/_agent_cli.py`. Wiring the silence call there guarantees every current AND future command is covered, even ones (like `init_cmd`, `accept_gateway_terms_cmd`) that bypass `make_pipelex_for_agent_cli`.

- [x] **Step 1.1** — Read `pipelex/cli/agent_cli/_agent_cli.py` to locate `app_callback` (around line 81 per the review). Confirm it's the typer choke point every command runs through, and that `set_agent_cli_error_format(CliOutputFormat.JSON)` already lives there.
- [x] **Step 1.2** — Add `silence_logging_for_agent_cli()` call at the top of `app_callback`, BEFORE `set_agent_cli_error_format`. Import the symbol from `pipelex.cli.agent_cli.commands.agent_cli_factory`.
- [x] **Step 1.3** — Decide: keep the existing per-call invocations in `make_pipelex_for_agent_cli:166` and `agent_doctor_cmd:134` OR remove them.
  - **Decision recorded:** KEEP both. `silence_logging_for_agent_cli` is idempotent (calling `logging.disable` twice with the same value is a no-op). Keeping preserves defense for direct library callers of `make_pipelex_for_agent_cli` and avoids breaking the unit tests that mock `Pipelex.make` and call the factory directly (they assert `logging.root.manager.disable == LOGGING_LEVEL_OFF` after the call).
- [x] **Step 1.4** — Update docstrings: `silence_logging_for_agent_cli`'s docstring says "Must be called at the very start of every agent CLI entry point (`make_pipelex_for_agent_cli`, `agent_doctor_cmd`)" — rewrite to reflect that `app_callback` is now the primary armor and the per-call invocations are belt-and-braces.

### ✅ CHECKPOINT 1 — verify before continuing

The structural change is invasive enough that a regression here would mask everything else. STOP here and:

- [x] Run `make agent-check` — must be clean. **Result:** 0 pyright errors, mypy success on 1893 files.
- [x] Run the unit suite for cli/: `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/cli/`. Must pass. **Result:** 349 passed in 10.29s.
- [x] Run the e2e: `.venv/bin/pytest --tb=short -q tests/e2e/agent_cli/test_stdout_is_clean_json.py`. Must pass — both the original three tests AND the new third-party-leak test. **Result:** 3 passed in 3.02s (incl. `test_models_json_stdout_and_stderr_stay_clean_under_third_party_logger_enabled`).
- [x] Manually verify with a fresh shell that `pipelex-agent init --format json` produces a clean stderr in offline mode (no httpx INFO leaks). **Result:** stderr is exactly the structured `ArgumentError` envelope (no project root in `/tmp`); no log lines. Confirms `app_callback` runs and silences logging even on the `init`/`accept-gateway-terms` paths that bypass `make_pipelex_for_agent_cli` (verified by grep — neither cmd module calls `silence_logging_for_agent_cli` nor the factory).

**Cold-start handoff at this checkpoint:** if the session ends here, the next agent should re-read this TODOS.md (especially the "Context" section above), then `git diff HEAD` to see what's staged. If Step 1.2 landed but the verify failed, the regression is most likely in `_agent_cli.py` — check that `app_callback` runs unconditionally for every command, not gated on some Typer flag. If verify passed, Phase 2 is independent and can start fresh.

---

## Phase 2 — Production-code hardening + test-fixture leak fix

Three small fixes, tightly related. Land together.

- [x] **Step 2.1 (fixes #9)** — In `pipelex/cli/agent_cli/commands/agent_cli_factory.py`, change `silence_logging_for_agent_cli` to call `logging.disable(sys.maxsize)` instead of `logging.disable(LOGGING_LEVEL_OFF)`. Add `import sys` if missing. Keep `LOGGING_LEVEL_OFF` import only if still used elsewhere in the file. Update the docstring's "blocks DEBUG through CRITICAL" line to "blocks every record at every level (including custom levels above CRITICAL)". **Done:** added `import sys`, removed `LOGGING_LEVEL_OFF` import (no other uses in file), updated docstring + the comment block at lines 32-49 that also referenced the old constant.
- [x] **Step 2.2 (fixes #9 tests)** — Update assertions in `tests/unit/pipelex/cli/test_agent_cli_factory_init_overrides.py:85` and `tests/unit/pipelex/cli/test_agent_cli_output_discipline.py` that compare `logging.root.manager.disable` to `LOGGING_LEVEL_OFF`. Change to compare to `sys.maxsize`. Update imports. **Done:** swapped both assertions and import statements; updated module/test docstrings.
- [x] **Step 2.3 (fixes #3)** — In `tests/unit/pipelex/cli/test_agent_cli_factory.py:31-39`, extend the autouse `_restore_globals` fixture to save/restore `logging.root.manager.disable` alongside `PrettyPrinter.mode` and `root_logger.level`. Follow the pattern from `test_agent_cli_factory_init_overrides.py`. **Done.**
- [x] **Step 2.4 (fixes #11)** — In `tests/unit/pipelex/cli/test_agent_cli_factory_suppression.py:22-30` AND `tests/unit/pipelex/cli/test_agent_cli_output_discipline.py:32-40`, extend the autouse fixture to snapshot and restore the `.level` attribute of every logger the tests arm. Targets to cover:
  - In `test_agent_cli_factory_suppression.py`: `pipelex`, `anthropic`, `httpx`, `some.unknown.transitive.dep`. **Done** (via module-level `_ARMED_LOGGER_NAMES` tuple consumed by the fixture).
  - In `test_agent_cli_output_discipline.py`: `anthropic`, `httpx`, `some.transitive.dep.we.never.heard.of`. **Done** (same pattern). Note: the TODOS step also mentioned `_THIRD_PARTY_PACKAGES` — that symbol does not exist anywhere in `pipelex/` or `tests/` (grep confirms), so it was a stale reference from the abandoned enumeration approach. The actual loggers armed by the test body are the three listed; nothing more to restore.

### ✅ CHECKPOINT 2 — verify before continuing

Production-code changes are done. Test-only work remains.

- [x] Run `make agent-check`. Must be clean. **Result:** 0 pyright errors, mypy success on 1893 files.
- [x] Run targeted: `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/cli/ tests/unit/pipelex/tools/test_log_config.py tests/e2e/agent_cli/`. Must pass. **Result:** 366 passed in 43.36s.
- [x] Run `make tb` (boot test) — sanity check on config loading. **Result:** 2 passed, 6708 deselected in 5.67s.

**Cold-start handoff at this checkpoint:** next agent reads this TODOS.md, runs `git diff HEAD --stat` to see what's staged. Phase 3 is test-only and can land in a fresh session safely. If anything in Phase 2 broke, the most likely culprits are: (a) the `sys.maxsize` swap left a dangling `LOGGING_LEVEL_OFF` import; (b) the fixture extension overlooked one of the logger names. Re-grep the test files for `setLevel(` calls and verify each target is in the restore loop.

---

## Phase 3 — Test/helper robustness (independent improvements)

- [x] **Step 3.1 (fixes #13)** — In `tests/e2e/agent_cli/test_stdout_is_clean_json.py::test_models_json_stdout_and_stderr_stay_clean_under_third_party_logger_enabled`, replace the `assert result.stderr == ""` with: stderr must be either empty OR parse as a structured error envelope (a dict with `error` field). This catches log-line leaks (which would not be valid JSON) while tolerating environmental noise like ResourceWarnings. Helper: try `json.loads(result.stderr)` and accept either parse-success-with-envelope-shape or empty. **Done:** added `_assert_stderr_is_clean_or_structured_envelope` helper; the test now calls it in place of the strict empty-string assertion.
- [x] **Step 3.2 (fixes #7, #8, #15)** — Rewrite `_set_package_log_level` in `tests/e2e/agent_cli/test_stdout_is_clean_json.py` using `tomlkit` (already a project dep — see `init_cmd.py`'s usage). Pseudo:
  ```python
  import tomlkit
  doc = tomlkit.parse(pipelex_toml_path.read_text())
  doc["pipelex"]["log_config"]["package_log_levels"][package_name] = level
  pipelex_toml_path.write_text(tomlkit.dumps(doc))
  ```
  This eliminates all three line-based-rewriter edges (duplicate section, no-space matcher, no-trailing-newline) in one pass. Keep the `_set_pipelex_package_log_level_to_debug` compat shim so the original two callers don't change. **Done:** used the project's `load_toml_with_tomlkit` + `save_toml_to_path` helpers from `pipelex.tools.misc.toml_utils` (proper type stubs, same pair `init_cmd` uses) instead of raw tomlkit — pyright was unhappy with the raw `tomlkit.dumps` overload. Compat shim preserved.
- [x] **Step 3.3** — Sanity check: read the rewritten test file to confirm the section path `["pipelex"]["log_config"]["package_log_levels"]` exists in the kit's `pipelex.toml` (it does, line 177 — `[pipelex.log_config.package_log_levels]`). **Confirmed via grep on both `pipelex/pipelex.toml:98` and `pipelex/kit/configs/pipelex.toml:177`.**

### ✅ CHECKPOINT 3 — final verification

- [x] Run `make agent-check`. Must be clean. **Result:** 0 pyright errors, mypy success on 1893 files.
- [x] Run targeted: `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/cli/ tests/unit/pipelex/tools/ tests/integration/pipelex/cli/ tests/e2e/agent_cli/`. All pass. **Result:** 1541 passed, 1 skipped (pre-existing `test_toml_utils.py:61` skip — unrelated) in 33.33s.
- [x] Run `make tb`. Pass. **Result:** 2 passed, 6708 deselected in 6.13s.
- [x] Skim `git diff HEAD --stat` — the diff should now cover: `_agent_cli.py` (new silence wire), `agent_cli_factory.py` (sys.maxsize), `test_agent_cli_factory.py` (fixture), `test_agent_cli_factory_suppression.py` + `test_agent_cli_output_discipline.py` (per-logger restore), `test_stdout_is_clean_json.py` (relaxed assertion + tomlkit rewrite). **Note:** Phase 1 (commit `d98eb0e2`) and Phase 2 (commit `9563915f`) are already landed on the branch, so `git diff HEAD --stat` now shows only the Phase 3 file (`test_stdout_is_clean_json.py`) plus `TODOS.md`. The cumulative range vs `main`/release base covers every file listed.

---

## Skipped findings (recorded so a future session doesn't re-litigate)

The `/code-review` surfaced 15 findings; these 9 were explicitly skipped after triage:

- **#4 + #5 (warnings module / print_to_stderr leaks)** — Skipped. `logging.disable` doesn't cover these channels (`warnings.warn` → `sys.stderr.write` directly; `print_to_stderr` in `remote_config_fetcher.py:82/219/259`). Doctor path has no `catch_warnings` wrapper, so `GatewayOverrideWarning` (UserWarning subclass) could leak there. Decision: no real-world report; defer until someone hits it. Phase 3 Step 3.1's relaxed e2e assertion absorbs the noise.
- **#6 (process-global `logging.disable` leaks for in-process callers)** — Skipped. Documented one-shot CLI; embedded/in-process use isn't supported. Could add a docstring note but no functional change.
- **#10 (apply_agent_cli_output_discipline lost the `pipelex = OFF` backstop)** — Skipped. With `silence_logging_for_agent_cli` in `app_callback` (Phase 1), every path that calls `apply_agent_cli_output_discipline` also has silence armed. Restoring the backstop would be cargo-cult.
- **#14 (silence ordering in `agent_doctor_cmd`)** — Made moot by Phase 1. `app_callback` runs before any command body, so silence is armed before `set_agent_cli_error_format` runs in `agent_doctor_cmd`.

---

## End-to-end completion criteria

When all phases are checked off:

- [x] `git diff HEAD --stat` shows the expected files (see Checkpoint 3 list). **Cumulative diff across the 3 commits on this branch since `Release v0.30.1` (6902952c): `_agent_cli.py`, `agent_cli_factory.py`, `doctor_cmd.py`, `test_stdout_is_clean_json.py`, `test_agent_cli_factory.py`, `test_agent_cli_factory_init_overrides.py`, `test_agent_cli_factory_suppression.py`, `test_agent_cli_output_discipline.py`, `test_agent_doctor_cmd.py`, `TODOS.md`, `CHANGELOG.md`.**
- [x] All three e2e tests in `test_stdout_is_clean_json.py` pass. **Result:** 3 passed in 3.73s.
- [x] No regression in `make agent-test` (full suite — run before commit per CLAUDE.md release/commit conventions). **Result:** "All tests passed." — full suite clean.
- [x] Decide whether this work folds into the existing `release/v0.30.1` branch or warrants a follow-up release entry in CHANGELOG. **Decision (user-confirmed):** fold into the existing v0.30.1 CHANGELOG entry. v0.30.1 is not yet tagged (only v0.30.0 exists), so the entry was still safely editable. Appended a second `### Fixed` bullet covering the Phase 1-3 work (process-global `logging.disable(sys.maxsize)`, `app_callback` wiring, third-party-logger leak regression test) and bumped the v0.30.1 date from 2026-05-25 → 2026-05-26.
