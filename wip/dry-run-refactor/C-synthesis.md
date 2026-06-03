> **Background — condensed answers to the founding questions; still accurate, with one update.** The `DryPipeRouter`-is-dead verdict, the taxonomy, the load profile, and the per-request injection mechanism all still hold. The one thing that changed: §5's last bullet (the three abandoned `# TODO` dry-run lines in `validate_bundle.py`) is **no longer true** — that regression was closed by signature-validation. Updated in place below.

# Synthesis — answers to user's questions

## 1. Is DryPipeRouter dead? YES — confirmed.

- `PipeAbstract._run_pipe_traced` (core/pipes/pipe_abstract.py:504-520) does the LIVE/DRY
  match. Any router calling `pipe.run_pipe(...)` with `run_mode=DRY` will end up in
  `dry_run_pipe()` automatically.
- `DryPipeRouter._run_pipe_job` (pipe_run/dry_pipe_router.py:18) calls
  `pipe.dry_run_pipe(...)` directly — same destination, different door.
- Grep finds no production instantiation. The class is defined and never used.
- **Delete it.** It's also conceptually wrong: it says "dry-run is a routing concern"
  when it's actually a pipe-execution concern.

## 2. Taxonomy of the four classes

| Class | Role | Side | What it does |
|---|---|---|---|
| `PipeRouter` | router | local | Calls `pipe.run_pipe()`. That's it. Mode-agnostic. |
| `PipeRun` | orchestrator | local | Wraps router + delivery + graph assembly + tracing cleanup. |
| `WfPipeRouter` | router | **server-side workflow** | Same job as PipeRouter, but it IS a Temporal child workflow. Adds library hydration + per-workflow tracing inside the workflow boundary. |
| `WfPipeRun` | orchestrator | **server-side workflow** | Same job as PipeRun, but is a Temporal parent workflow that runs WfPipeRouter as a child and delivery as an activity. |
| `TemporalPipeRouter` | router | **client-side launcher** | Submits WfPipeRouter to Temporal. |
| `TemporalPipeRun` | orchestrator | **client-side launcher** | Submits WfPipeRun to Temporal. |

The naming confusion: `Wf*` = server-side (runs IN the Temporal worker),
`Temporal*` = client-side (the thing that KICKS OFF a workflow from the API).
Worth renaming to `WorkflowPipeRouter` vs `TemporalSubmitterPipeRouter` or similar.

### Hub swap

`Pipelex.setup()` at pipelex.py:443-461:
- Line 447-452: pipe_router → TemporalPipeRouter if `config.temporal.is_enabled`, else PipeRouter
- Line 454-461: pipe_run → TemporalPipeRun if enabled, else PipeRun(router)

**One swap per process at boot.** Not per-request.

### Per-request override

`PipelexRunner.__init__(pipe_run=...)` (runner.py:62) lets you inject a PipeRun.
Line 152: `effective_pipe_run = self._pipe_run or get_pipe_run()`.

So you CAN say "for this request, use the local PipeRun even though the hub default
is the Temporal one." But you can only inject the whole PipeRun, not the router
separately. That's enough for the dry-run case.

## 3. Dry-run load profile — verdict: SAFE IN-PROCESS

| Resource | Per dry-run |
|---|---|
| Latency | 5-50 ms (Pydantic + Jinja2 dominate) |
| Memory | 1.5-2 MB |
| Network | 0 |
| Disk I/O | 0 |
| Subprocess | 0 |
| Throughput/worker | ~20k/sec theoretical |
| Locks | 1 (schema codegen cache, uncontended post-warmup) |

Bottlenecks:
- GIL (Pydantic + Jinja2 are sync CPU, block the event loop briefly)
- Memory: ~2GB for 1000 concurrent in flight
- Tail latency starts mattering above ~100 concurrent per worker

Caveats:
- If user pipes wire in a `PipeFunc` that does blocking I/O, all bets off.
- Pathological Jinja2 templates could push render to 10+ ms.

## 4. Architectural implication

Under the user's philosophy ("a run is a run, all paths the same"), and combined
with the load profile (dry-run is cheap), here's the design that falls out:

**Dry-runs go through the same PipelexRunner → PipeRun → DeliveryExecutor as live
runs, but with `pipe_run_mode=DRY`. In a FastAPI process where Temporal is the
hub default for live runs, the dry-run endpoint injects a local `PipeRun` per
request.** Something like:

```python
# Live endpoint — hub default (TemporalPipeRun)
runner = PipelexRunner(pipe_run_mode=PipeRunMode.LIVE, ...)
await runner.execute_pipeline(..., delivery=user_delivery)

# Dry endpoint — explicit local PipeRun
runner = PipelexRunner(
    pipe_run_mode=PipeRunMode.DRY,
    pipe_run=PipeRun(pipe_router=PipeRouter(...)),  # force local
    ...
)
await runner.execute_pipeline(..., delivery=fs_delivery)
```

This collapses ALL the dead/duplicate paths:
- `dry_run.py` / `dry_run_pipe` / `dry_run_pipes` — gone (validators try/except the runner)
- `dry_run_pipeline.py` — gone (callers use runner directly)
- `dry_run_with_graph.py` — gone (set generate_graph=True on the runner)
- `dry_pipe_router.py` — gone (mode is pipe-level, not router-level)
- `_run_core.py` artifact block — gone (DeliveryExecutor handles it via a filesystem target)

## 5. Smells worth noting (carryover from agents)

- TemporalPipeRun hardcodes `WfPipeRouter` — can't inject workflow class.
- PipelexRunner can't inject a router separately — must wrap in a PipeRun.
- "delivery_assignment is None" as the implicit "skip delivery" — ad-hoc.
- Library/tracing setup scattered across WfPipeRouter (lines 51-65, 72-123) and
  WfPipeRun (lines 83-97). Could be context managers.
- ~~Three `# TODO: wip - restore or refactor dry run` in validate_bundle.py~~ —
  **CLOSED.** Since this synthesis was written, signature-validation restored
  dry-on-load: `validate_bundle` now calls `dry_run_pipes(...)` on every load
  path. But it did so through the **old** `dry_run.py` (not the PipelexRunner
  consolidation), and then extended that module with the strict signature
  pre-check. So the duplicate paths in §4 are still uncollapsed — the
  consolidation goal stands — but `dry_run.py` is now load-bearing for
  signatures (see `A-taxonomy.md` §7), which makes the deletion bigger than this
  synthesis assumed.
