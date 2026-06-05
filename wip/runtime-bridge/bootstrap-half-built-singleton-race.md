# `ensure_pipelex_booted` can publish a half-built Pipelex singleton under concurrent first-boot

**Status:** ⏸️ **DEFERRED by decision** (PR #966 review). Real P1 race in new code; ships as-is for now because the recommended boot path is unaffected and it fails loud, not silent.
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

## Test ideas (when fixed)

- Three-thread test: A wins the lock and is held inside a patched `make()` whose "setup" sleeps **after** the singleton is registered; B and C arrive during that window and must NOT return until A finishes — assert neither observed a half-built hub (e.g. patch `get_required_pipe`/`get_library_manager` to record whether they were called before setup completed).
- Setup-failure interleaving: A's patched `make()` registers then raises; assert B does not silently proceed against a deleted instance (it should re-boot under the lock).
- Keep the existing `make_calls == 1` assertion (no regression of the #959 write-write fix).

## Related

- README §2 "Boot race — ✅ applied" (the #959 double-checked lock this extends).
- `pipelex/system/registries/singleton.py` (`MetaSingleton` — registration-at-construction).
- `pipelex/pipelex.py:577-607` (`make` construct-then-setup, with delete-on-failure).
