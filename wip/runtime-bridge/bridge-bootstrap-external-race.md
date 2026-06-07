# Bridge bootstrap vs a concurrent external Pipelex.make() — narrow, documented, deferred

**Status:** ✅ RESOLVED for the reachable/standard cases (lock-serialized, tested). The residual race against a *concurrent external* boot is narrow/non-standard; the docstring now states the real contract, and the bounded-wait fix is recorded below as deferred (adding it now would be over-engineering for a config standard hosts don't produce).

**Raised by:** PR #969 round-6 review — cubic-dev-ai **P2** (confidence 8), `pipelex/runtime_bridge/bootstrap.py:39`: "`ensure_pipelex_booted()` can raise `Pipelex is already initialized` during concurrent startup when another thread is already mid-boot, instead of safely adopting/waiting for that boot."

## What's actually true

`ensure_pipelex_booted()` is:
```python
if Pipelex.is_fully_booted():
    return
with _boot_lock:
    if not Pipelex.is_fully_booted():
        Pipelex.make(config_overrides=config_overrides)
```
`Pipelex.make()` raises `PipelexSetupError("Pipelex is already initialized")` if any instance is already registered (pipelex.py). `is_fully_booted()` is `instance is not None and instance.is_ready`; `is_ready` flips True only at the tail of `make()` (after setup + optional deck validation; a failed boot deletes the instance).

**Reachable cases are safe** — verified against the three tests in `tests/unit/pipelex/runtime_bridge/test_bootstrap_concurrency.py`:

- *Two `ensure_pipelex_booted` threads.* `make()` runs **inside** `with _boot_lock`, so thread A holds the lock for its entire boot. Thread B blocks on the lock and, when it finally enters, sees `is_fully_booted()==True` and skips. No second `make()`, no raise. (`test_concurrent_first_calls_boot_once_without_error`)
- *Reader arriving mid-setup.* B/C gate on `is_fully_booted()` (not bare presence), so they block on the lock through A's half-built window and never read a not-ready instance. (`test_reader_arriving_mid_setup_blocks_until_ready`)
- *Setup failure.* A registers half-built, fails, deletes the instance; B (held on the lock) then re-boots cleanly. (`test_setup_failure_lets_next_thread_reboot`)

The cubic write-up's two-`ensure_pipelex_booted`-threads scenario is **not** a real race: it assumes B can run `make()` while A is mid-`make()`, but the lock makes that impossible.

## The genuine residual (scenario B)

The lock only serializes the bridge's *own* callers. A **separate external** `Pipelex.make()` (e.g. `worker_cli.py`, `codec_server_cli.py`, a CLI factory) does **not** take `_boot_lock`. If such an external boot is mid-setup (`is_ready=False`) on one thread while the bridge's `ensure_pipelex_booted()` runs on another, the bridge sees `is_fully_booted()==False`, acquires the (uncontended) lock, calls `make()`, and hits "already initialized".

**Reachability: narrow.** Each external `make()` call site is a process entry point that boots Pipelex *before* serving work; activities (which reach the bridge) run after boot, when `is_fully_booted()` is already True and the bridge fast-paths. Hitting scenario B requires a non-standard host that boots Pipelex on one thread while *concurrently* serving bridge traffic on another. No code in the repo does this.

## Decision: document the contract, defer the bounded-wait

The docstring previously over-promised ("adopts that singleton without re-initializing") without qualifying the mid-boot window. It now states the real contract: the bridge serializes its own boot and adopts a *fully-booted* external singleton; it does **not** support racing a concurrent external `make()` that is mid-initialization — boot Pipelex before bringing up concurrent bridge callers. No code change: the failure mode is a loud raise (not a silent corruption) in a setup nothing standard produces.

## Deferred: bounded-wait adoption

If a real host ever needs to boot Pipelex concurrently with serving bridge traffic, make `ensure_pipelex_booted()` wait out a mid-flight external boot instead of colliding. Because a failed boot deletes the instance, the wait terminates:

```python
with _boot_lock:
    while not Pipelex.is_fully_booted():
        if Pipelex.get_optional_instance() is None:
            Pipelex.make(config_overrides=config_overrides)   # still needs to tolerate a TOCTOU raise vs external
        else:
            time.sleep(...)   # external boot mid-setup: wait for is_ready, or for it to fail+disappear
```

This adds a poll loop, holds `_boot_lock` while waiting (acceptable — other bridge callers would block anyway), and must also catch the `make()` "already initialized" raise for the external-registers-between-check-and-make TOCTOU. That fragility for a non-occurring setup is why it's deferred, not done.
