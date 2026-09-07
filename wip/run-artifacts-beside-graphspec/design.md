---
status: active
item: L-260907-817d80
---

# Design: a run's results carry the I/O artifacts that describe its data

## The problem

A run's `graphspec.json` carries every stuff payload the run produced and nothing that says what those payloads are. The graph renderer (`@pipelex/mthds-ui`, `GraphViewer`) shows a data node's value only when its host passes both `pipe_io_contracts` and `output_form`, keyed by `pipe_ref`; without them it shows the concept's structure table and no data tab, by design (`mthds-ui/src/graph/react/viewer/GraphViewer.tsx:255-273`, "both artifacts or neither"). The three artifacts — `pipe_io_contracts`, `input_form`, `output_form` — are the validate report's own fields, and today they exist only on `/validate`.

The ledger item asks that a run write them beside its `graphspec.json`, as three sibling files under the standard's names. This document confirms the ask, corrects the item's premise about *where* they can be built, and settles the shape that serves the local file layout and the hosted plane alike.

## What the survey established

### Every consumer of a run's graph is missing them, and each patches around it differently

- **`vscode-pipelex`** has the reader and no producer: `readRunArtifacts` (on branch `fix/Expanded-input-slot`, `editors/vscode/src/pipelex/graph/runArtifacts.ts:46-48,110-129`) loads `pipe_io_contracts.json`, `output_form.json` and an optional `input_form.json` from the graphspec's own directory, takes the first two together or not at all, and is silent on absence.
- **`pipelex-app`** is the only consumer that renders a run's graph *with* data, and it does so by pairing the run's `graph_spec` (from `GET /v1/runs/{id}/results`) with the artifacts of a **separate `/validate` of the current editor buffer**, held in a non-persisted client store (`src/actions/mthds-validator.ts:296-300`, `src/hooks/use-method-validation.ts:134-151`). The app documents the resulting gap itself: "a run restored without its validate artifacts has a value and no declaration of what it is" (`src/components/method-run/output-render.tsx:37-42`, also `flowchart-view.tsx:66-72`). A historic run whose method has since changed is rendered against the wrong description.
- **`pipelex-mcp`** mounts `GraphViewer` on a completed run with no artifacts at all (`src/views/run-graph.tsx:236-244`, `src/views/run-follow.tsx:456-466`), so every hosted run graph it shows takes the no-data floor.
- **Neither SDK** carries the artifacts on a run-result type; `RunResults` in `@pipelex/sdk` has `graph_spec` and nothing describing it (`pipelex-sdk-js/src/runs.ts:156-190`). The platform's `GET /v1/runs/{id}/results` reads a **hardcoded set of result filenames** from S3 and relays them verbatim (`pipelex-server/platform/src/pipelex_platform/routers/v1/runs.py:141-176`); the platform persists no contracts or forms anywhere, and the `Run` row keeps only `mthds_contents` as "the only record of what ran" (`shared/src/pipelex_shared/schemas/run.py:126`).

So the need is real and wider than the item states: a run's own artifacts are the only correct description of a run's data, locally and hosted, and no path produces them today.

### The three builders need the run's library window, and the item's proposed hook is outside it

`build_pipe_io_contracts` (`pipelex/pipeline/pipe_io_contracts.py:135`), `build_input_form` and `build_output_form` (`pipelex/pipeline/input_form.py:154,190`) take the live pipes and read the current library: JSON-Schema rendering resolves bundle-defined structure classes through the class registry, and the forms qualify the current library's crate (`qualify_current_library_crate`, `input_form.py:246`). The validate path says so in as many words and builds them inside the window before its `finally` tears it down (`pipelex/pipeline/validate_in_process.py:86-91,109-115`); the hosted Temporal validator does the same in its worker's one window (`pipelex-server/temporal/pipelex_temporal/tprl_pipe/act_dry_validate.py:142-156`).

The item names the write sites as the natural hook — `generate_graph_outputs` / `save_graph_outputs_to_dir` and the delivery executor's `_generate_graph_files`. Neither holds the window:

- **The local CLIs write after the window has closed.** `PipelineRunner.execute` restores the outer library and tears the run library down in its `finally` (`pipelex/pipeline/runner.py:303-315`) *before* returning to `pipelex run`, which only then calls `generate_graph_outputs` and `save_graph_outputs_to_dir` (`pipelex/cli/commands/run/_run_core.py:281-287`); `pipelex-agent run` is the same shape (`pipelex/cli/agent_cli/commands/run/_run_core.py:173-190`).
- **The hosted delivery may run on a worker that never loaded the bundle.** In the Temporal plugin the `PipeOutput` is dehydrated before the workflow's tail precisely because `act_deliver` "may run on a worker that has never loaded this bundle" (`pipelex-server/temporal/pipelex_temporal/tprl_pipe/wf_pipe_run.py:430-435`); `DeliveryActivityArg` carries the output, the scope and the assignment, no crate and no pipes (`act_deliver.py:17-31`); and the delivery executor's raw-working-memory branch and `try_local_hydrate_stuff` exist because the classes may not be registered (`pipelex/pipe_run/delivery_executor.py:90-97,218-246`).

The direct-mode delivery is the one write site that *is* inside the window: `PipeRun.run` delivers in its `finally`, which runs inside `runner.execute`'s `try` (`pipelex/pipe_run/pipe_run.py:76-103`). That is not enough to build on, since the same class delivers the Temporal path from outside the window.

### How a run's graph already crosses the same boundary

`graph_spec` is the precedent. It is assembled at the end of the run onto `pipe_output.graph_spec` (`assemble_tracing_on_output`, `pipe_run.py:82-90`; the Temporal twin stamps it in the workflow tail, `wf_pipe_run.py:481-517`), rides on `PipeOutput` — a wire model of the transport boundary (`docs/specs/pipelex-transport-boundary.md`, section C) — crosses the SPI payload as `graph_spec_dump` (`pipelex/runtime_bridge/payloads.py:81`, `serialization.py:65`), is rehydrated by `pipelex-api` for the `/execute` response (`pipelex-api/api/routes/pipelex/pipeline.py:134-167`), and is written by whoever holds the output: the CLIs to a directory, the delivery executor to storage. Every writer serializes what the run assembled; none rebuilds it.

## Decision

**The artifacts are built once, inside the run's library window, and carried on `PipeOutput` beside `graph_spec`. Every writer that serializes `graph_spec` to `graphspec.json` serializes them to three sibling files.**

### 1. One model, one builder

A new module `pipelex/core/pipes/pipe_io_artifacts.py` holds:

- `PipeIOArtifacts`, a pydantic model with exactly the three report fields under the report's names and types: `pipe_io_contracts: PipeIOContracts`, `input_form: InputForm`, `output_form: OutputForm`. `extra="forbid"`. It is a grouping, not a new shape: each field is the standard's artifact, and the three are always produced together because they share one key set (all three iterate the same pipes, `input_form.py:155-157`).
- `build_pipe_io_artifacts(pipes, *, qualified_crate=None) -> PipeIOArtifacts`, which qualifies the current library's crate once and runs the three existing builders off it, exactly the sequence `validate_in_process.py:109-115` performs today. `validate_bundles_in_process` and the projection-corpus command call it instead of the three builders, so the sequence exists in one place and a future fourth artifact is populated everywhere or nowhere — the same rule `build_validation_report` states for the report.
- The three filenames as module constants, moved from `generate_projection_corpus_cmd.py:76-78` (`pipe_io_contracts.json`, `input_form.json`, `output_form.json`), and one rendering function that maps a `PipeIOArtifacts` to `{filename: text}` using the corpus's byte discipline (`json.dumps(payload, indent=2, ensure_ascii=False)` plus a trailing newline, over `{pipe_ref: model.model_dump(mode="json")}`, `generate_projection_corpus_cmd.py:229-232`). The corpus command uses the same function, so for the same bundle a results directory and the committed fixture corpus hold byte-identical files.

The validate report keeps its flat fields; `PipeIOArtifacts` is the carrier, not a new report shape.

### 2. Built in the window, carried on the output

`PipeOutput` gains `pipe_io_artifacts: PipeIOArtifacts | None = None`, beside `graph_spec` (`pipelex/core/pipes/pipe_output.py:27`). It is set only on the top-level output, in the same place the graph is assembled:

- **Direct mode.** In `PipeRun.run`, right after `assemble_tracing_on_output`, when `pipe_output.graph_spec` is not `None`: `pipe_output.pipe_io_artifacts = build_pipe_io_artifacts(get_pipes())`, where `get_pipes()` (`pipelex/interpreter_hub.py:341`) enumerates the current run library. This runs inside `runner.execute`'s window, before the direct-mode delivery in the same `finally` and before the CLI receives the output. The build is best-effort in the same way the graph render is: a failure of the builders' own (`PipelexError`, or a `ValidationError` of a protocol model) leaves the field `None` and sets `pipe_output.pipe_io_artifacts_error` to the message, while any other exception surfaces as the bug it is, per the repository's exception policy; mirroring `graph_assembly_error` and `usage_assembly_error` on the same model, so a consumer can tell "graph tracing off" from "build failed"; it never fails a run that succeeded.
- **Temporal mode** is the plugin's twin, in `pipelex-server` (see "Consequences"): an activity that opens the transported crate's window, calls the same builder over the same enumeration and returns the model; the workflow stamps it onto the output before `act_deliver`, where it already stamps `graph_spec`.

The condition is the graphspec's own: the artifacts exist to describe a graphspec's data, so they are built when a graph is assembled *and* the run will write a graphspec (`graphs_inclusion.graphspec_json`), and not otherwise; the run setup stamps that as `describe_pipe_io` on the trace context, and validate's own graph dry run stamps it off, since validate already built the artifacts for its report and a second build would be thrown away. A run with graph tracing off has neither.

### 3. Every writer serializes them beside the graphspec

`GraphOutputs` (`pipelex/graph/graph_factory.py:27`) gains three optional text fields, `pipe_io_contracts_json`, `input_form_json`, `output_form_json`; `generate_graph_outputs` takes `pipe_io_artifacts: PipeIOArtifacts | None = None` and fills them, through the rendering function above, when **`graphs_inclusion.graphspec_json`** is on and artifacts were given. `save_graph_outputs_to_dir` writes them under the three constant names beside `graphspec.json`; `DeliveryExecutor._generate_graph_files` adds them through `_add_optional_text_file` beside its `graphspec.json`, so the hosted results prefix gains the same three keys. The two CLIs pass `pipe_output.pipe_io_artifacts` through.

Gating on `graphspec_json` is the item's own request and the right one: a run that asks for no graphspec writes nothing that describes one, and a caller that overrides the flag at render time (the agent CLI does, `_run_core.py:150-165`) gets the siblings with it. There is no new inclusion flag; the three files are the graphspec's companions, not a fourth graph output.

The agent CLI renames `graphspec.json` to `live_run_graph.json`; the siblings keep their canonical names beside it, because the VS Code reader resolves them from the graphspec's directory, not from its name.

### 4. The key set is the bundle's own pipes

Validate keys the artifacts by the validated bundle's pipes, and a run keys them the same way: every pipe of the library it executed against that the library holds under a bare `pipe_ref`, which is the entry bundle, its imports and any library directories, so a consumer that also drives a run form from `input_form` gets the method's other entry pipes too. A dependency package's pipes are left out, and the review round settled why: the library keys them `alias->domain.code`, the builders would key them by bare `pipe_ref` and silently overwrite a host pipe of the same name, and the host's crate holds no blueprint of theirs, so their descriptors would come out unknown anyway. Describing them properly is a deferred design of its own (see the plan's deferred items). The set is bounded by the method's own size. Pipes the runtime synthesizes at run time and never registers (the batch wrapper the item observed) are not described, and the renderer's undescribed-value view is the documented floor for those.

### 5. The SPI payload and the `/execute` response carry them

`PipelexPipeRunOutput` (`pipelex/runtime_bridge/payloads.py:64`, `extra="forbid"`) gains `pipe_io_artifacts_dump: dict[str, Any] | None = None`, filled by `serialize_completed_output` from `model_dump(mode="json")` like `graph_spec_dump`. `pipelex-api` rehydrates it in `_pipe_output_from_run_output` so the synchronous `/execute` response carries `pipe_output.pipe_io_artifacts` beside `pipe_output.graph_spec`. Wherever the run's graph travels, its description travels with it; a client that renders the `/execute` graph needs nothing else.

This is additive on every wire: an optional field with a `None` default on `PipeOutput`, on the SPI payload and in `pipelex-api`'s published OpenAPI artifact. `PipeOutput` is a distributed-execution wire model, and `pipelex` is pinned to one exact version across `pipelex-server`, so the field crosses the activity boundary the moment the pin moves; no reader on either side breaks on its absence.

## Alternatives rejected

- **Build at the write sites** (the item's proposal). Impossible as stated: the CLI writes after `runner.execute` has torn the library down, and the hosted delivery runs where the bundle may never have been loaded. Building there would mean reopening a library window at every writer, which the transport does deliberately not do for delivery.
- **Embed them in `GraphSpec`.** `GraphSpec` is `extra="forbid"` and standard-facing (`meta.format = "mthds"`); the fields would be a format change every reader must follow, the payloads are unrelated to the graph's shape, and the results layout already keeps one run's projections side by side. The `meta` bag is for format and mode. Embedding would not have avoided the window problem either.
- **Re-validate `mthds_contents` on the platform** when a run is viewed (the platform keeps the bundle that ran, and `/validate` accepts inline contents). It is hosted-only, so the local file layout that `vscode-pipelex` reads gains nothing; it costs a full validation and a second round trip per run view; and it describes the bundle text, not the library the run executed against, when the two diverge.
- **A private attribute on `PipeOutput`** (the `_job_metadata` pattern). It does not survive serialization, and the artifacts must cross the Temporal activity boundary to reach delivery.
- **A reference back to the bundle instead of the artifacts.** A local run's graphspec has no registry to resolve one against, and the hosted `Run` row has no method version to point at.
- **A fourth inclusion flag.** The files are the graphspec's companions; a run that writes a graphspec without them is the state this design ends.

## Consequences across repos

`pipelex` ships the model, the builder, the field, the SPI dump and the writers. The chain that consumes it, each a ledger item filed at ratification (ids in the plan's Phase 0):

- **`pipelex-api`** — at the pin bump, rehydrate `pipe_io_artifacts_dump` in `_pipe_output_from_run_output` and regenerate the committed OpenAPI artifact (`PipeOutputWire`, `api/schemas/models.py:370-381`, gated by `test_openapi_contract.py`).
- **`pipelex-server`, `temporal` member** — build the artifacts in the run's window and stamp them before delivery: an activity opening the crate's window (`scoped_library_for_crate`) and calling `build_pipe_io_artifacts` over the library's pipes, invoked from `_finish_run_root` beside `act_assemble_tracing`; the orchestrator's blocking mapping fills `pipe_io_artifacts_dump`. Sweep `transport/` for every site that copies `PipeOutput` fields by name (`prepare_output_for_transport`, `rehydrate_pipe_output_with_crate`) and carry the field. The plugin already imports the three builders for validation, so no new symbol enters the pinned transport surface; `PipeOutput` is already on it as a wire model, and the change is additive.
- **`pipelex-server`, `platform` member** — `GET /v1/runs/{id}/results` reads the three new keys beside the existing set and relays them on `RunResultsResponse`; an older run reads them as `null`, exactly as `tokens_usages.json` was introduced. `docs/specs/pipelex-platform-api.md` names the relayed file set and moves with it.
- **`pipelex-sdk-js`** — `RunResults` gains the three fields, typed from `mthds/protocol`.
- **`pipelex-app`** — pair a run's graph with the run's own artifacts when the results carry them, falling back to the buffer's validate only for a run that predates them.
- **`pipelex-mcp`** — pass the run's artifacts to `GraphViewer` in the run views.
- **`workspace` and `conformance`** — a short spec section on the results-directory layout (the sibling names, the `graphspec_json` gate, the "both or neither" rule for the contracts and the output form, the directory-not-name resolution the VS Code reader relies on) paired with a conformance test running `pipelex run` in dry-run mode over a corpus bundle. Filed rather than done here because it lives in two other repos and the test needs an installable release.
- **`vscode-pipelex`** — nothing: the reader is written against this layout and is blocked only on the producer.

## Questions settled at ratification

- **Should the synchronous `/execute` response carry the artifacts?** Decided yes, for the "wherever the graph travels" rule and because the cost is only paid when a graph is on. The alternative is to fill the SPI dump and stop there, leaving `/execute` clients to call `/validate`.
- **Should the key set be restricted to the pipes the graph references?** Decided no; the whole library is simpler, never falls short, and serves the run form too.
- **Should a build failure be reported on a field**, as `graph_assembly_error` reports a graph assembly failure? Decided yes at ratification: `pipe_io_artifacts_error`, the third instance of a pattern the model already carries twice, so a hosted failure is visible to the consumer that opens the graph and not only in a worker log nobody reads.
