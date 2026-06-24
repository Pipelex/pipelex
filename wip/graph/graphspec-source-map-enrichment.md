# GraphSpec Registry Source Paths

## Question

Can `GraphSpec` include the source bundle path for each pipe and concept by enriching `pipe_registry` and `concept_registry` entries from `LibraryCrate.source_map`?

Short answer: yes, this is feasible, and the lowest-churn path is to add a `source` field to registry payload dictionaries at graph event creation time.

## Current State

`GraphSpec` has:

- `nodes[]`: execution nodes with `pipe_code`, `pipe_type`, `description`, `domain_code`, IO, timing, status, metrics, and execution data.
- `pipe_registry`: `dict[str, dict[str, Any]]`, keyed by `domain.pipe_code`.
- `concept_registry`: `dict[str, dict[str, Any]]`, keyed by `domain.ConceptCode`.

The registry entries are optional. They are emitted only when `graph_config.data_inclusion.pipe_and_concept_registry` is true, which is true in the shipped config.

Today those registry entries do not include bundle source paths:

- pipe registry entries come from `PipeAbstract.model_dump(mode="json")`;
- concept registry entries come from `Concept.model_dump(mode="json")` plus `json_schema`;
- runtime `PipeAbstract` has no `source` field;
- runtime `Concept` does not receive the blueprint `source` when created.

The source data exists elsewhere:

- `PipeBlueprint.source` and `ConceptBlueprint.source` exist at blueprint level.
- `LibraryCrate.source_map` maps both `pipe_ref` and `concept_ref` to the source file path.
- `LibraryManager.get_pipe_source()` exposes pipe source for diagnostics, backed by the crate source map.
- `PipeJob.library_crate` is already attached by `prepare_pipe_job()` and crosses the Temporal boundary.

## Recommended Design

Enrich registry payloads before they are handed to the tracer:

- pipe registry entry: add `source` from `library_crate.source_map[self.pipe_ref]`;
- concept registry entry: add `source` from `library_crate.source_map[concept.concept_ref]`;
- if no crate or no source map entry exists, omit the field rather than emitting `source: null`.

This keeps source paths attached to the existing registry artifacts and avoids changing `NodeSpec`, `PipeAbstract`, or `Concept`.

Example resulting shape:

```json
{
  "pipe_registry": {
    "research.summarize": {
      "code": "summarize",
      "domain_code": "research",
      "type": "PipeLLM",
      "description": "Summarize notes",
      "inputs": {},
      "output": {},
      "source": "/workspace/research/summarize.mthds"
    }
  },
  "concept_registry": {
    "research.Summary": {
      "code": "Summary",
      "domain_code": "research",
      "description": "A summary",
      "structure_class_name": "...",
      "json_schema": {},
      "source": "/workspace/research/concepts.mthds"
    }
  }
}
```

## Why This Is Feasible

The graph event creation point has access to both sides:

- `PipeAbstract._run_pipe_traced(..., library_crate: LibraryCrate | None = None)` already receives the crate.
- The same function currently builds `pipe_data` and `concept_data` before calling `tracer_manager.on_pipe_start(...)`.
- `PipeAbstract._make_single_concept_data_for_registry()` already centralizes concept registry payload construction.
- `PipeStartEvent.pipe_data` and `PipeStartEvent.concept_data` are generic dictionaries, so serialized Temporal graph events can carry the additional `source` field without schema changes.
- `GraphTracer` and `GraphSpecAssembler` already copy those dictionaries into `GraphSpec.pipe_registry` / `concept_registry` unchanged.

No `GraphSpec` schema migration is required because the registries are already `dict[str, Any]` payloads.

## Implementation Plan

1. Thread source-map awareness into registry serialization.

   Suggested helpers in `PipeAbstract`:

   ```python
   def _make_pipe_data_for_registry(self, *, library_crate: LibraryCrate | None) -> dict[str, Any]:
       pipe_data = self.model_dump(mode="json")
       if library_crate is not None:
           source = library_crate.source_map.get(self.pipe_ref)
           if source:
               pipe_data["source"] = source
       return pipe_data
   ```

   Update concept helpers similarly:

   ```python
   def _make_single_concept_data_for_registry(
       self,
       concept: Concept,
       *,
       library_crate: LibraryCrate | None,
   ) -> dict[str, Any]:
       concept_dict = concept.model_dump(mode="json")
       if library_crate is not None:
           source = library_crate.source_map.get(concept.concept_ref)
           if source:
               concept_dict["source"] = source
       ...
   ```

2. Use those helpers from `_run_pipe_traced()`.

   Replace:

   ```python
   pipe_data = self.model_dump(mode="json")
   concept_data = self._make_concept_data_for_registry()
   ```

   with source-aware helper calls using the `library_crate` argument already present in `_run_pipe_traced()`.

3. Preserve current behavior when source is unavailable.

   This happens for:

   - in-memory protocol validation without `mthds_sources`;
   - tests or internal call sites that build `PipeJob` without `library_crate`;
   - native concepts or concepts loaded from code rather than a `.mthds` declaration;
   - dependency scenarios where the active crate does not include a source-map entry for a cross-package ref.

   In all of those cases, omit `source`.

4. Keep source on registry entries, not nodes.

   A node is an invocation. A registry entry is the declaration. Source path is declaration metadata, so the registry is the right layer. Renderers can join `node.domain_code + "." + node.pipe_code` to `pipe_registry` when they need to show source.

## Tests

Add coverage for both direct and assembled graph paths.

1. Unit-level helper test in the graph or pipe area:

   - construct a pipe with a fake `LibraryCrate(source_map={pipe_ref: "...", concept_ref: "..."})`;
   - run with `pipe_and_concept_registry=True`;
   - assert registry payloads include `source`.

2. Direct/in-memory graph integration:

   - use a real `.mthds` bundle loaded from disk;
   - run graph generation;
   - assert `graph_spec.pipe_registry["domain.pipe"]["source"]` is the bundle path;
   - assert declared concepts in `concept_registry` include their source path.

3. Temporal/event-assembled path:

   - ensure `PipeStartEvent.pipe_data` / `concept_data` carry `source`;
   - assert `GraphSpecAssembler` preserves the fields into `pipe_registry` / `concept_registry`.

4. Sourceless path:

   - validate/run from raw in-memory `mthds_contents` without `mthds_sources`;
   - assert graph generation still succeeds and registry entries simply omit `source`.

## Edge Cases

- Multi-file same-domain bundles: `LibraryCrate.source_map` already tracks the winning declaration source for each `pipe_ref` / `concept_ref`, including signature/concrete reconciliation, so use it as the source of truth.
- Duplicate declarations: no new logic needed; the crate factory already rejects or reconciles before execution.
- Cross-package dependencies: confirm whether the `PipeJob.library_crate` used by the executing pipe includes dependency source-map entries. If not, source enrichment will be incomplete for dependency pipes. That is acceptable for a first pass, but it should be documented and pinned with a test or follow-up.
- Privacy: source paths can be absolute filesystem paths. That is already true in validation diagnostics and `LibraryCrate.source_map`, but exposing them through API graph responses is a product/API decision. If public hosted responses should not leak worker filesystem paths, add a normalization/redaction policy before shipping this on hosted surfaces.

## Files To Touch

- `pipelex/core/pipes/pipe_abstract.py`
- tests under `tests/unit/pipelex/graph/` or `tests/unit/pipelex/core/pipes/`
- graph integration tests under `tests/integration/pipelex/pipeline/` or existing graph tracing tests
- Temporal tracing tests if the event-assembled path needs explicit coverage

## Recommendation

Implement this as a registry enrichment, not as a structural `GraphSpec` model change. It is additive, works for direct and Temporal graph assembly, and uses the already-canonical `LibraryCrate.source_map` instead of duplicating source-tracking state onto runtime pipe/concept models.
