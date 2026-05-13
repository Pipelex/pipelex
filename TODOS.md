# Promote `description` and `domain_code` onto `NodeSpec`

## Goal

Surface pipe `description` and `domain_code` directly on each `NodeSpec` so renderers (reactflow viewer, mermaid, future consumers) can show per-node pipe details without joining `pipe_registry` — and so the data flows even when `data_inclusion.pipe_and_concept_registry` is disabled.

## Approach

- New fields on `NodeSpec`: `description: str | None = None`, `domain_code: str | None = None`.
- Wire them through the full pipeline: call site → tracer protocol/manager → live tracer + replay assembler → internal `_MutableNodeData`/`_AssemblerNodeData` → `NodeSpec`.
- Also propagate through `PipeStartEvent` so the event-replay path on Temporal carries the same data.
- Strict TDD: every layer has a failing test landed first, then the code change that turns it green.

### Why `str | None` on `NodeSpec` even though `PipeAbstract.description` / `domain_code` are required `str`

The pipe-side and the node-side aren't symmetric:

- **`PipeAbstract` side (`pipelex/core/pipes/pipe_abstract.py:52-53`)**: `domain_code: str` and `description: str` are required. Every pipe definition must declare both — that's a language-level invariant.
- **`NodeSpec` side**: a `NodeSpec` is "a node in the run graph," and `NodeKind` (`pipelex/graph/graphspec.py:24-33`) is wider than "pipe call":
    - `PIPE_CALL` / `CONTROLLER` / `OPERATOR` → backed by a `PipeAbstract` → both fields available.
    - `INPUT` / `OUTPUT` / `ARTIFACT` / `ERROR` → no pipe behind them → nothing meaningful to put in `description` / `domain_code`. Making the fields required would force fake values on these nodes, which is worse than `None`.
- **Back-compat**: existing GraphSpec JSON files (`tests/data/graphs/cv_batch.json`, `cv_job_match.json`, `cv_batch_old.json`, and any spec saved by an older Pipelex version) have `nodes[*]` without these keys. `NodeSpec` uses `ConfigDict(extra="forbid", strict=True)`, so missing keys are fine only if the fields have defaults. Required fields would break loading of every older GraphSpec JSON.

Net: `str` on the pipe (required by the language), `str | None = None` on the node (optional because the node-kind taxonomy is wider than pipe-call, and to keep older JSON loadable).

## Files in scope

- `pipelex/graph/graphspec.py` — `NodeSpec` model.
- `pipelex/tracing/trace_events.py` — `PipeStartEvent`.
- `pipelex/graph/graph_tracer_protocol.py` — `on_pipe_start` signature.
- `pipelex/graph/graph_tracer_manager.py` — manager forwarding.
- `pipelex/graph/graph_tracer.py` — live tracer + `_MutableNodeData`.
- `pipelex/tracing/graphspec_assembler.py` — replay assembler + `_AssemblerNodeData`.
- `pipelex/core/pipes/pipe_abstract.py` — call site.

---

## Phase 1 — `NodeSpec` schema (red → green)

- [ ] Add a failing unit test in `tests/unit/pipelex/graph/test_graphspec_validation.py` (new `TestNodeSpecPipeMetadata` class in a new module if a second class is needed — recall: 1 class per module) asserting:
    - [ ] `NodeSpec(... description="d", domain_code="dc", ...)` instantiates.
    - [ ] `description` and `domain_code` default to `None` when omitted (back-compat).
    - [ ] `NodeSpec(**node.model_dump(by_alias=True))` round-trips.
- [ ] Run the test, confirm it fails on unknown keyword (`extra="forbid"`).
- [ ] Add `description: str | None = None` and `domain_code: str | None = None` to `NodeSpec` in `pipelex/graph/graphspec.py`.
- [ ] Run `make agent-check` and the new test alone; both green.

## Phase 2 — `PipeStartEvent` payload (red → green)

- [ ] Add a failing test in `tests/unit/pipelex/tracing/test_trace_events.py` asserting:
    - [ ] `PipeStartEvent(..., description="d", domain_code="dc")` instantiates.
    - [ ] Fields default to `None` when omitted.
    - [ ] JSON round-trip preserves both fields.
- [ ] Run, confirm failure.
- [ ] Add `description: str | None = None` and `domain_code: str | None = None` to `PipeStartEvent` in `pipelex/tracing/trace_events.py`.
- [ ] Re-run; green.

### Checkpoint A — schema layer complete

At this point the data model can carry the new fields end-to-end but nothing populates them. Good handoff point: next phase opens up the wiring layer across tracer / assembler / call site.

Status snapshot to record here when reached:

- [ ] Phase 1 + 2 done.
- [ ] No existing tests broken (run `make agent-test`).

---

## Phase 3 — Live tracer wiring (red → green)

- [ ] Add a failing test in `tests/unit/pipelex/graph/` (new module e.g. `test_graph_tracer_node_metadata.py`, one class) that:
    - [ ] Builds a `GraphTracer` directly, calls `on_pipe_start(..., description="d", domain_code="dc", ...)`, then `on_pipe_end_success(...)` and `teardown()`.
    - [ ] Asserts the resulting `GraphSpec.nodes[0].description == "d"` and `.domain_code == "dc"`.
- [ ] Run, confirm failure (kwarg unknown).
- [ ] Add `description` and `domain_code` parameters (both `str | None = None`) to:
    - [ ] `GraphTracerProtocol.on_pipe_start` in `pipelex/graph/graph_tracer_protocol.py`.
    - [ ] `GraphTracerManager.on_pipe_start` in `pipelex/graph/graph_tracer_manager.py` (forward through).
    - [ ] `GraphTracer.on_pipe_start` in `pipelex/graph/graph_tracer.py`.
    - [ ] No-op / null tracer implementations (whatever else implements the protocol).
- [ ] Extend `_MutableNodeData` in `pipelex/graph/graph_tracer.py` with the two fields and pass them when constructing.
- [ ] Update the conversion that builds the final `NodeSpec` (look for the `to_node_spec` / `NodeSpec(...)` site inside `graph_tracer.py`) to forward both fields.
- [ ] Also include `description`/`domain_code` when emitting `PipeStartEvent` (lines ~611–627 in `graph_tracer.py`).
- [ ] Re-run the new test; green. Run `make agent-check`.

## Phase 4 — Replay assembler wiring (red → green)

- [ ] Add a failing test in `tests/unit/pipelex/tracing/test_graphspec_assembler.py` (new test method inside the existing class — keep 1 class per module rule) that:
    - [ ] Feeds a `PipeStartEvent` with `description="d"`, `domain_code="dc"` plus matching `PipeEndSuccessEvent` to `GraphSpecAssembler.assemble(...)`.
    - [ ] Asserts the produced `GraphSpec.nodes[0].description == "d"` and `.domain_code == "dc"`.
- [ ] Run, confirm failure.
- [ ] Extend `_AssemblerNodeData` in `pipelex/tracing/graphspec_assembler.py` with the two fields.
- [ ] In `_handle_pipe_start`, read `event.description` / `event.domain_code` and store on the node.
- [ ] In the assembler's NodeSpec construction site, forward both fields.
- [ ] Re-run; green.

---

## Phase 5 — Call-site wiring in `PipeAbstract.run_pipe` (red → green)

- [ ] Add a failing **integration** test (or expand an existing one under `tests/integration/pipelex/temporal/tracing/` or `tests/e2e/pipelex/graph/`) that:
    - [ ] Runs (dry-run is fine) a small pipeline with a known pipe `code`, `domain_code`, and `description`.
    - [ ] Asserts the resulting `GraphSpec` has a node whose `description` and `domain_code` match the source pipe.
- [ ] Run, confirm failure (still `None`).
- [ ] In `pipelex/core/pipes/pipe_abstract.py` around line 454 (`tracer_manager.on_pipe_start(...)`), pass `description=self.description, domain_code=self.domain_code`.
- [ ] Re-run; green.

## Phase 6 — Sweep for incidental breakage

- [ ] `grep -rn "on_pipe_start(" tests/ pipelex/` and update any in-test callers if they assert exact kwargs.
- [ ] `grep -rn "PipeStartEvent(" tests/ pipelex/` — confirm new optional fields don't break existing constructions (they shouldn't, since defaults are `None`).
- [ ] `grep -rn "NodeSpec(" tests/ pipelex/` — confirm no test re-asserts field-set exhaustiveness in a way that the new fields would break.
- [ ] Re-run `make agent-test`. Fix any fallout.

## Phase 7 — Quality gates

- [ ] `make agent-check` (pyright, ruff, mypy, plxt) — clean.
- [ ] `make agent-test` — green.
- [ ] Eyeball one generated `GraphSpec` JSON (e.g. via a small dry-run script or an existing e2e graph fixture regenerated) and confirm the new fields appear on nodes.

### Checkpoint B — feature complete

Status snapshot to record here when reached:

- [ ] Phases 3–7 done.
- [ ] `NodeSpec.description` + `NodeSpec.domain_code` populated on every pipe-call node in both live and replay paths.
- [ ] Optional next step (NOT part of this plan; track separately if pursued): wire the reactflow viewer (`pipelex/graph/reactflow/assets/`) to consume the new per-node fields instead of joining with `pipe_registry`.

---

## Out of scope

- Renderer changes (mermaid, reactflow JS bundle). The data is being made available; UI consumption is a follow-up.
- Adding `description` / `domain_code` to `pipe_registry` entries — already present via `model_dump`.
- Changes to `error` / `artifact` / `input` / `output` `NodeKind`s — they keep both fields as `None`.

## Decisions taken

- Fields are optional (`str | None`, default `None`) — keeps old GraphSpec JSON loadable and keeps non-pipe nodes valid.
- Description is propagated explicitly through `on_pipe_start` parameters (not derived from `pipe_data`) so it flows even when `data_inclusion.pipe_and_concept_registry = False`.
