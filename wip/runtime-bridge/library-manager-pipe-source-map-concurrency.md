# LibraryManager `_pipe_source_map` is not per-call scoped (deferred)

**Status:** deferred. Pre-existing `LibraryManager` behaviour, surfaced more by the bridge's per-call scoped-library path. Observability-only impact, Temporal not in production. Not fixed in PR #969.

## What

`LibraryManager._pipe_source_map` (`pipelex/libraries/library_manager.py:98`) is a **manager-level** dict keyed by `pipe_ref` (`domain.pipe_code`):

```python
self._pipe_source_map: dict[str, Path] = {}  # pipe_ref (domain.pipe_code) -> source .mthds file
```

Its siblings — `_blueprints`, `_crate_cache`, `_loaded_fingerprints` — are all keyed by `library_id` (one entry per open library). `_pipe_source_map` is the odd one out: it is shared across every open library.

`load_from_crate` writes `self._pipe_source_map[pipe_ref] = Path(source)`, and the keyed `teardown(library_id=...)` iterates the torn-down library's pipes and `pop()`s those `pipe_ref`s out of the shared map (`library_manager.py:122`).

## Why it can interfere across concurrent bridge calls

`run_pipe_via_bridge` opens a fresh per-call scoped library (`bridge._scoped_library_for_crate`) with a unique `library_id`, loads the caller's crate into it, and tears it down on exit. Two **concurrent** bridge calls whose crates define the **same** `pipe_ref` will:

- overwrite each other's source path (last writer wins), and
- one call's teardown can `pop()` the `pipe_ref` out from under the other still-running call, so the survivor's `get_pipe_source()` returns `None` (or, after an overwrite, the other tenant's path).

`get_pipe_source` feeds source attribution into the graph / observability layer only — it does **not** affect pipe resolution or run correctness. So the blast radius is a wrong-or-missing source path in a trace graph, not a wrong result.

There is also a broader, lower-confidence concern: `LibraryManager` mutates these plain dicts (`open_library` / `teardown` / `load_from_crate`) with no lock, while the bridge advertises a concurrent-activity execution model. The no-arg `teardown()` branch reassigns the dicts wholesale; concurrent mutation during the keyed teardown's iterate-and-`pop` could in principle raise `dictionary changed size during iteration`. Each bridge call uses a unique `library_id` (isolating `_libraries`/`_blueprints`/etc.), which keeps the realistic blast radius confined to `_pipe_source_map`.

## Why defer (not fix here)

- **Pre-existing.** This is `LibraryManager` behaviour, not introduced by this PR. The pre-existing Temporal `wf_pipe_router` scoped-library path uses the same map. The bridge only makes the concurrent-scoped-library pattern more prominent.
- **Observability-only.** Worst case is a wrong/missing source path in a trace graph. No run-correctness or data-loss impact.
- **Not in production.** The concurrent-multi-tenant path that triggers it is the Temporal/Mistral worker model, which is not in production.
- **Right fix touches `library_manager.py` beyond this PR's surface** and wants a deliberate design pass, not a reflexive patch on the way to landing the bridge.

## Fix shape when picked up

- Scope the source map per `library_id`: `dict[str, dict[str, Path]]` keyed by `library_id` (matching the sibling caches) so the keyed teardown pops only the calling library's entries and concurrent crates cannot clobber each other. Alternatively, store the source path on the `Library` object itself.
- If `LibraryManager` is to formally support concurrent callers, add a lock around the structural mutations in `open_library` / `teardown` / `load_from_crate` (or document that mutation is not thread-safe and require callers to serialise). At minimum, guard the `_pipe_source_map` iterate-and-`pop` in the keyed teardown.

Found by the `/review` adversarial (red-team) pass on PR #969.
