# Boot-split test-coverage gaps left open deliberately

**Status:** deferred. Found by a test-quality review pass on PR #1073, which confirmed no new test on that branch passes vacuously. These are the gaps it found *around* the new tests. Each is a coverage tradeoff rather than a defect, so each is recorded rather than patched — the two that were cheap and pinned a documented unrecoverable invariant (the same-class exclusivity guard, and `Pipelex.teardown_if_needed()` against a bare `RuntimeBoot`) were fixed on the branch instead.

## 1. The `try`/`finally` in `_release_after_failed_boot` is only distinguishable under `BaseException`

`_teardown_plugin_callbacks` swallows every ordinary `Exception` per callback, so wrapping the call in `try`/`finally` differs from a bare sequence *only* when a `BaseException` passes through — and its 16-line justification says exactly that ("must run even on a `KeyboardInterrupt` mid-teardown"). No test raises one, so deleting the `try`/`finally` keeps the suite green.

Not fixed because the test would be pinning Python's `finally` semantics against a hand-raised `KeyboardInterrupt` from a plugin callback: contrived enough that the next reader would reasonably question why it exists. The rationale comment is the actual defence here. Worth adding if the failed-boot path ever grows a step that can raise ordinarily.

## 2. The booted-runtime closure subprocess runs outside the test harness

`tests/unit/pipelex/test_runtime_boot_closure.py` boots in a fresh interpreter via `subprocess.run`, and `RunMode` is set by an in-process session fixture rather than an env var. Measured inside the subprocess: `run_mode=normal`, `is_unit_testing=False`. Consequences:

- `tests/pipelex_unit_test.toml` is **not** layered.
- The developer's real global and project `.pipelex/` configs **are** (cwd is inherited).
- `ensure_global_config_exists()` runs — a filesystem write to `~/.pipelex` from a unit test.

So the verdict depends on the machine's config: a `.pipelex/pipelex.toml` enabling an external plugin that pulls an interpreter package would produce a spurious failure.

Not fixed with the obvious one-liner (`env={**os.environ, "RUN_MODE": "unit_test"}`) because it cuts the other way too: the unit-test config layer may disable plugin groups, which would *weaken* the sweep it is meant to strengthen. Deciding which config a hermetic boot-closure test should run against — and whether the answer is a purpose-built minimal config dir rather than either existing one — is a decision worth making deliberately. Note that the sibling import-closure test does not have this problem, because it only imports.

## 3. Untested new public surfaces

- `RuntimeBoot.make(needs_inference=True)` — every call site passes `False`, so `validate_model_deck()` on the runtime-only path has no coverage.
- `Pipelex.make(config_dir=...)` — `config_dir` is tested through `RuntimeBoot.make` only, though the parameter is documented at length on both.
- The two `| None` narrowing guards in `Pipelex.setup` (plugin registrar, class registry). These are unreachable by construction — `super().setup()` assigns both unconditionally and any earlier failure propagates — and exist to satisfy the declarations. Testing an unreachable branch is not worth it; the note is here so nobody mistakes the absence for an oversight.

## 4. Teardown *phase order* is asserted nowhere

`Pipelex.teardown` sequences plugin callbacks → pipeline manager → runtime, and the comment calls the order load-bearing (a worker's in-flight resources must release before the pipeline manager drops the pipelines they may still be reporting on). `test_teardown_callbacks_run_lifo` pins LIFO *among* callbacks only. Replacing the three explicit lines with `self.pipeline_manager.teardown(); super().teardown()` reads cleaner, inverts the documented order, and passes everything.

A test would need an ordering probe across all three phases — a plugin callback, an injected pipeline manager, and a runtime-teardown observer appending to one list. Worth doing when the Temporal worker's teardown path is next touched, since that is the integration the order exists for.
