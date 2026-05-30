# Stuffs as first-class NodeSpec

## Why this exists

When we promoted `description` and `domain_code` onto `NodeSpec` for pipes, we deliberately stopped at pipes. Concepts have the same metadata (`domain_code`, `description`) and the same problem: today, the only way for a renderer to discover the domain or human description of a stuff's concept is to join with `GraphSpec.concept_registry` — and that registry is empty when `data_inclusion.pipe_and_concept_registry = False`.

So the symmetric fix is to make stuffs self-describing in the graph, just like pipe nodes now are.

This is a starter, not a worked plan. Treat the design below as a starting point — the code will likely have moved by the time we pick this up, and several of the choices below are reversible.

## Current shape (snapshot)

- `NodeKind` already defines `INPUT`, `OUTPUT`, `ARTIFACT` — so the type system says `NodeSpec` is meant to span pipes and stuffs.
- In practice today, only pipe-shaped `NodeSpec`s ever get emitted. `GraphTracer.on_pipe_start` and `GraphSpecAssembler._handle_pipe_start` create `PIPE_CALL` / `CONTROLLER` / `OPERATOR` nodes only.
- Stuffs live as `IOSpec` entries inside `NodeSpec.node_io.inputs` / `.outputs`.
- Renderers (mermaidflow, reactflow) synthesize stuff "nodes" inline at render time from `IOSpec` data, using digest-derived IDs — they never enter the model.

That inline synthesis is the asymmetry: pipe NodeSpecs are model-level, stuff nodes are render-level.

## What this rework would do

Make stuffs first-class `NodeSpec` instances:

- Tracer (and replay assembler) emit a `NodeSpec` per stuff with `kind` ∈ {`INPUT`, `OUTPUT`, `ARTIFACT`}.
- The stuff's concept metadata lives on the same `NodeSpec.description` / `NodeSpec.domain_code` fields we just added — same shape, semantics depend on `kind`:
    - On a pipe-call node: pipe's `description` and `domain_code`.
    - On a stuff node: the concept's `description` and `domain_code`.
- Pipe ↔ stuff relationships move out of `IOSpec` lists and into `EdgeSpec` entries (data edges already exist; this would extend their role).
- `IOSpec` goes away (or becomes a thin reference to the stuff node by `node_id`). One source of truth.

## Decisions taken in the discussion (revisable)

These were chosen quickly in chat and should be re-examined when picking this up:

- **One source of truth.** Stuffs as `NodeSpec` replaces `IOSpec`, not in parallel with it. Two-source designs were rejected to avoid drift between the in-model graph and the rendered one.
- **`NodeSpec.description` / `.domain_code` are polymorphic by `NodeKind`.** Same fields, semantics change by kind. The alternative (separate `concept_description` / `concept_domain_code` fields) was considered uglier given the taxonomy already exists.
- **`INPUT` / `OUTPUT` / `ARTIFACT` are semantic, not visual-only.** `INPUT` = pipeline entrypoint, `OUTPUT` = pipeline final, `ARTIFACT` = intermediate stuff. The tracer/assembler is responsible for classifying — renderers should not need to derive this from edge topology.

If any of these no longer fits when we revisit, change them. The starter doesn't lock anything in.

## Likely impact surface

Not exhaustive — just the obvious ones to scope from before committing:

- `pipelex/graph/graph_tracer.py` and `pipelex/tracing/graphspec_assembler.py` — emit stuff nodes, classify kind, drop or rewrite `IOSpec` aggregation.
- `pipelex/graph/graphspec.py` — `NodeSpec` field semantics doc, possibly retire `IOSpec` / `NodeIOSpec`.
- `pipelex/tracing/trace_events.py` — `PipeStartEvent.input_specs` rethink (events probably emit stuff-node ids instead of inline `IOSpec`).
- Every renderer that today synthesizes stuff nodes at render time (mermaidflow, reactflow JS bundle, HTML).
- All `GraphSpec` JSON fixtures under `tests/data/graphs/` — breaking change, will need regeneration.
- The existing pipe-side `description` / `domain_code` work landed in this branch — confirm semantics stay consistent when extended to stuff kinds.

## Open questions to settle before starting

- Stuff node identity: derive `node_id` from `stuff_code` (digest), or assign sequenced IDs like pipe nodes?
- Concept reference on the stuff node: still keep a `concept` string (qualified `domain.code`)? Drop it now that `domain_code` is a real field?
- Migration story for older `GraphSpec` JSON files. Probably "no back-compat" per repo policy, but worth confirming.
- `ERROR` `NodeKind` — same treatment as data kinds, or stays pipe-attached?

## Out of scope for this future work

- The pipe-side metadata wiring is already done — don't redo it.
- Adding new `NodeKind`s.
- Cross-pipeline concept dedup beyond what `concept_registry` already does.
