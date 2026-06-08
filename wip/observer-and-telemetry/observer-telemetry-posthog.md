# How Observer, Telemetry, and PostHog actually fit together

Written up after a wrong mental model surfaced during the runtime-bridge DIRECT-router review (`wip/runtime-bridge/direct-mode-nested-router-leak.md`). The belief under review was: *"the `multi_observer` has nothing to do with telemetry, and we don't use it at all in practice."* Both halves are wrong in instructive ways. This doc is the corrected map, traced against the code on `feature/Runtime-bridge-extraction`.

## TL;DR — the corrected mental model

1. **The Observer subsystem's *only* job is telemetry.** The default `multi_observer` is `{"noop": ObserverNoOp, "telemetry": ObserverTelemetry}`. The noop does nothing; `ObserverTelemetry` emits PostHog product-analytics events (`PIPE_RUN`, `PIPE_COMPLETE`). There is nothing else in it. "Observer" and "pipe-level PostHog telemetry" are the same thing.

2. **It IS used in practice — but only on the Gateway/hosted path.** By default (BYO-key, direct Python SDK, pytest, CI) the telemetry manager resolves to `TelemetryManagerNoOp`, so the observer fires into a no-op and nothing leaves the process. The moment you run under **Pipelex Gateway**, a real `TelemetryManager` is built with `pipelex_telemetry_enabled=True` and those `PIPE_RUN`/`PIPE_COMPLETE` events flow to Pipelex's PostHog. So "we don't use it" is true for local/OSS, false for the hosted product.

3. **The hub-level observer is dead code.** `PipelexHub.set_observer()` stores `self._observer` and **nothing ever reads it** — there is no `get_observer`. The only live observer is the instance attribute on the `PipeRouter` (`router.observer`), consumed inside `PipeRouterProtocol.run()`. The hub write is a red herring; it provides zero redundant coverage.

## The Observer subsystem

### The protocol

`pipelex/observer/observer_protocol.py` — three async hooks plus a payload dict:

```python
class ObserverProtocol(Protocol):
    async def observe_before_run(self, payload: PayloadType) -> None: ...
    async def observe_after_successful_run(self, payload: PayloadType) -> None: ...
    async def observe_after_failing_run(self, payload: PayloadType) -> None: ...
```

`PayloadType = dict[str, Any]`, keyed by `PayloadKey` (`PIPELINE_RUN_ID`, `PIPE_JOB`, `PIPE_OUTPUT`, `ERROR`).

### Implementations that exist

| Class | File | Does | Wired by default? |
|---|---|---|---|
| `ObserverNoOp` | `observer/observer_protocol.py:40` | nothing | yes (as `"noop"`) |
| `MultiObserver` | `observer/multi_observer.py` | fans out to a named dict of sub-observers | yes (the container) |
| `ObserverTelemetry` | `system/telemetry/observer_telemetry.py` | calls `telemetry_manager.track_event(PIPE_RUN / PIPE_COMPLETE)` | yes (as `"telemetry"`) |
| `LocalObserver` | `observer/local_observer.py` | writes payloads to disk under `results/observer` | **no — defined but never instantiated in production wiring** |

`LocalObserver` is reachable only if a caller passes a custom `observers=` dict into `Pipelex.make()`. Default boot never builds it. (Flag: dead-ish code, or a debugging aid nobody wired.)

### Where the observer fires — the one live path

`PipeRouterProtocol.run()` is the only caller of the observer hooks:

- `pipelex/pipe_run/pipe_router_protocol.py:22` → `observe_before_run`
- `:34` → `observe_after_successful_run`
- `:46` → `observe_after_failing_run`

It calls `self.observer`, i.e. the observer attached to **that router instance** at construction. `PipeRouter.__init__` defaults to `ObserverNoOp` when none is passed (`pipe_run/pipe_router.py:11`).

### The wiring at boot (`pipelex/pipelex.py`)

```python
# pipelex.py ~417-452
if not observers:
    no_op_observer = ObserverNoOp()
    observer_telemetry = ObserverTelemetry(telemetry_manager=self.telemetry_manager)
    observers = {"noop": no_op_observer, "telemetry": observer_telemetry}
multi_observer = MultiObserver(observers=observers)
self.pipelex_hub.set_observer(observer=multi_observer)   # <-- DEAD: never read back
...
# non-Temporal:
self.pipelex_hub.set_pipe_router(PipeRouter(observer=multi_observer))   # <-- the ONLY live install
# Temporal:
self.pipelex_hub.set_pipe_router(make_temporal_pipe_router())          # observer = ObserverNoOp
```

So:

- **Non-Temporal hub router** carries `multi_observer` → telemetry fires (into whatever the telemetry manager is — real or no-op).
- **Temporal router** carries `ObserverNoOp` (`temporal/tprl_pipe/temporal_pipe_router.py:52`) → **no** pipe-level telemetry on Temporal at all. Precedent: "no router observer" is already a shipped state.

### The dead hub write — proof

```
hub.py:89   self._observer: ObserverProtocol | None = None   # declared
hub.py:206  self._observer = observer                        # written by set_observer
(no get_observer / get_required_observer anywhere in the repo)
```

Grep for `get_observer` / `_observer` readers returns only the declaration and the setter. The doc-in-review had hoped "the hub also sets the observer separately, so the router-level observer may be redundant." It isn't redundant — the hub copy is simply unused. Cleanup opportunity: either delete `_observer`/`set_observer`, or add a `get_observer` and actually route through it (decide intentionally).

## The Telemetry layer — what the observer feeds into

`ObserverTelemetry` is a thin adapter: it turns each pipe run into a `track_event` call (`observer_telemetry.py`). Everything past that is the **telemetry manager**, which has two independent sinks.

### Sink A — custom PostHog (user's own analytics)

- Config: `telemetry.toml` → `[custom_posthog] mode = ...`, model `TelemetryConfig` in `system/telemetry/telemetry_config.py`.
- Default: `PostHogMode.OFF` (`telemetry_config.py:81`).
- `track_event` (`telemetry_manager.py:245`) matches the mode: `OFF` → logs verbose and emits nothing; `ANONYMOUS`/`IDENTIFIED` → captures to the user's PostHog.

### Sink B — Pipelex Gateway telemetry (our hosted analytics)

- Flag: `pipelex_telemetry_enabled` on the `TelemetryManager`, gated by `is_pipelex_telemetry_enabled` in `TelemetryFactory.make_telemetry_manager` (`telemetry_factory.py`).
- Turned on when running under **Pipelex Gateway** (needs the gateway API key as distinct_id; `GatewayApiKeyMissingError` if absent).
- `track_event` always also fires Sink B when `_pipelex_telemetry_enabled` (`telemetry_manager.py:262`), **independent of `custom_posthog.mode`**. So even with custom PostHog `OFF`, Gateway users still emit `PIPE_RUN`/`PIPE_COMPLETE` to Pipelex's PostHog (`telemetry_factory.py:64-74`).

### When the whole telemetry manager collapses to a no-op

`TelemetryFactory.make_telemetry_manager` returns `TelemetryManagerNoOp` when:

- `DO_NOT_TRACK` env var is truthy (always respected; Gateway+DNT raises `GatewayDoNotTrackConflictError` rather than tracking), OR
- custom PostHog is `OFF` **and** Gateway telemetry is off, OR
- the **integration mode** disallows custom telemetry and Gateway is off. `is_custom_telemetry_allowed_for_mode(integration_mode)` — e.g. `pytest`/`ci`/`python` default to not allowing custom telemetry (see `telemetry.toml` `[telemetry_allowed_modes]` and the model defaults).

When it's `TelemetryManagerNoOp`, `ObserverTelemetry` still runs every pipe but `track_event` does nothing.

### "Is it used in practice?" — the matrix

| Context | custom PostHog | Gateway telemetry | Net effect of the observer |
|---|---|---|---|
| Local dev / direct Python SDK, no config | OFF (default) | off | **no-op** — fires into `TelemetryManagerNoOp` |
| pytest / CI | disallowed by mode | off | **no-op** |
| User explicitly sets `mode=anonymous/identified` | on | off | events → user's PostHog |
| **Pipelex Gateway (hosted runner)** | usually OFF | **on** | **events → Pipelex PostHog** (live, real) |
| Any of the above + `DO_NOT_TRACK=1` | — | forced off | no-op |
| Temporal router (any context) | — | — | **no-op** (router uses `ObserverNoOp`) |

So the honest statement is: *the observer is best-effort PostHog product analytics; it is genuinely inert in OSS/local/test, and genuinely live for Gateway/hosted non-Temporal runs.*

## Don't confuse these three things — they are all "observability" but separate

The word "tracing"/"observability" is overloaded across the codebase. They are independent subsystems:

1. **Observer → PostHog events** (this doc). Coarse product analytics: a `PIPE_RUN` / `PIPE_COMPLETE` event per pipe, with `pipeline_run_id` + `pipe_type`. Driven by `router.observer`. Sinks: user PostHog and/or Pipelex PostHog.

2. **OTel AI tracing** (`custom_posthog.tracing`, `pipelex_telemetry`). OpenTelemetry spans for LLM/inference calls, built in `TelemetryManager` (`telemetry_manager.py:83-106`, `otel_factory.py`). Separate enable flags, separate exporter. Not the observer.

3. **Pipelex trace-event log** (`[pipelex.tracing_config]` in `pipelex.toml`, `flush_trace_events_to_backend`). The distributed run-trace log persisted to NDJSON / DynamoDB for cross-Temporal-worker run reconstruction. This is the subject of `wip/runtime-bridge/trace-flush-blocking-io.md`. Nothing to do with PostHog or the observer.

If someone says "telemetry is off so tracing is off," check *which* of the three they mean — they don't share switches.

## Implications for the bridge DIRECT-router decision

(Full context in `wip/runtime-bridge/direct-mode-nested-router-leak.md`.) Because the router observer's sole effect is best-effort PostHog telemetry, and because:

- the **root** pipe of a DIRECT run **already** carries no observer today (bare `PipeRouter()` → `ObserverNoOp`), so DIRECT runs already emit telemetry on nested pipes but not the root — an inconsistency, not a feature;
- Temporal mode already emits nothing through this path;
- threading the observer into the bridge (Option B) would require a `get_observer` on the hub that **doesn't exist**, i.e. re-coupling the framework-agnostic bridge to internals;

→ **Option A (scope the bare router for the whole DIRECT run)** is safe: it makes root + nested consistently silent on PostHog pipe events, matching Temporal. The only loss is nested-pipe `PIPE_RUN`/`PIPE_COMPLETE` events **for Gateway users running bridge-DIRECT pipes** — a brand-new path no dashboard depends on yet. If complete pipe telemetry on this path is ever wanted, that's a separate "make telemetry whole" task (and would mean giving the root pipe an observer too, which today's code doesn't).

## Flagged cleanups (separate from the bridge work)

- `PipelexHub._observer` / `set_observer` is write-only dead code. Remove it, or wire `get_observer` and route the router through it intentionally.
- `LocalObserver` is defined but never instantiated by default boot. Confirm whether it's a debugging aid worth keeping or removable.
- `multi_observer` always contains a `"noop"` entry that does nothing on every pipe — harmless, but it's pure overhead in the fan-out loop. Likely a placeholder for "there's always at least one observer."
