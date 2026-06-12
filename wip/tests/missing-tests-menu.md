# Missing Tests Menu

Source: full non-inference suite run with `--cov=pipelex` (overall ~75% line coverage after section A was ground down — was ~72%) plus a structural sweep of `pipelex/` vs `tests/`. This is a curated menu of the gaps that matter, not an exhaustive list. Caveat: plugin inference workers' live-call paths are exercised by `inference`-marked tests that don't run in this measurement, so their numbers understate real coverage — only their offline-testable logic (factories, arg builders, error mapping) is listed here.

## A. CLI internal logic — DONE (2026-06-12, see TODOS.md for the as-built notes)

Scope note: the spec'd CLI *interface* (arg parsing, `--help` surfaces, `init` behavior, `validate --all`, agent JSON output shapes) is owned by `../conformance` (paired with `docs/specs/`) — not duplicated here. This section is only the pipelex-internal logic those commands run, which conformance's subprocess-level tests never reach (and which doesn't count toward conformance coverage anyway). All testable offline with Typer's `CliRunner` or direct calls into the `_core` modules.

- [x] `cli/commands/doctor_cmd.py` (21% → **92%**, ~600 stmts) — all diagnostic checks, fix mode, health-report rendering covered; remainder ≈ `setup_doctor_runtime` (once-per-process log.configure side effects, deliberately untested).
- [x] `cli/commands/run/_run_core.py` (32% → **94%**) — happy path, bundle/inputs resolution, output saving (graphs/main_stuff/working-memory/CSV), wrapper error dispatch.
- [x] `cli/commands/show_cmd.py` (27% → **73%**) and `which_cmd.py` (27% → **66%**) — the `do_*` report logic is fully covered; the remainder is the Typer wrappers that boot Pipelex (interface layer, conformance-owned).
- [x] `cli/commands/build/*` internals (`_output_core` 41→**74%**, `_runner_core` 21→**76%**, `_inputs_core` 21→**72%**, `structures_cmd` 41→**69%**) — codegen cores covered; remainder is the Typer command wrappers. NB: these tests live in `tests/unit/pipelex/cli/commands/build/`, which pytest's default `norecursedirs` silently skipped until the pyproject override (defaults minus `build`) — the pre-existing cross-package refines regression test there had never been running.
- [x] `cli/readiness.py` (20% → **97%**) — venv detection, dev-install detection, and the readiness gate.
- [x] `cli/error_handlers.py` (51% → **99%**, ~290 stmts) — every handler incl. gateway/telemetry/signature ones, panel rendering, validation-error detail sections.

## B. Temporal distributed execution — DONE (2026-06-12, see TODOS.md Phase B for the as-built notes)

Never shipped to prod yet, but these are the deploy-critical entry points; bugs here only surface inside a live cluster.

- [x] `temporal/worker_cli.py` (0% → **100%**) — project resolution from pyproject, fast-fail task-queue validation before library load, worker-base library loading, forced `is_enabled`, full Typer arg wiring into the worker loop.
- [x] `temporal/codec/codec_server.py` (0% → **96%**) — encode/decode round-trip over real HTTP, CORS preflight/origin gating, content-type and malformed-payload guards, storage-failure → HTTP status mapping; remainder = the `TYPE_CHECKING` import block. NB: `codec_server_cli.py` stays at 0% — it's the thin arg-parse + `run_app` wrapper around `build_codec_server`, same interface-layer category as the Typer wrappers left out in section A.
- [x] `temporal/temporal_connect.py` (24% → **98%**) — API-key resolution per secret method, TLS/RPC-metadata wiring, payload-codec converter selection, named server-config selection, SDK error wrapping; remainder = the `TYPE_CHECKING` import block.

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

1. ~~**A (CLI)**~~ — DONE 2026-06-12 (branch `feature/Add-tests`; plan + as-built notes in TODOS.md).
2. ~~**B (Temporal)**~~ — DONE 2026-06-12 (user-prioritized ahead of C; same branch, TODOS.md Phase B).
3. **C (inference plumbing)** — pure-function factories, fast unit tests, protects the money path. ← NEXT
4. **D then E** — fill-in work, good for small sessions.
