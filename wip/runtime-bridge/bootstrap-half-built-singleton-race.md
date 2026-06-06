# `ensure_pipelex_booted` can publish a half-built Pipelex singleton under concurrent first-boot

**Status:** ✅ **APPLIED** — Approach B (instance-level `is_ready`). Real P1 race in new code, now fixed: `ensure_pipelex_booted` gates on `Pipelex.is_fully_booted()`, and the singleton is published as ready only at the very end of `make()` (after `setup()` + the optional `validate_model_deck()`). See [As applied](#as-applied) below.
**Source:** PR #966 pre-landing review (`/review`), adversarial pass + source verification.
**Severity:** real, but **scoped**: only bites when two threads race the *first* boot from inside activities; the recommended "boot once at the worker entry-point" path never hits it. Fails with a loud `RuntimeError`, not silent corruption.
**Relation to the #959 "Boot race" fix:** this **extends** it. The double-checked `threading.Lock` added in #959 (`bootstrap.py`, see README §2) correctly serializes the two *writers* so the loser no longer raises `PipelexSetupError("already initialized")`. It does **not** close the second hole below: a *reader* taking the lock-free fast path while the winner is mid-`setup()`.

## The finding

`ensure_pipelex_booted` (`pipelex/runtime_bridge/bootstrap.py:34`) has a lock-free fast path:

```python
if Pipelex.get_optional_instance() is not None:   # line 34 — no lock
    return
with _boot_lock:
    if Pipelex.get_optional_instance() is None:
        Pipelex.make(config_overrides=config_overrides)
```

The premise that makes this unsafe is that **the singleton becomes publicly visible before it is configured**:

1. `MetaSingleton.__call__` registers the instance the moment `__init__` returns:
   - `pipelex/system/registries/singleton.py:17` — `cls.instances[cls] = super().__call__(*args, **kwargs)`
2. `Pipelex.make()` constructs **then** runs the slow `setup()`:
   - `pipelex/pipelex.py:577` — `pipelex_instance = cls(config_overrides=config_overrides)`  (registers now; `__init__:107` even swaps in a fresh **empty** hub via `set_pipelex_hub`)
   - `pipelex/pipelex.py:579` — `pipelex_instance.setup(...)`  (this is what assigns the library manager, class registry, pipe router, pipeline manager — slow: loads libraries, validates the model deck)
3. `get_optional_instance()` reads exactly that registry:
   - `pipelex/pipelex.py:611` — `return MetaSingleton.instances.get(cls)`

**Chain:** Thread A holds `_boot_lock` and is inside `make()`, past line 577 (instance registered, empty hub installed) but still inside `setup()`. Thread B arrives fresh, hits the lock-free check at `bootstrap.py:34`, sees a non-`None` instance, returns immediately, and proceeds into `run_pipe_via_bridge` → `get_required_pipe()` / `get_library_manager()` against the still-empty hub → `RuntimeError` ("LibraryManager is not initialized" or similar partial-state failure).

There is a second nasty interleaving: `make()` wraps `setup()` in `try/except BaseException` that **deletes** the instance on setup failure (`pipelex.py:601-605`). If A's `setup()` fails, B — which already returned thinking boot succeeded — is now running against an instance A just removed from the registry.

## Why this is the multi-thread scenario the module targets

`bootstrap.py:18-20` already calls out "Temporal's sync-activity thread pool / multi-thread workers" as the reason for the lock. The bridge is built for embedding (`pipelex-mistralai-workflows` calls `run_pipe_via_bridge` directly from inside an activity, with `ensure_pipelex_booted` as the documented in-activity first-boot). So concurrent first-boot across worker threads is a supported path, not a corner case — the lock proves the author intended it to be safe.

The window is wide: `setup()` does real work (library load + model-deck validation), so it is realistically open for hundreds of ms on a cold worker.

## Why the existing test does not catch it

`tests/unit/pipelex/runtime_bridge/test_bootstrap_concurrency.py::test_concurrent_first_calls_boot_once_without_error` starts both worker threads at the same `threading.Barrier`, so both miss the fast path (no instance yet) and both queue on `_boot_lock`. The test asserts `make_calls == 1` and no raise — it verifies the *writers* are serialized. It never has a thread arrive **fresh during another thread's `setup()` window**, which is the only way to exercise the lock-free read of a half-built instance. The `fake_make` also conflates registration and setup (it appends to `instance_holder` then `time.sleep`), but the timing never lets a third party observe the in-between state.

## Recommended fix

> **Note:** the shape sketched here (a module-global `_booted`) is **not** what shipped — see [As applied](#as-applied). The applied fix is the `is_ready`-on-instance alternative called out in the caveat, chosen against the test lifecycle. This section is kept as the record of the original sketch and its trade-off.

Gate the fast path on a "fully booted" flag flipped **only after** `make()` returns, and move the existence check inside the lock so the lock-free path can never read a half-built instance:

```python
_booted = False

def ensure_pipelex_booted(config_overrides: dict[str, Any] | None = None) -> None:
    global _booted
    if _booted:
        return
    with _boot_lock:
        if _booted:
            return
        if Pipelex.get_optional_instance() is None:
            Pipelex.make(config_overrides=config_overrides)
        _booted = True
```

This preserves the documented "adopt an externally-created singleton" contract: the first bridge call finds `_booted == False`, takes the lock, sees a fully-built external instance, skips `make()`, and sets `_booted = True`. The one requirement (already implicit today) is that any external boot must *complete* before the first bridge call — adopting a singleton another thread is mid-`make()`-ing externally is inherently racy and out of scope.

### Caveat that makes this worth a deliberate decision, not a reflex fix

`_booted` is module-global, so it survives across tests. The existing concurrency test (and any test that boots/tears down Pipelex) needs a reset hook (e.g. a fixture that sets `bootstrap._booted = False`), or the flag has to live somewhere resettable. A "check the instance is fully set up" alternative (an `is_ready` flag on `Pipelex` flipped at the end of `setup()`) avoids the module global but is more invasive (touches `pipelex.py`). Pick the shape against the boot/teardown lifecycle the test suite expects — hence deferred rather than auto-applied in the review pass.

## As applied

Shipped the `is_ready`-on-`Pipelex` alternative from the caveat, **not** the module-global `_booted` sketch above. The deciding factor is exactly the test-lifecycle point the caveat raised: the suite's module-scoped autouse fixture (`tests/conftest.py`) tears Pipelex down with `Pipelex.teardown_if_needed()`, which deletes the singleton from `MetaSingleton.instances`. An instance-level flag dies with the instance, so it auto-resets between test modules — no module-global to leak, no reset fixture to add, no second source of truth that can drift from the registry.

Changes:

- `pipelex/pipelex.py` — `__init__` initializes `self.is_ready = False` (set before the metaclass registers the instance, so it always exists before the instance is observable); `make()` flips `pipelex_instance.is_ready = True` on its success tail, **after** the `try/except`, so it is set only once `setup()` and the optional `validate_model_deck()` have both succeeded and the delete-on-failure handler is behind us; new classmethod `is_fully_booted()` returns `instance is not None and instance.is_ready`.
- `pipelex/runtime_bridge/bootstrap.py` — `ensure_pipelex_booted` gates both the lock-free fast path and the in-lock re-check on `Pipelex.is_fully_booted()` instead of `get_optional_instance() is not None`. A registered-but-not-ready instance (mid-`setup()`, or about to be deleted on setup failure) is now treated as not-booted, so the reader blocks on the lock and re-checks. The "adopt an externally-created singleton" contract is preserved: a fully-booted external instance is `is_ready` → no-op.

## Tests (done)

`tests/unit/pipelex/runtime_bridge/test_bootstrap_concurrency.py` (all mock at the `Pipelex` classmethod boundary — never touching `MetaSingleton.instances`, so they coexist with the autouse session singleton):

- `test_reader_arriving_mid_setup_blocks_until_ready` — three-thread test: A is held inside a patched `make()` that registers an `is_ready=False` instance, then flips it ready only just before returning; B and C arrive during the window and must block on the lock until A finishes (asserted via `is_alive()` mid-window). Fails against the pre-fix bare-presence check.
- `test_setup_failure_lets_next_thread_reboot` — A's patched `make()` registers then clears + raises (mirroring delete-on-failure); B must fall through to the lock, find nothing booted, and re-boot rather than proceed against the deleted instance.
- The original `test_concurrent_first_calls_boot_once_without_error` keeps the `make_calls == 1` assertion (no regression of the #959 write-write fix).

## Related

- README §2 "Boot race — ✅ applied" (the #959 double-checked lock this extends).
- `pipelex/system/registries/singleton.py` (`MetaSingleton` — registration-at-construction).
- `pipelex/pipelex.py:577-607` (`make` construct-then-setup, with delete-on-failure).
