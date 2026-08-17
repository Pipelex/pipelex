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

**Resolved at S7.** The open question was answered by reading the plugin: our Daytona plugin owns a separate root, `daytona.toml` → `pipe_func_timeout_seconds` on `config_daytona.py`, and does **not** extend `[interpreter.pipe_func]`, which still holds `execution_mode` and nothing else. So the mechanical correction would indeed have asserted an address no reader could find. The docstring now says the timeout is plugin-configured, names our Daytona plugin's key as one instance rather than as the contract, and stops naming a core address altogether.

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

**Resolved at S7 — the line was added, and the docstring says why.** Half of the argument against did not survive checking: the probe **does** have a module-level accessor that outside code calls, `is_in_isolated_execution`, and `ReportingManager` is what reads it. What is left of the argument — that the probe is written *conditionally*, only when a plugin claims `HubSlot.ISOLATED_EXECUTION_PROBE` in `RuntimeBoot.setup` — turns out to argue the other way: a boot that claims nothing *inherits* rather than overwrites, so the release is what a fresh `RuntimeHub` per boot would otherwise be the only thing providing. The docstring now records both, and a second test in `tests/unit/pipelex/test_runtime_boot_releases_boot_scoped_state.py` pins the release. The greptile finding itself stays a false positive: the failure it described still cannot happen, for the two reasons above.

## 3. Nothing mechanically guards the "stale config path in a string" class

**Reporter:** none — an observation from doing this triage.

This one bug class has now produced three rounds of fixes on this single PR:

- the original reshape commit moved the keys;
- the first review round swept `plugins.disabled` → `runtime.plugins.disabled` and three exception docstrings;
- this round swept the `*_config` roots that the previous round left in the message bodies three lines below those same docstrings, plus roughly twice as many more sites across the plugin seam, the reporting and dry-run paths, the reasoning-controls doc page, and several test docstrings.

Every one of these is invisible to pyright, mypy, ruff and the whole test suite, because a config address inside a string literal, a comment or a Markdown sentence is just text. The migration ledger already knows, as data, every path that was retired and what it became (`pipelex/migration/ledgers/pipelex-config.toml` plus the `fingerprint@N` goldens). A check that greps source strings, comments and docs for a retired root and fails when one is named would therefore have the answer key already available — it would not need a hand-maintained list.

**Open question:** is that worth building? Points in favour: the ledger makes it nearly free to keep correct, it is exactly the kind of gate the repo already likes (`check-keyword-only`, `check-migration-schemas`, the drift contracts), and this class will recur on every future config reshape. Points against: it needs a real allowlist for the legitimate collisions — module filenames (`log_config.py`, `aws_config.py`, the per-provider `*_config.py`), genuine attributes (`deck.model_deck_config.is_model_fallback_enabled`), local variables that share the name (`storage_config = get_config().runtime.storage`), the migrator's own fixtures and goldens, and intentional historical prose in the changelog and the `# was [cogt]` markers. Get that allowlist wrong and the gate is noise.

**A fourth review round supplied the first measured false positive of the manual sweep, which is direct evidence for the allowlist half of that question.** The sweep had rewritten a sentence in `pipelex/system/data_inclusion_config.py` that names the graph rendering *module* names `mermaid_config` / `reactflow_config` — modules `pipelex/graph/graph_config.py` still imports and that the reshape never touched — into the field names `mermaid` / `reactflow`. The tell was that the identical sentence in `docs/contribute/hub-layering.md` had been swept correctly, so source and docs had silently diverged. Reverted in that round. A mechanical gate would have flagged the same sentence, so the module-filename allowlist entry is not hypothetical: it is required on day one, and it has to cover a module name appearing in prose, not just an import statement.

Designing it is a decision, not a review fix, so it is recorded here rather than attempted.

## 4. Our Temporal plugin reads `boot_orchestrator` from a field that no longer exists

**Reporter:** found by the fourth review round while checking what depends on the demoted field.
**File:** `pipelex-server/temporal/pipelex_temporal/temporal_activation.py:19` (sibling repo, not this one).

`boot_orchestrator` stopped being a config field and became a boot argument plus boot-scoped hub state. That site still reads `get_config().plugins.boot_orchestrator`.

**This is the one downstream site in the whole cross-repo sweep whose fix is not a path rename**, and it is worth calling out because a mechanical `plugins.` → `runtime.plugins.` pass produces the wrong answer here. The field was deleted, not moved; the correct fix is `from pipelex.runtime_hub import get_boot_orchestrator` and calling it. Every other downstream hit found so far — `content_generator_in_workflow.py`, `act_pipe_func.py`, the tracing tests, the `pipelex-api` / cookbook / cocode TOMLs, `pipelex-mistral-workflows` — is a straight rename.

The one piece of good news is that it fails loudly rather than silently: `plugins` is not a root field on `PipelexConfig` any more, so the read raises `AttributeError` at import-activation time instead of quietly returning a default.

**Action:** this belongs in the release-gated cross-repo sweep, flagged as manual. There is now an in-repo test pinning the write end of that seam (`tests/integration/pipelex/system/test_boot_orchestrator_validation.py` asserts `get_boot_orchestrator()` returns the accepted name), so the reader has something to trust.

## 5. A backend TOML matches the `pipelex-config` tier glob and is claimed by nothing

**Reporter:** found by the fourth review round while checking surface claiming.
**File:** `.pipelex/inference/backends/pipelex_gateway.toml`.

It matches the `pipelex-config` surface's tier glob `pipelex_*.toml`, but it is a backend definition, not a config root. `pipelex_service.toml` is safe from the same glob for a reason that does not apply here — filenames claim before globs, and it is a `base_file` for its own surface — whereas nothing claims this one first.

Nothing on this branch is affected: `files_by_surface_in_directory` does not exist here, so no directory walk consults the glob yet.

**Action:** this is a concrete, named specimen for S6's `pipelex migrate` directory walk. Whatever S6 builds for the walk should be tested against this exact file rather than a synthetic one.

## 6. `introduced_in` is a forward-written version with no validator behind it

**Reporter:** found by the fourth review round.
**File:** `pipelex/migration/ledgers/pipelex-config.toml`.

The `pipelex-config@2` entry declares `introduced_in = "0.46.0"` while `pyproject.toml` is on `0.45.0`. That is deliberate — the entry ships in a future release — and it is consistent with the changelog's forward-written `pipelex migrate` line, which Louis already ruled to keep.

The point worth recording is that **nothing checks it**. `ledger.py:79` types `introduced_in` as a bare `str`, so any value parses, and no gate compares it to the package version at any point.

**Action:** re-check this at release time. If the release lands on a number other than `0.46.0`, the field is silently wrong. A cheap release-time assertion (the head entry's `introduced_in` must equal the version being cut, or be unreleased) would close it permanently, but that is a decision for the release session, not this PR.

## 7. The committed error pages under `docs/errors/` are gated by nothing

**Reporter:** found by the fourth review round — `docs/errors/core-unconditional-plugin-disabled-error.md` had shipped stale.

The commit "Review follow-up: the rest of the retired config roots, in strings and prose" added double-backticks to the `CoreUnconditionalPluginDisabledError` docstring. The generated page kept the un-backticked sentence, through three review rounds and a green full suite.

Nothing catches it, and the two halves of the generated-error-docs system are gated asymmetrically:

- the identity snapshot (`tests/data/errors/error_identity.txt`, `make gei`) has a real gate — `tests/unit/pipelex/errors/test_error_identity_snapshot.py` compares the committed file to a fresh generation and fails on drift;
- the pages (`docs/errors/`, `make gep`) have none. Every test in `tests/unit/pipelex/errors/test_error_pages_generator.py` writes to `tmp_path`, and `make docs-check` *runs* the generator as a build dependency — so it rewrites the pages in the working tree, builds green, and never compares them against what is committed.

The consequence is broader than a forgotten new class: **editing the docstring of an existing error class silently leaves its committed page stale**, and no gate anywhere — lint, full test suite, or CI — will say so. The page was regenerated in the fourth round, but the gap remains.

**Open question:** add a snapshot-style test for the pages, mirroring the identity snapshot (generate to a temp dir, compare against `docs/errors/`, fail on drift)? The complication is the `<!-- pipelex:authored -->` marker: pages a maintainer has claimed are preserved across runs, so the comparison has to skip them, and the test would need to encode that rule rather than compare the directory wholesale.
