# PR #1111 review — deferred items

Items surfaced while triaging the review threads on PR #1111 (configuration reshape, `pipelex-config@2`) that were deliberately **not** acted on. Each needs a decision rather than a drive-by fix.

## 1. `pipe_func_config.timeout_seconds` names a config address that does not exist

**Reporter:** found by the sweep, not by a bot.
**File:** `pipelex/pipe_operators/func/pipe_func_execution_transport.py:38`

The docstring reads:

> `timeout_seconds` is the PipeFunc kill-timeout that rides on the request. Callers pass the configured `pipe_func_config.timeout_seconds` (they live in plugins, outside core's import graph, so they can read the config without a cycle); it falls back to the module default otherwise.

`pipe_func_config` is a retired root, so on its face this belongs with the rest of the sweep. It was left alone because the mechanical correction would make things worse: core's `PipeFuncConfig` (`pipelex/system/configuration/pipe_func_config.py`) holds only `execution_mode`, and `[interpreter.pipe_func]` in `pipelex/pipelex.toml` holds only `execution_mode` too. There is no `timeout_seconds` anywhere in core. Rewriting the root to `interpreter.pipe_func.timeout_seconds` would assert a core address that does not exist, which is a worse failure than a stale one — a reader would go looking for a key they can never find.

The docstring itself says the callers "live in plugins, outside core's import graph", so the key is plugin-supplied.

**Open question:** does our Daytona plugin extend the `[interpreter.pipe_func]` table with its own `timeout_seconds`, or does it own a separate config root? If it extends the table, the fix is the mechanical one. If it owns a separate root, the sentence should name that root instead, or stop naming an address at all and just say the timeout is plugin-configured. Not answerable from open core.

**Thread:** none — this one was not reported; it surfaced from sweeping the class.

## 2. Should `reset_boot_state` also release the isolated-execution probe?

**Reporter:** greptile (P1), on `pipelex/runtime_hub.py:183-185`.
**Thread:** https://github.com/Pipelex/pipelex/pull/1111 — replied and resolved as a false positive.

Greptile claimed that a probe installed by a boot-orchestrator plugin survives teardown on the reusable runtime hub, so a later in-process boot routes usage events through the runner fallback instead of its registered event-log context, corrupting usage attribution. That specific failure cannot occur, for two independent reasons:

- The hub is not reused across boots. `RuntimeBoot.__init__` constructs a fresh `RuntimeHub()` and installs it (`pipelex/runtime_boot.py:184-185`), and every boot goes through construction, so a later boot always starts from the `_never_in_isolated_execution` default. The plugin registrar is rebuilt per boot too, so the slot claim is re-derived rather than inherited.
- In the one window that does exist — post-teardown, pre-next-boot, where `get_runtime_hub()` still hands out the dead hub — the probe's only production reader (`pipelex/reporting/reporting_manager.py:199`) first consults `_event_log_contexts`, which `ReportingManager.teardown()` clears. With no registered context the emission takes the runner fallback anyway, which is the same branch a stale probe would have forced.

**What is still open** is a hygiene question, not a bug. After the earlier follow-up commit ("Review follow-up: stale config paths, and boot-scoped state that outlived its boot"), `reset_boot_state` releases `_config`, `_is_dry_run_forced` and `_boot_orchestrator`, and its docstring says it releases "the process-global state a boot established". The probe is now the one boot-established hub attribute left out.

The argument for adding `self._isolated_execution_probe = _never_in_isolated_execution` is that consistency: a reader auditing the method should not have to re-derive why one attribute is absent.

The argument against is that the docstring's justification would stop being true. It says the flags are boot arguments that "`setup()` writes both unconditionally on the way up" — and that is precisely the difference. The probe is written *conditionally*, only when an orchestrator plugin claims the slot (`pipelex/runtime_boot.py:596-598`), and unlike `is_dry_run_forced()` and `get_boot_orchestrator()` it has no module-level accessor that outside code calls between boots. Adding the line means also rewriting the docstring to explain a release that guards against a hub-reuse pattern the code forbids.

**Decision needed:** add the line and generalise the docstring, or leave it out and add one sentence to the docstring saying explicitly why the probe is not in the list. Doing nothing leaves the asymmetry unexplained, which is the weakest of the three.

## 3. Nothing mechanically guards the "stale config path in a string" class

**Reporter:** none — an observation from doing this triage.

This one bug class has now produced three rounds of fixes on this single PR:

- the original reshape commit moved the keys;
- the first review round swept `plugins.disabled` → `runtime.plugins.disabled` and three exception docstrings;
- this round swept the `*_config` roots that the previous round left in the message bodies three lines below those same docstrings, plus roughly twice as many more sites across the plugin seam, the reporting and dry-run paths, the reasoning-controls doc page, and several test docstrings.

Every one of these is invisible to pyright, mypy, ruff and the whole test suite, because a config address inside a string literal, a comment or a Markdown sentence is just text. The migration ledger already knows, as data, every path that was retired and what it became (`pipelex/migration/ledgers/pipelex-config.toml` plus the `fingerprint@N` goldens). A check that greps source strings, comments and docs for a retired root and fails when one is named would therefore have the answer key already available — it would not need a hand-maintained list.

**Open question:** is that worth building? Points in favour: the ledger makes it nearly free to keep correct, it is exactly the kind of gate the repo already likes (`check-keyword-only`, `check-migration-schemas`, the drift contracts), and this class will recur on every future config reshape. Points against: it needs a real allowlist for the legitimate collisions — module filenames (`log_config.py`, `aws_config.py`, the per-provider `*_config.py`), genuine attributes (`deck.model_deck_config.is_model_fallback_enabled`), local variables that share the name (`storage_config = get_config().runtime.storage`), the migrator's own fixtures and goldens, and intentional historical prose in the changelog and the `# was [cogt]` markers. Get that allowlist wrong and the gate is noise.

Designing it is a decision, not a review fix, so it is recorded here rather than attempted.
