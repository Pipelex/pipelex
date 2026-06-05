# DIRECT mode: nested controller sub-pipes leak to the hub default router

**Status:** confirmed bug, **deferred pending decision — do not fix yet.**
**Source:** PR #959 review — greptile-apps (P1, `bridge.py:252-258`); the enabler is cubic-dev-ai (P2, `hub.py:615`, "prefer a `scoped_pipe_router` context manager").
**Severity:** real but **latent** — only bites when a worker runs with `[temporal] is_enabled = true`, and Temporal hasn't shipped to prod. In the common (non-Temporal) worker it's silently harmless today *except* for an observer inconsistency (see the fork).

## The finding

> `DIRECT` mode creates a fresh `PipeRouter`, so only the root pipe uses the bridge-local direct runner. Controller pipes dispatch their sub-pipes through `get_pipe_router()`, which resolves to the hub or context router. In a worker booted with Temporal enabled, a direct bridge run of a sequence or batch can unexpectedly send nested pipes to Temporal instead of running in-process.

## Verified behavior (code trace)

1. `_run_direct` builds a **bare** router and hands it only to `PipeRun`:
   - `pipelex/runtime_bridge/bridge.py:256` — `pipe_run = PipeRun(pipe_router=PipeRouter())`
2. `PipeRun.run` uses that router **only for the root pipe**, and never installs it into the routing ContextVar:
   - `pipelex/pipe_run/pipe_run.py:42` — `pipe_output = await self._pipe_router.run(pipe_job)`
3. Controllers dispatch every sub-pipe via `get_pipe_router()` — *not* the parent's router instance:
   - `pipelex/pipe_controllers/sub_pipe.py:179` (batch), `:195` (condition), `:229` (normal) — all `await get_pipe_router().run(...)`
4. `get_pipe_router()` returns the ContextVar override if set, else the **hub default**:
   - `pipelex/hub.py:633-637`
   ```python
   def get_pipe_router() -> "PipeRouterProtocol":
       override = _current_pipe_router.get()
       if override is not None:
           return override
       return get_pipelex_hub().get_required_pipe_router()
   ```
5. The hub default is **Temporal-aware** when Temporal is enabled:
   - `pipelex/pipelex.py:446-452`
   ```python
   if pipe_router:
       self.pipelex_hub.set_pipe_router(pipe_router)
   elif get_config().temporal.is_enabled:
       self.pipelex_hub.set_pipe_router(make_temporal_pipe_router())   # TemporalPipeRouter
   else:
       self.pipelex_hub.set_pipe_router(PipeRouter(observer=multi_observer))
   ```

**Chain:** `_run_direct` never sets `_current_pipe_router` → nested `get_pipe_router()` sees no override → returns the hub default → which is `TemporalPipeRouter` in a Temporal-enabled worker → **nested sub-pipes of a DIRECT-mode sequence/batch get dispatched to Temporal**, contradicting the whole point of DIRECT (run in-process, here, now).

This is not intentional: `set_pipe_router`'s own docstring (`pipelex/hub.py:618-619`) describes exactly this use case — *"Used by host runtimes that want controllers to dispatch sub-pipes through their own router."* DIRECT mode simply forgets to use it.

The greptile comment also notes a Mistral-native variant of the same root cause: a `set_pipe_router` override installed by a host is honored by nested pipes (via `get_pipe_router()`) but bypassed by the root pipe (which runs on the bare `PipeRouter()`), so root vs nested dispatch is inconsistent.

## Provenance — new in #959, not pre-existing in dev

Checked against `dev` (`../pipelex`, HEAD `fa15d15c` — the commit this branch was cut from, no `runtime_bridge/`). **This bug is introduced by the bridge PR.** Both ingredients are new:

- dev's `get_pipe_router()` (hub.py:612-613) has **no override layer** — it just `return get_pipelex_hub().get_required_pipe_router()`. The PR added `_current_pipe_router` + the module-level `set_pipe_router`/`teardown_current_pipe_router`.
- dev never builds a fresh bare router for a root run: the hub's `PipeRun` uses the *hub's* router (`pipelex.py:461` — `PipeRun(pipe_router=self.pipelex_hub.get_required_pipe_router())`), and nested sub-pipes resolve the *same* hub router. So in dev root and nested always agree — non-Temporal → both `PipeRouter(observer=multi_observer)` (no observer split either); Temporal-enabled → both the Temporal router. There is no "in-process root while Temporal is enabled" concept in dev.

The bridge introduces that concept (`DIRECT` = force in-process even in a Temporal worker) via the bare `PipeRouter()` in `_run_direct`, but doesn't install it into the new ContextVar — hence the leak. The **observer split** is likewise bridge-introduced.

Pre-existing look-alike (out of scope, flagged for honesty, not #1): `pipelex/pipeline/bundle_validator.py:106` builds `PipeRun(pipe_router=PipeRouter(observer=ObserverNoOp()))` — same "fresh root router, nested falls to `get_pipe_router()`" shape, but it's the validation/dry-run path, predates the bridge, and is low-risk. Worth its own look someday, separately.

## The mechanism for the fix (resolves cubic's hub.py:615 too)

There's an established pattern in the same file — `scoped_current_library` (`pipelex/hub.py:517-532`) — a context manager that captures the prior ContextVar value, sets the new one, and restores on exit:

```python
@contextmanager
def scoped_current_library(library_id: str) -> Generator[None, None, None]:
    prev = _library_id.get()
    _library_id.set(library_id)
    try:
        yield
    finally:
        _library_id.set(prev)
```

The router ContextVar has only the raw pair today, and the teardown clobbers any outer override:

- `pipelex/hub.py:615` `set_pipe_router(router)` → `_current_pipe_router.set(router)`
- `pipelex/hub.py:628-630` `teardown_current_pipe_router()` → `_current_pipe_router.set(None)` (unconditional — **does not restore a prior override**, cubic's P2)

**Proposed shared fix:** add `scoped_pipe_router(router)` mirroring `scoped_current_library`, then wrap the DIRECT run in it so the in-process router is the active router for the *whole* call (root + nested). Keep the raw `set_pipe_router` / `teardown_current_pipe_router` — the external `pipelex-mistralai-workflows` plugin depends on them (separate repo, can't edit here) — but prefer the scoped helper internally.

```python
# bridge.py _run_direct
direct_router = PipeRouter()
with scoped_pipe_router(direct_router):
    pipe_run = PipeRun(pipe_router=direct_router)
    pipe_output = await pipe_run.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
```

## The fork — what to do about the observer

The hub default in-process router is `PipeRouter(observer=multi_observer)` (`pipelex.py:452`), but the bridge builds a bare `PipeRouter()` (`observer=None`, see `pipe_router.py:10`). So **today**, in a non-Temporal worker:

- root pipe → bridge's bare router (no observer)
- nested pipes → hub default router (**with** `multi_observer`)

Scoping the bridge's bare router makes nested pipes consistent with the root — but they'd **lose** the router-level `multi_observer`. Open sub-question: does that matter? The hub *also* sets the observer separately (`pipelex.py:424` `set_observer(multi_observer)`), and the report delegate is reachable via the hub — so the router-level observer may be partly redundant. Needs a quick check of what `MultiObserver` does on a `PipeRouter` vs via the hub before choosing.

**Option A — Fix now, bare router (recommended).** Scope the bridge's bare `PipeRouter()` for the whole DIRECT run.
- Pros: smallest change; root + nested become consistent; matches what `_run_direct` already builds for the root; kills the Temporal-leak. Also delivers cubic's `scoped_pipe_router` request.
- Cons: nested pipes lose the router-level `multi_observer` in non-Temporal workers (behavior change — possibly fine if the hub observer covers it, possibly a telemetry regression).

**Option B — Fix now, preserve observer.** Scope an in-process router that carries `multi_observer`.
- Pros: no observer behavior change; still kills the leak.
- Cons: more plumbing — the bridge must source `multi_observer` (it lives in `Pipelex.make`, not trivially reachable from the framework-agnostic bridge); risks coupling the bridge back to internals it was extracted to avoid.

**Option C — Defer.** Leave routing untouched; this doc is the record.
- Pros: zero risk now; the bug can't fire until a Temporal-enabled worker ships.
- Cons: leaves a known P1 latent in new code; the root-vs-nested observer split persists.

## Test ideas (when fixed)

- Unit: `scoped_pipe_router` — `get_pipe_router()` returns the scoped router inside the block; nested `scoped_pipe_router` restores the *outer* override (not `None`) on inner exit; restores prior on outer exit.
- Bridge: install a sentinel/recording router as the hub default, run a sequence pipe in `DIRECT` mode via `run_pipe_via_bridge`, assert nested dispatch went through the scoped in-process router and **not** the hub default. (Optionally with `temporal_enabled=True` to prove no Temporal dispatch.)

## Related

- `graph-context-temporal-contract.md` — sibling bridge contract issue (#3).
- The raw `set_pipe_router`/`teardown_current_pipe_router` consumer lives in `pipelex-mistralai-workflows` (other repo) — if `scoped_pipe_router` lands, that plugin can adopt it later to fix its own unconditional teardown.
