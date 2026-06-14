# Missing Tests Menu

Source: full non-inference suite run with `--cov=pipelex` (overall ~78% line coverage after sections A–E were ground down — was ~72%) plus a structural sweep of `pipelex/` vs `tests/`. This is a curated menu of the gaps that matter, not an exhaustive list. Caveat: plugin inference workers' live-call paths are exercised by `inference`-marked tests that don't run in this measurement, so their numbers understate real coverage — only their offline-testable logic (factories, arg builders, error mapping) is listed here.

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

## C. Inference plumbing (offline-testable parts) — DONE (2026-06-12, see TODOS.md Phase C for the as-built notes)

Not the live calls — the factories, arg-builders, and config logic around them, which can break independently of any provider.

- [x] `cogt/img_gen/img_gen_args_factory.py` (58% → **100%**, ~320 stmts) — all provider taxonomies (Flux, Flux-1.1 Ultra, Qwen, SDXL/Lightning, GPT-image, BFL Flux 2) across aspect-ratio, prompt, inference, safety, output-format, input-images, and input-fidelity arg-building.
- [x] `cogt/llm/llm_worker_factory.py` (28% → **100%**) and `img_gen/img_gen_worker_factory.py` (40% → **99%**) — full SDK routing matrices, client-instance caching, missing-dependency errors; remainder = a `TYPE_CHECKING` import.
- [x] `cogt/llm/structured_output.py` (55% → **99%**) — every `StructureMethod` → instructor mode pinned with a completeness guard; remainder = a `TYPE_CHECKING` import.
- [x] `cogt/model_backends/backend_credentials.py` (30% → **100%**) — env vs generic-provider error messages, missing/placeholder var aggregation, report models.
- [x] `cogt/models/model_deck_check.py` (42% → **100%**) — every check function x every reference kind (found/not-found), fuzzy suggestions, wrong-sigil hints, setting short-circuits.
- [x] `plugins/gateway/gateway_completions_factory.py` (21% → **96%**) and `mistral_factory.py` (27% → **99%**) — client construction, message shaping, and the extract-output parsers (Azure/Mistral/Deepseek/Linkup; OCR responses, image cleanup, document prep/upload). Remainders = `TYPE_CHECKING` blocks, a defensive `except` reachable only if `model_dump` itself throws, and mistral's `make_mistral_client` retry wiring (already pinned by `test_transport_retry_wiring.py`).

## D. Core runtime odds and ends — DONE (2026-06-12, see TODOS.md Phase D for the as-built notes)

- [x] `observer/local_observer.py` (0% → **100%**) — constructor dir resolution, every observe method, JSONL append semantics, event-type collision behavior (originally pinned as payload-wins; the source was then fixed on this same branch so the lifecycle event name wins, and the pinning test flipped with it).
- [x] `core/pipes/output/output_renderer.py` (33% → **98%**) — Anything-output resolution through PipeCondition/PipeSequence (incl. recursion), operator arms, every Anything render format; remainder = the `TYPE_CHECKING` import block.
- [x] `graph/graph_rendering.py` (40% → **100%**) — `_dry_run_bundle` library-dirs matrix, format dispatch, the sanitized-rename branch, `generate_view_for_bundle` direction precedence.
- [x] `builder/bundle_spec.py` (34% → **100%**) and `builder/operations/inputs_ops.py` (20% → **98%**) — spec validation, `to_blueprint()` ordering/error wrapping, pretty rendering; every `build_inputs_for_pipe` branch. Remainder = a `TYPE_CHECKING` import. NB: the test phase surfaced a real source bug here (`ConceptSpec.model_validate_spec` crashed on plain-string concept values); it was fixed later on this same branch with the pinning tests flipped — see `deferred-source-bugs-pinned-by-tests.md` and the CHANGELOG `[Unreleased]` entry.
- [x] `pipeline/runner.py` (65% → **93%**) — `extra` rejection, both `except PipelexError` arms, `except ValidationError`, `start()`, and the protocol surfaces `validate()` (incl. the finally restore matrix), `models()`, `version()`. Remainder = the `TYPE_CHECKING` block plus the happy-path/`PipeRouterError`/tracer-close lines already pinned by the integration suite.

## E. Tools / config — DONE (2026-06-12, see TODOS.md Phase E for the as-built notes)

- [x] `tools/misc/toml_sync.py` (0% → **98%**) and `tools/misc/document_utils.py` (0% → **97%**) — toml_sync's full read/set/sync surface incl. the destroy-config guards (never creates keys, comment/structure preservation, dry-run, no-op write guard, idempotency); document format enum matrix. Remainders = a `TYPE_CHECKING` import, an unreachable defensive `continue`, and the type-checker-appeasement trailing `raise`.
- [x] `tools/storage/storage_config.py` (45% → **100%**) — per-provider `lazy_validate` fault matrices, provider-config validator, `uri_format`/`storage_path` properties. (The originally-pinned S3-vs-GCP `{hash}` asymmetry was then eliminated on this same branch: a shared config base validates every provider, local/in-memory included, each pinned by its own test module.)
- [x] `tools/misc/image_utils.py` (52% → **98%**) — format enum matrix, both unsupported-MIME message branches, PIL conversion round-trips; remainder = the unreachable trailing `raise`.

## Deliberately not on the menu

- CLI interface surfaces owned by `../conformance`: `init` (dedicated modules there), `validate` command wrappers, `--help` smoke tests, agent JSON output shapes. Rule of thumb: cross-repo contract behavior → conformance test paired with a spec section; pipelex-internal logic → here.
- `cli/dev_cli/*` (mostly 0%) — internal dev tooling, not shipped; low value per test.
- `plugins/*_list.py`, `huggingface_factory` (0%) — model-listing scripts hitting live APIs; belongs to inference-marked tests if anything.
- `pipelex.py` / `hub.py` (84%/83%) — already decent; remaining lines are teardown/edge accessors.
- Templating, input normalizer, URI resolver, reporting — explorer flagged them as thin on dedicated tests, but coverage shows they're well exercised (88–100%) via integration; dedicated unit tests would be redundant.

## Suggested grind order

1. ~~**A (CLI)**~~ — DONE 2026-06-12 (branch `feature/Add-tests`; plan + as-built notes in TODOS.md).
2. ~~**B (Temporal)**~~ — DONE 2026-06-12 (user-prioritized ahead of C; same branch, TODOS.md Phase B).
3. ~~**C (inference plumbing)**~~ — DONE 2026-06-12 (same branch, TODOS.md Phase C).
4. ~~**D then E**~~ — DONE 2026-06-12 (same branch, TODOS.md Phases D and E).

All menu sections are complete. Remaining gaps are deliberate (see "Deliberately not on the menu") plus the per-module remainders noted inline above (TYPE_CHECKING blocks, interface-layer wrappers, integration-pinned lines).
