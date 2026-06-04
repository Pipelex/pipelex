# Blueprint Elaboration Directives — going further

A **blueprint elaboration directive** is a build-time instruction in a `.mthds` bundle that `BundleElaborator` expands into concrete pipes when the library loads — so the authoring shape and the executed shape differ. The first (and so far only) directive is `preliminary_text`, which synthesizes a draft-text pipe plus a `PipeStructure` pipe in memory.

This doc collects the work to take that system further: make the pipes the elaborator synthesizes first-class across observability, generalize the single-purpose elaborator into a directive framework, and add the tooling and guards a growing elaboration layer needs. None of it is started — pick items up as the need arises.

## Synthetic-pipe handling

The elaborator synthesizes pipes (e.g. `__draft_text`, `__structure`) that today surface as ordinary pipes everywhere. These items make them recognizable and friendly across the observability surfaces.

- **Marker on graph nodes + `pipelex list` exclusion.** When emitting `NodeSpec`, look up `bundle.elaboration_metadata` and set `tags["synthetic"] = "true"` + `tags["parent_pipe_code"] = parent`. Requires either a runtime-only field on `PipeAbstract` or a side-registry keyed by pipe code. Also hide synthetic pipes from `pipelex list`. This is the keystone — the next two build on it.
- **Friendly rendering across logs/traces/run-reporting.** Once the marker lands, render `<parent_pipe_code> [<step_role_label>]` everywhere `self.code` appears for a synthetic pipe. Touches graph_tracer, run_reporting, journal, distributed-tracing.
- **`mthds-ui` graph viewer integration.** Once the marker lands, decide in the UI repo whether to nest synthetic pipes under their parent or hide them.

## Generalizing the framework

- **Directive plugin registry.** `BundleElaborator` handles exactly one directive today (`_elaborate_preliminary_text`). Promote it to a plugin registry when a SECOND elaboration directive appears — not before, to avoid premature abstraction.

## Tooling & guards

- **`pipelex-dev elaborate-bundle <path>`.** A debugging CLI that prints the elaborated bundle form without running it, so directive expansion can be inspected directly.
- **Bundle-load benchmark in CI.** Microbenchmark library load time and alert on >5% regression. Protects future elaboration passes from silently slowing startup.

## Serialization

- **Persist `elaboration_metadata` across serialization boundaries.** Today `Field(exclude=True)` drops it on every `model_dump`. When a cross-boundary consumer materializes (graph viewer over a serialized bundle, Temporal payload, persistent cache), flip `exclude=False`, regenerate the schema, ship a plxt bump. The regression test at `test_elaboration_metadata.py::test_bundle_round_trip_drops_elaboration_metadata` flips first.
