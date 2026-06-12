# Missing Tests Menu

Source: full non-inference suite run with `--cov=pipelex` (overall ~72% line coverage) plus a structural sweep of `pipelex/` vs `tests/`. This is a curated menu of the gaps that matter, not an exhaustive list. Caveat: plugin inference workers' live-call paths are exercised by `inference`-marked tests that don't run in this measurement, so their numbers understate real coverage — only their offline-testable logic (factories, arg builders, error mapping) is listed here.

## A. CLI internal logic — highest leverage

Scope note: the spec'd CLI *interface* (arg parsing, `--help` surfaces, `init` behavior, `validate --all`, agent JSON output shapes) is owned by `../conformance` (paired with `docs/specs/`) — not duplicated here. This section is only the pipelex-internal logic those commands run, which conformance's subprocess-level tests never reach (and which doesn't count toward conformance coverage anyway). All testable offline with Typer's `CliRunner` or direct calls into the `_core` modules.

- `cli/commands/doctor_cmd.py` (21%, ~600 stmts) — the diagnostic *checks* themselves (conformance only smoke-tests `--help`); if doctor breaks, users are stranded when things go wrong.
- `cli/commands/run/_run_core.py` (32%) — the main `pipelex run` execution logic; happy path + error paths barely covered.
- `cli/commands/show_cmd.py` (27%) and `which_cmd.py` (27%) — the report *content* (not the interface); cheap to test, pure output formatting.
- `cli/commands/build/*` internals (`_output_core`, `_runner_core`, `_inputs_core`, `structures_cmd` — 21–41%) — the codegen logic behind the spec'd build interface; silent breakage corrupts generated projects.
- `cli/readiness.py` (20%) — gates whether the CLI considers itself usable; wrong answer blocks everything.
- `cli/error_handlers.py` (51%, ~290 stmts) — how every CLI error is shaped for the user; untested branches mean ugly tracebacks instead of friendly messages.

## B. Temporal distributed execution — operational risk

Never shipped to prod yet, but these are the deploy-critical entry points; bugs here only surface inside a live cluster.

- `temporal/worker_cli.py` (0%) — the worker process entry point; a broken arg parse = fleet-wide dead workers.
- `temporal/codec/codec_server.py` (0%) — payload codec HTTP server; failure corrupts/blocks all payload decoding in the UI.
- `temporal/temporal_connect.py` (24%) — connection/TLS/API-key wiring; the kind of code that only fails at deploy time.

## C. Inference plumbing (offline-testable parts)

Not the live calls — the factories, arg-builders, and config logic around them, which can break independently of any provider.

- `cogt/img_gen/img_gen_args_factory.py` (58%, ~320 stmts) — maps user settings to per-provider image-gen args; wrong mapping = silently wrong generations or API rejects.
- `cogt/llm/llm_worker_factory.py` (28%) and `img_gen/img_gen_worker_factory.py` (40%) — worker selection/dispatch; wrong route = wrong backend.
- `cogt/llm/structured_output.py` (55%) — structured-output schema handling; errors here corrupt every structured generation.
- `cogt/model_backends/backend_credentials.py` (30%) — credential resolution; failure modes should be tested, not discovered by users.
- `cogt/models/model_deck_check.py` (42%) — deck validation; the guard that catches bad model configs.
- `plugins/gateway/gateway_completions_factory.py` (21%) and `mistral_factory.py` (27%) — request-shaping for our recommended (gateway) and a major BYOK backend; pure functions, easy to unit test.

## D. Core runtime odds and ends

- `observer/local_observer.py` (0%) — the only fully untested observer implementation; observers run inside every pipeline execution, a raise here breaks runs.
- `core/pipes/output/output_renderer.py` (33%) — renders final pipe outputs; wrong rendering = users see wrong results even when execution was correct.
- `graph/graph_rendering.py` (40%) — top-level graph render dispatch (the mermaid/reactflow internals are covered; this orchestrator isn't).
- `builder/bundle_spec.py` (34%) and `builder/operations/inputs_ops.py` (20%) — agent-authoring spec layer; `to_blueprint()` transforms feed everything the builder emits.
- `pipeline/runner.py` (65%) — uncovered branches are mostly error/edge paths in the main execution loop; worth targeted (not blanket) tests.

## E. Tools / config

- `tools/misc/toml_sync.py` (0%) and `tools/misc/document_utils.py` (0%) — completely untested utilities; toml_sync edits config files, a bug destroys user config.
- `tools/storage/storage_config.py` (45%) — storage backend selection (local/S3); misconfig paths untested.
- `tools/misc/image_utils.py` (52%) — image conversion used across pipe operators.

## Deliberately not on the menu

- CLI interface surfaces owned by `../conformance`: `init` (six dedicated modules there), `validate` command wrappers, `--help` smoke tests, agent JSON output shapes. Rule of thumb: cross-repo contract behavior → conformance test paired with a spec section; pipelex-internal logic → here.
- `cli/dev_cli/*` (mostly 0%) — internal dev tooling, not shipped; low value per test.
- `plugins/*_list.py`, `huggingface_factory` (0%) — model-listing scripts hitting live APIs; belongs to inference-marked tests if anything.
- `pipelex.py` / `hub.py` (84%/83%) — already decent; remaining lines are teardown/edge accessors.
- Templating, input normalizer, URI resolver, reporting — explorer flagged them as thin on dedicated tests, but coverage shows they're well exercised (88–100%) via integration; dedicated unit tests would be redundant.

## Suggested grind order

1. **A (CLI)** — biggest user-facing risk, cheapest to write (CliRunner, no inference), huge statement count payoff.
2. **C (inference plumbing)** — pure-function factories, fast unit tests, protects the money path.
3. **B (Temporal)** — before the integration ships to prod.
4. **D then E** — fill-in work, good for small sessions.
