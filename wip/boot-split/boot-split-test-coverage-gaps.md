# Boot-split test-coverage gaps left open deliberately

**Status:** deferred. Found by a test-quality review pass on PR #1073, which confirmed no new test on that branch passes vacuously. These are the gaps it found *around* the new tests. Each is a coverage tradeoff rather than a defect, so each is recorded rather than patched — the two that were cheap and pinned a documented unrecoverable invariant (the same-class exclusivity guard, and `Pipelex.teardown_if_needed()` against a bare `RuntimeBoot`) were fixed on the branch instead.

## 1. The `try`/`finally` around `_teardown_plugin_callbacks` is only distinguishable under `BaseException`

`_teardown_plugin_callbacks` swallows every ordinary `Exception` per callback, so wrapping the call in `try`/`finally` differs from a bare sequence *only* when a `BaseException` passes through — and the 16-line justification on the failed-boot path says exactly that ("must run even on a `KeyboardInterrupt` mid-teardown"). No test raises one, so deleting the `try`/`finally` keeps the suite green.

This now covers **three** sites, not one: `_release_after_failed_boot`, `RuntimeBoot.teardown` and `Pipelex.teardown` all wrap the call, the latter two added by the pre-landing review that found the sibling gap. Three unpinned copies of one argument is a stronger case for a test than one was.

Still not fixed, for the same reason: the test would be pinning Python's `finally` semantics against a hand-raised `KeyboardInterrupt` from a plugin callback, contrived enough that the next reader would reasonably question why it exists. The rationale comments are the actual defence. Worth adding if any of the three paths ever grows a leading step that can raise ordinarily — at which point the test stops being contrived.

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

## 5. The `MetaSingleton.get_subclass_instance` copy-fix is unpinned

`pipelex/system/registries/singleton.py` changed `for subclass, instance in cls.instances.items()` to iterate `list(cls.instances.items())`, justified by a four-line comment: `instances` is a process-global dict that grows at run time (`GraphTracerManager` registers itself during a pipeline run) and this lookup sits on the boot hot path `ensure_pipelex_booted` reaches from concurrent threads.

Reverting the `list(...)` leaves the whole suite green. The two concurrency tests in the tree — `tests/unit/pipelex/runtime_bridge/test_bootstrap_concurrency.py` — patch `Pipelex.get_optional_instance` and `Pipelex.make` out entirely, so they never reach the metaclass.

Not fixed because a deterministic test needs a `base_cls` whose `__instancecheck__` or `__subclasshook__` inserts a key into `MetaSingleton.instances` mid-scan, plus a `finally` restoring the process-global dict. That is a test about CPython's dict-mutation semantics wearing a Pipelex costume, and the copy is a one-word defensive change with no downside. The honest position is that this is defence-in-depth rather than a pinned invariant; if it is ever removed as "unused", nothing will notice.

## 6. `config_dir` is pinned as "reaches the loader", not as "bypasses layering"

`tests/unit/pipelex/test_runtime_boot_config_dir.py` writes one overridden leaf into a temp dir and asserts it landed. That passes identically if `config_dir` were merely an *extra highest-priority layer* rather than a replacement for project/global layering — which is the half the docstrings actually promise.

Two reasons it is left alone. First, the assertion belongs at `ConfigLoader.load_config`, not at the boot: it is a property of the layer list, and asserting absence at boot level needs a leaf that differs between `pipelex/pipelex.toml` and the project `.pipelex/pipelex.toml`, of which there is currently none committed. Second, the bypass is genuinely *not* total under pytest — `load_config` appends `tests/pipelex_{run_mode}.toml` on both branches — so a boot-level test would be pinning a statement that is true in production and false in the harness running it.

## 7. `test_gateway_terms_check.py` stubs a `RemoteConfigSource` as a bare string

`test_needs_inference_false_does_not_raise_when_terms_not_accepted` sets `mock_result.source = "fresh"` where the contract is a `RemoteConfigSource` (the session conftest uses the real enum). `setup()` therefore dies at `gateway_config_source.is_cached` with an `AttributeError` about ten lines past the gate the test exists for, and the trailing `except Exception: pass` swallows it.

The test still does what its name says — the gate is reached and does not raise — but the swallow is wide enough that it cannot distinguish "gate skipped correctly" from "gate never reached", so a future reordering that moves an unrelated failure ahead of the gate would leave it green and blind. It also calls `setup()` on a `Pipelex.__new__(Pipelex)` with no `__init__`, which is what keeps the damage contained.

Pre-existing (this branch only renamed the module constant it patches), and left alone because the one-line stub fix moves the swallowed `AttributeError` from one unasserted line to another without adding coverage. The real fix is to assert the specific expected failure instead of swallowing, which is a rewrite of the test's contract.
