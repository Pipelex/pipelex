---
status: active
item: L-260907-817d80
---

# Plan: a run's results carry the I/O artifacts that describe its data

The design is [`design.md`](./design.md). This tracker is the implementation order for the `pipelex` half, the checkpoints where a session hands off, and the downstream chain that follows the release.

Working rules for every phase: tests before implementation; `make agent-check` with the changes staged after every code change; `make agent-test` before a checkpoint; if `make drift-check` opens a contract, resolve it with `/drift-review` rather than around it.

## Phase 0 — Ratification and the downstream filing

- [x] The design is read and ratified on 2026-09-07; its frontmatter and this plan flip to `active` in the same change. The four calls: build in the run window and carry on `PipeOutput`; the `/execute` response carries the artifacts; a build failure is reported on `pipe_io_artifacts_error`; the spec and conformance half is filed, not done here.
- [x] The downstream ledger items are filed, each discovered from and blocked by L-260907-817d80 (no release item exists yet; the release that carries the field is what unblocks them in practice): `pipelex-api` L-260907-c772e9 (rehydrate the dump, regenerate OpenAPI), `pipelex-server` `temporal` L-260907-2ad3d8 (the in-window activity and the orchestrator dump, with the `transport/` sweep of every by-name `PipeOutput` copy), `pipelex-server` `platform` L-260907-682a2b (relay the three files on run results, and move `docs/specs/pipelex-platform-api.md` with it), `pipelex-sdk-js` L-260907-b7b9b1 (`RunResults` fields), `pipelex-app` L-260907-b22bad (pair a run's graph with its own artifacts), `pipelex-mcp` L-260907-16d2c6 (pass them to the run views), `workspace` L-260907-f6fd8d (the results-directory spec section and its conformance test).
- [x] Recorded on L-260907-817d80 that the item's proposed hook is outside the library window, with the two evidence sites (the log entry of 2026-09-07).

## Phase 1 — The model and the builder

Modules: `pipelex/core/pipes/pipe_io_artifacts.py` (the carrier, the filenames and the rendering, importing only the protocol package so `PipeOutput` can import it; it lives under `core/` because `PipeOutput` is kernel-layer and the kernel-layer closure tests refuse an import from `pipelex/pipeline/`, where the first cut placed it) and `pipelex/pipeline/build_pipe_io_artifacts.py` (the builder, which needs the library machinery). One module was the first cut and imported circularly through `PipeOutput`; the split is the plain fix.

- [x] Tests first: `tests/unit/pipelex/core/pipes/test_pipe_io_artifacts.py` (the model forbids extras and round-trips; the rendering yields the three filenames with the corpus's byte discipline, `ensure_ascii=False` proven with a non-ASCII description) and `tests/integration/pipelex/pipeline/test_pipe_io_artifacts.py` (the builder equals the three builders in sequence on the probe bundle, with and without a caller-held qualification, and the three maps share one key set).
- [x] `PipeIOArtifacts` (`extra="forbid"`, the three fields under the report's names and types), `build_pipe_io_artifacts(pipes, *, qualified_crate=None)`, the three filename constants, and `render_pipe_io_artifact_files`.
- [x] `validate_bundles_in_process` builds through `build_pipe_io_artifacts` and spreads into `build_validation_report`; the report's flat fields do not change. The two tests that patched the old builders at the orchestrator's namespace now patch the builder module.
- [x] `generate_projection_corpus_cmd.py` renders through `render_pipe_io_artifact_files` and its own filename constants are gone (the corpus test imports them from the artifacts module). Regenerated the corpus with the four bundles in the README's order and compared against `mthds-python/tests/fixtures/protocol/`: the three files and the whole `inputs_template/` tree are byte-identical.
- [x] The `trace_input_semantics` command keeps calling the builders directly: it traces hops, and its hop files are a separate discipline.

## Phase 2 — Built in the window, carried on the output

- [x] Tests first (`tests/integration/pipelex/pipeline/test_direct_pipe_io_artifacts.py`, `tests/unit/pipelex/runtime_bridge/test_output_serialization.py`): a `PipeRun.run` test that runs a small bundle with graph tracing on and asserts `pipe_output.pipe_io_artifacts` is set, keyed by every `pipe_ref` in `graph_spec.pipe_registry`, and is `None` when graph tracing is off; a test that a builder raising leaves the field `None`, sets `pipe_io_artifacts_error` to the message and keeps the run successful (patch the builder on the module, not the instance); a serializer test that `serialize_completed_output` fills `pipe_io_artifacts_dump` and leaves it `None` when the output has none.
- [x] `PipeOutput.pipe_io_artifacts: PipeIOArtifacts | None = None` and `pipe_io_artifacts_error: str | None = None` beside `graph_spec` and `graph_assembly_error`.
- [x] `PipeRun.run`: after `assemble_tracing_on_output`, when graph events were on and a graph was assembled, `_build_pipe_io_artifacts_on_output` builds over `get_pipes()` inside the same `finally`, before the direct-mode delivery; any exception sets `pipe_io_artifacts_error` and logs a warning (a blind except, deliberately: a description must never fail a completed run).
- [x] `PipelexPipeRunOutput.pipe_io_artifacts_dump` and `pipe_io_artifacts_error`, filled by `serialize_completed_output`.
- [x] Swept `pipelex` for sites rebuilding a `PipeOutput` field by field: none carries `graph_spec` (the controllers build sub-outputs with a working memory only), so nothing to carry. The by-name copies live in `pipelex-server/transport/`, which is L-260907-2ad3d8.

## Phase 3 — Every writer serializes them beside the graphspec

- [x] Tests first, extending `tests/unit/pipelex/graph/test_graph_output_generation.py` and `tests/unit/pipelex/pipe_run/test_delivery_executor.py` (with a shared hand-built artifacts fixture in `tests/helpers/pipe_io_artifacts.py`): `generate_graph_outputs` fills the three texts when `graphspec_json` is on and artifacts are given, none when the flag is off, none when artifacts are `None`; `save_graph_outputs_to_dir` writes the three files beside `graphspec.json` and returns their keys; `generate_result_files` emits the three `ResultFile` entries when the output carries artifacts and omits them otherwise, on both the typed and the raw working-memory branches.
- [x] `GraphOutputs` fields, the `pipe_io_artifacts` parameter on `generate_graph_outputs`, `save_graph_outputs_to_dir`, `DeliveryExecutor._generate_graph_files`.
- [x] `pipelex run` and `pipelex-agent run` pass `pipe_output.pipe_io_artifacts`; the agent CLI's `graph_files` side-effect map names the three paths beside `graph_spec`. Both verified by hand on the probe bundle in dry mode.
- [x] `tests/integration/pipelex/pipeline/test_run_artifacts_parity.py`, the design's promise: for one corpus bundle, the file a run writes equals the corpus's committed file for that bundle, byte for byte, and its parsed value equals the corresponding field of the report `validate_bundles_in_process` returns for the same bundle.
- [x] `tests/e2e/pipelex/cli/test_run_artifacts_beside_graphspec.py`, an end-to-end CLI test: `pipelex run` on a bundle with a graph, in dry-run mode so no inference is needed, leaves a results directory with `graphspec.json` and the three siblings, each parsing as a JSON object keyed by `pipe_ref`.

### Checkpoint 1

The runtime half is complete when Phases 1 to 3 are green under `make agent-check` and `make agent-test`, and `make test-ts-gates` if anything under `pipelex/codegen/emitters/` was touched (it should not have been). Record here: the decisions taken, anything left out, and the state of the parity test.

Reached on 2026-09-07. `make agent-check` is green. Decisions beyond the design: the carrier and the builder are two modules (see Phase 1); the run's failure catch is blind, with the reason on the `except` line; the delivery executor writes the companions on both the typed and the raw working-memory branches, since the artifacts are already built and need no class registry. Left out: nothing under `pipelex/codegen/emitters/` moved, so `make test-ts-gates` was not run. The parity test compares per pipe and asserts byte identity only when the run library's key set equals the validated bundle's, which it does for the probe bundle in the test harness.

## Phase 4 — Documentation, changelog, specification

- [x] `docs/under-the-hood/execution-graph-tracing.md`: the outputs table gains the three siblings, gated by `graphspec_json`; the delivery paragraph names them beside `tokens_usages.json`; the configuration listing's comment on `graphspec_json` says the siblings follow it.
- [x] `docs/tools/cli/run.md`: what a results directory holds, and that the three files describe the graphspec's data for a graph viewer.
- [x] The agent CLI's run documentation (`docs/tools/cli/agent-cli.md`, Graph Visualization) and its contract doc (`pipelex/cli/agent_cli/CLAUDE.md`) name the siblings and the `graph_files` keys; the `cli-docs` drift contract was acked with that review.
- [x] `CHANGELOG.md`, Unreleased, Added: one condensed entry — what a run's results now carry, that `PipeOutput` and the `/execute` response carry `pipe_io_artifacts` beside `graph_spec`, that the hosted results prefix gains the three keys, and that the fixture corpus is unchanged.
- [x] The workspace `docs/specs/` section and its conformance test are L-260907-f6fd8d, filed at ratification: they live in two other repos and the test needs an installable release. The transport-boundary spec's wire-model table needs no row: `PipeOutput` is already on it.
- [x] `make check-rules` is not touched by this work; no agent-rules source changed.

## Phase 5 — Landing and the downstream chain

- [ ] `/rev` at the derived profile before the pull request; the PR body carries `Closes L-260907-817d80`.
- [ ] After the merge, `/ledger-land`; the release that carries the change is what unblocks the downstream items filed in Phase 0, and the `pipelex-server` pin bump is the moment the Temporal twin lands — until then a hosted run writes `graphspec.json` without its siblings, and the platform relays nothing new.
- [ ] `vscode-pipelex` L-260906-e9ab24 verifies end to end against a real `pipelex run` results directory once the release is installable.

## Deferred from the review round

Findings of the round-1 `/rev` pass at profile 4 (2026-09-07) that are real but not this campaign's to fix. Each is a candidate for its own item once a consumer asks for it.

- **`pipe_io_artifacts_error` never reaches a delivered results prefix.** The delivery executor writes the three companions when the output carries them and nothing when it does not, so a hosted consumer cannot tell "graph tracing off" from "build failed" the way `tokens_usages.json` lets it tell for usage. The ratification rationale for the field was hosted visibility. The fix is a small marker beside the graphspec carrying the error, but its name is a new contract for the readers (`vscode-pipelex`, `pipelex-app`), so it waits for the spec item L-260907-f6fd8d to name it.
- **The agent CLI's live and dry runs share one companion set.** `live_run_graph.json` and `graphspec.json` sit in the same directory with one `input_form.json`; editing the bundle between a live run and a dry run leaves the older graph described by the newer declarations, exactly as `live_run.json` itself goes stale. Per-graph snapshots are a change to the agent CLI's file layout, not to this feature.
- **The artifacts describe declared output, not a step's effective `output_multiplicity`.** A `PipeLLM` declared `Text` and run with `output_multiplicity=2` returns a list while its contract says single. The validate report has the same property, and the graph viewer already lives with it; describing effective invocations is a change to the contracts themselves.
- **Describing dependency pipes.** Left out of the key set (design §4). Doing it needs the dependency's own qualified crate and alias-aware keys in the three artifacts, which is a protocol question before it is a runtime one.
- **Payload growth.** `pipe_io_artifacts` rides `PipeOutput` across the Temporal activity boundary and `pipe_io_artifacts_dump` rides the SPI payload for every graphspec-writing run. Measure a serialized `PipeOutput` on a large real method before the `pipelex-server` pin moves; Temporal's payload limit does not fail cleanly.

## Live state

Decisions taken so far are in the design's "Decision" and "Questions settled at ratification" sections. Phases 0 to 4 are implemented in the worktree on `feature/Run-artifacts-beside-graphspec`, from `pipelex` `dev` as of the commit that added the compact Commands rules; Checkpoint 1 below records the state at the end of Phase 4, and the review round that followed narrowed the build to the bundle's own pipes, gated it on `graphspec_json` through `describe_pipe_io` on the trace context, and made a written graphspec remove stale companions. What remains is Phase 5.
