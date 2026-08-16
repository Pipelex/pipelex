# Migrator Phase 3, part 2 — items deferred from the PR #1114 review

What the review-bot pass on [PR #1114](https://github.com/Pipelex/pipelex/pull/1114) surfaced and this branch did **not** fix, with why. Each was verified against the code before being parked; none is a live user-facing defect today. The confirmed important items — `changed_plans` blind to a partly-applied entry, the boot-tolerance warning logged before logging exists, the retry ignoring the schema-version floor, the diagnosis scanning the wrong directories under `--global`, and the doctor's unescaped Rich fields — were fixed on the branch.

## 1. The stale warning names `pipelex migrate` for a directory the command never walks

**Reporters:** Codex (`config_loader.py`, `_config_the_ledger_can_explain`), Cubic (`migration/run.py`, `config_directories_to_migrate`) — [thread](https://github.com/Pipelex/pipelex/pull/1114#discussion_r3792653243), [thread](https://github.com/Pipelex/pipelex/pull/1114#discussion_r3792679325).

An embedder's `Pipelex.make(config_dir=…)` outside `~/.pipelex/` and the project `.pipelex/` is read by boot tolerance (the retry replays exactly the files the loader merged) but not by `pipelex migrate`, whose walk is fixed to the two directories by design (`docs/migration-ledger.md` → "Where the ledgers are"). So a stale file there would boot with a warning whose closing sentence — "run `pipelex migrate` to bring the files up to date" — names a command that will not touch it, on every boot.

**Why deferred:** unreachable today. The `pipelex-config` ledger ships no entry, so its retry never fires; the telemetry loader takes no `config_dir`; the service configuration is loaded from the global directory, which is in the walk. It goes live with the first `pipelex-config` entry. The docs now say plainly that such a directory is the embedder's to update; the warning text does not yet.

**Recommendation:** when the first `pipelex-config` entry ships, have `stale_configuration_warning` take the walked directories and, for a stale file outside them, say "this file is outside `pipelex migrate`'s reach — update it where it lives" instead of naming the command. Do **not** add `pipelex migrate --config-dir`: `check_pending_migrations` deliberately takes no directory so the doctor row can never name a command that then rewrites a file it did not mention. This sits beside `migrator-write-scope-and-rename-fidelity.md`, which parks the sibling question of writing outside the walk.

## 2. What the presence of a `migration` block means when the plan is unexplained-only

**Reporter:** Cubic (`agent_output.py`, the `TelemetryConfigValidationError` hint) — [thread](https://github.com/Pipelex/pipelex/pull/1114#discussion_r3792679317).

`_pending_migration` attaches the block whenever any plan is not clean, and a plan carrying only `unexplained` paths is not clean. So a misspelled key in `telemetry.toml` — `extra="forbid"` refuses it, the diagnosis reports it as unexplained, the retry does not repair it — produces a `migration` block with `needs_attention: true` and empty `steps`. The agent hint then says "the configuration is out of date: run `migrate --dry-run`, then `migrate --yes`", and `--yes` writes nothing. The mechanism is correct; the wording over-claims.

**Why deferred:** the hint faithfully implements a documented contract — `docs/tools/cli/agent-cli.md` ("Its presence is the whole signal: the configuration is *out of date* rather than wrong") and `docs/migration-ledger.md` → "Reporting a stale configuration on a validation error" say the same — and `_migration_prose` ends the human message with the same unconditional "run `pipelex migrate`". Rewording the hint alone would leave the CLI and its spec disagreeing. This is one ruling over four surfaces: what "presence" means, or whether the block should carry (or the hint should point at) "is there anything the command would write" as distinct from "is there anything a person must look at". The `--dry-run` the hint sends the agent to does print the unexplained note ("either the name is a typo, or this file was written by a newer pipelex"), so the wasted round trip is the whole harm.

## 3. The service-configuration loader still warns directly, and two commands load it before logging exists

**Surfaced by:** the fix for Cubic's `runtime_hub.py` finding — [thread](https://github.com/Pipelex/pipelex/pull/1114#discussion_r3792679304).

The main configuration's warning is now parked on the loader and emitted after `log.configure` (the main configuration *is* the log configuration, so nothing else was possible). The telemetry and service loaders kept their direct `log.warning`, which is safe on every path that exists today for telemetry (loaded inside `setup()`) — but `load_pipelex_service_config_if_exists` is also called from `pipelex init` (`cli/commands/init/command.py`) and its warning would raise `LogConfig is not set` there once the `pipelex-service-config` ledger gains an entry. `pipelex plugins` calls `load_config_validated` without configuring logging and would now silently drop the parked warning rather than crash.

**Recommendation:** when either ledger gains an entry, a `StaleConfigurationWarning(UserWarning)` raised through `warnings.warn` on the `RemoteConfigStaleWarning` pattern (`pipelex_service/exceptions.py`, captured by the agent CLI factory) covers all three loaders and every entry point uniformly, at the cost of a second presentation channel. Not worth building against an empty ledger.

## 4. Pre-existing unescaped Rich fields in the doctor report

**Surfaced by:** Cubic's two escape findings on `doctor_cmd.py` — [thread](https://github.com/Pipelex/pipelex/pull/1114#discussion_r3792679312), [thread](https://github.com/Pipelex/pipelex/pull/1114#discussion_r3792679315).

The telemetry row and the pending-migrations row now escape what they print (this PR is what put user-file content into the telemetry message). `config_message`, `backends_message`, `models_message` and `deck_message` in `display_health_report` (and the Manual-Fixes block) still interpolate unescaped, and `config_message` embeds `report_validation_error(...).message` too. A bracketed path segment is silently dropped by Rich and a `[/x]` sequence raises `MarkupError`.

**Recommendation:** one pass over `display_health_report` escaping every dynamic field, with the recorded-console test pattern from `test_doctor_display_report.py`. Small, mechanical, and outside this PR's scope.
