# TODOS — Test coverage grind

Source plan: [wip/tests/missing-tests-menu.md](wip/tests/missing-tests-menu.md). This file is the working plan; when a section is done, update the menu doc's matching section with the evolved coverage percentages. Section A (CLI internal logic) is complete — see Checkpoint 3. Current work: Phase B = menu section B (Temporal distributed execution).

## Context for cold start

- **Branch:** `feature/Add-tests` in the `_tests` worktree (treat `_tests/` as repo root; do not look in `pipelex/` sibling).
- **Goal:** unit tests for pipelex-internal CLI logic. The CLI *interface* (arg parsing, `--help`, agent JSON shapes) is owned by `../conformance` — do NOT duplicate it. We test the `_core` functions and check/report logic directly.
- **Where tests go:** `tests/unit/pipelex/cli/` (existing dir, has `conftest.py` with autouse fixtures `reset_traceback_requested` and `reset_agent_cli_error_format`). Build-command tests go in `tests/unit/pipelex/cli/commands/build/`.
- **Established patterns** (read these before writing tests):
  - `tests/unit/pipelex/cli/test_doctor_cmd.py` — mocking `config_manager` via `mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, ...)`, real TOML files in `tmp_path`.
  - `tests/unit/pipelex/cli/test_traceback_flag_run_core.py` — driving the async `_execute_run()` with a `_run_async()` helper, mocking `get_console()`, `get_config()`, `PipelexMTHDSProtocol`.
  - `tests/unit/pipelex/cli/test_error_handlers_snapshot.py` — pinning Rich panel output with `Console(width=80, record=True, color_system=None)` + `export_text()`.
  - Booted-library fixtures: `load_empty_library` / `load_test_library` from `tests/conftest.py` (module-scoped `Pipelex.make()` via `reset_pipelex_config_fixture`).
- **Run tests locally:** `.venv/bin/pytest -x -q tests/unit/pipelex/cli/` (fine for iteration); full gate at end = `make agent-check` then `make agent-test`.
- **Coverage measurement** (to update the menu doc — must match how baseline was measured, i.e. the full non-inference suite):
  `.venv/bin/pytest -n auto -m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)" --cov=pipelex --cov-report=term | grep -E "cli/|TOTAL"`
  Cheaper per-module proxy during iteration: `.venv/bin/pytest -q tests/unit/pipelex/cli --cov=pipelex.cli --cov-report=term-missing`.
- **House rules:** TDD where it makes sense; never hardcode counts in comments/docs; `make agent-check` after code changes; tests must be offline (no inference marks needed here).
- **Pytest standards (`.claude/rules/pytest-standards.md`):** ONE TestClass per test module (so e.g. doctor tests split across several `test_doctor_*.py` files); pytest-mock (`MockerFixture`) only, never unittest.mock; strong asserts on values; parametrize multiple cases; variable names ≥3 chars.

## Phase 1 — `cli/readiness.py` (baseline 20%)

Small, self-contained, zero existing tests. New file `tests/unit/pipelex/cli/test_readiness.py`.

- [x] `_is_in_virtual_environment()`: venv (sys.prefix != base_prefix), conda env var, VIRTUAL_ENV env var, none → False (monkeypatch `sys.prefix`/env)
- [x] `_find_venv_directories()`: finds `.venv`/`venv` with `bin/python` in cwd + parents, ignores dirs without `bin/python`, empty result (monkeypatch cwd to tmp_path)
- [x] `_is_development_install()`: `.git` in parents → True, none → False, AttributeError/OSError → False
- [x] `check_readiness()`: dev+venv passes silently; production passes; dev+no-venv raises `ReadinessCheckError` with activation instructions (venvs found) vs creation instructions (none found)

## Phase 2 — `cli/error_handlers.py` (baseline 51%)

Extend `tests/unit/pipelex/cli/test_error_handlers.py` (or new `test_error_handlers_more.py`). Pattern: recorded Console, assert exit code 1 + key phrases in exported text. Untested handlers are the gateway/telemetry/signature ones.

- [x] `display_error_panel()`: basic render, no error_message, multi-line tip, links, special chars escaped
- [x] `handle_model_deck_preset_error()`: with/without user_action_detail (auto-built "Possible solutions" tip), with/without enabled_backends
- [x] `handle_validate_bundle_error()` + `_display_validation_error_details()`: blueprint errors / pipe errors / dry-run error / signature check error sections, with and without bundle_path, empty lists skip sections
- [x] `handle_signatures_not_allowed_error()`: exit 1 + `--allow-signatures` tip
- [x] `handle_telemetry_config_validation_error()`: exit 1 + migration guidance
- [x] `handle_gateway_terms_not_accepted_error()`, `handle_gateway_api_key_missing_error()`, `handle_gateway_do_not_track_conflict_error()`: exit 1 + expected guidance
- [x] `handle_remote_config_validation_error()` ("Please report this!"), `handle_remote_config_unavailable_error()` (offline guidance)
- [x] `handle_gateway_unknown_model_error()`: FRESH vs CACHED source branches

## Phase 3 — `show_cmd.py` + `which_cmd.py` (baseline 27% each)

New files `tests/unit/pipelex/cli/test_show_cmd.py`, `test_which_cmd.py`. Test the `do_*` functions directly (not the Typer wrappers — wrappers boot Pipelex; mock hub getters instead).

- [x] `do_show_config()`: loads config via config_manager, pretty-prints
- [x] `do_list_pipes()`: calls `get_pipe_library().pretty_list_pipes()`
- [x] `do_show_pipe()`: found → pretty print
- [x] `do_show_backends()`: enabled-only vs `show_all=True` (Status column), no backends → warning, routing-profile display, markup-escape path
- [x] `do_which_pipe()`: found (search path + source label, returns True), not found (returns False, tip shown), empty library_dirs, non-existent dirs marked

### CHECKPOINT 1 — small modules done

Status: **CLEARED 2026-06-12.** New files: `test_readiness.py`, `test_error_handlers_more.py`, `test_show_cmd.py`, `test_which_cmd.py`. CLI unit dir fully green; `make agent-check` clean. Coverage (unit-cli-dir proxy, lower bound vs full suite): readiness 20→97%, error_handlers 51→99%, show_cmd 27→73%, which_cmd 27→66% (remainder in both = the Typer wrappers that boot Pipelex — interface layer, conformance-owned). Decisions: tested `do_*` functions directly with hub getters mocked at the command-module namespace; SimpleNamespace for backend/routing-profile stand-ins; recorded `Console(record=True, color_system=None)` + `export_text()` for output assertions (width 300 for which_cmd to avoid path wrapping); markup-escape path triggered via a mismatched closing tag (`bad[/bold]name`) — an unclosed tag does NOT raise MarkupError.

## Phase 4 — `doctor_cmd.py` (baseline 21%, ~600 stmts — biggest payoff)

Extend `tests/unit/pipelex/cli/test_doctor_cmd.py` with new test classes (keep existing `TestDoctorLayeredResolution` untouched). The check functions return `(healthy, ..., message)` tuples — assert on those, not console output. Existing mocking pattern: ConfigLoader property mocks + real TOML files in tmp_path.

- [x] `check_config_files()`: missing files counted; pipelex.toml ValidationError; ConfigValidationError; TomlError; OSError; all-good path
- [x] `check_telemetry_config()`: file not found; TomlError; valid new format; old-format detection ("format has changed"); invalid new format
- [x] `check_backend_credentials()`: backends.toml missing; all creds valid; missing env var; placeholder value; internal backend skipped; disabled backend skipped; broad-exception path
- [x] `check_backend_files()`: no backends dir; no backends.toml; TomlError; valid file; InferenceBackendLibraryError captured per-file; has_kit_template True/False
- [x] `check_kit_template_exists()` + `replace_backend_file()`: template exists/missing/exception→False; replace happy path writes file; dry_run doesn't write; missing template → False
- [x] `check_deck_sync()`: deck dir missing → healthy; clean deck; dirty deck w/ version mismatch message; manifest missing
- [x] `gather_config_location()`: project-local vs global
- [x] `check_models()`: backend files unhealthy short-circuit; gateway disabled happy path; gateway enabled but service config missing / terms not accepted; remote fetch failure; deck validation error path
- [x] `do_doctor_cmd()` fix mode: config fix → init_cmd(focus=CONFIG); telemetry fix; deck fix → update_cmd(yes=True); backend file replace accepted/declined (mock `Confirm.ask`)

## Phase 5 — `run/_run_core.py` (baseline 32%)

Extend alongside `test_traceback_flag_run_core.py` patterns (new file `tests/unit/pipelex/cli/test_run_core.py`). Mock `PipelexMTHDSProtocol`, `get_config`, `get_console`; use tmp_path for outputs.

- [x] `_execute_run()` happy path: pipe executes, recap printed
- [x] Bundle with main_pipe used when no pipe_code; bundle without main_pipe → Exit(1); no bundle + no pipe_code → Exit(1)
- [x] Inline JSON inputs success; file inputs success (resolve_inputs_paths called); non-dict file JSON → Exit(1)
- [x] Output saving: graphs dir, main_stuff JSON/MD/HTML, working memory JSON (assert files exist in tmp_path)
- [x] CSV branches: happy flat-list save; empty `--save-csv` path → Exit(1); bad suffix → Exit(1); no main_stuff → Exit(1); non-flat output → Exit(1)
- [x] `execute_run()` wrapper: setup/teardown called; `PipeOperatorModelChoiceError` → `handle_model_choice_error`; `PipeOperatorModelAvailabilityError` → handler; `typer.Exit` passthrough

### CHECKPOINT 2 — doctor + run core done

Status: **CLEARED 2026-06-12.** Doctor tests split across one-class-per-module files: `test_doctor_config_checks.py`, `test_doctor_backend_checks.py`, `test_doctor_deck_sync.py`, `test_doctor_check_models.py`, `test_doctor_fix_mode.py`, `test_doctor_display_report.py` (display rendering + the doctor_cmd outer error guard). Run core in `test_run_core_execution.py` + `test_run_core_wrapper.py`. Coverage (unit-cli-dir proxy): doctor_cmd 21→92% (remainder ≈ setup_doctor_runtime, deliberately untested — once-per-process log.configure side effects, existing tests stub it), _run_core 32→94%. Decisions: check functions tested via explicit `config_dir=tmp_path` (resolve_config_file bypasses layering) with real TOML files; check_models decision tree tested with all collaborators mocked at the doctor module namespace (ModelManager, RemoteConfigFetcher, gateway probes); fix mode mocks `doctor_cmd.Confirm.ask` + init_cmd/update_cmd/replace_backend_file; runner mocked via `mocker.AsyncMock` on `PipelexMTHDSProtocol.execute` returning `SimpleNamespace(pipe_output=...)`; pipe_output is a SimpleNamespace with a MagicMock working_memory; render_cost_report_for_output mocked away; CSV happy path mocks flat_field_names + csv_from_list_content but uses a real ListContent for the isinstance check. All green incl. `make agent-check`.

## Phase 6 — `build/*` internals (baseline 21–41%)

New files under `tests/unit/pipelex/cli/commands/build/`. Existing reference: `test_structures_cmd_cross_package_refines.py` (calls `generate_structures_from_blueprints()` directly with tmp output dir).

- [x] `structures_cmd.py`: `_compute_relative_path_from_output_dir()` (inside/outside/equal cwd); `_build_concept_ref_to_class_info()` (skips native domain, qualified names, module paths); `generate_structures_from_blueprints()` (string concept → TextContent; explicit structure; refines native; refines custom qualified; default; `__init__.py` written; skip-existing check; quiet flag)
- [x] `_inputs_core.py`: bundle main_pipe vs explicit pipe_code vs neither → Exit(1); output path defaulting (bundle parent vs results dir); `NoInputsRequiredError` → exit 0 with message; happy path writes JSON
- [x] `_output_core.py`: same pipe/bundle resolution matrix; output path defaulting per format (json/py); happy path writes rendered output; render failure → Exit(1)
- [x] `_runner_core.py`: structures generated + classes registered; runner code generated to `run_{pipe_code}.py` default path; explicit output_path wins; no bundle → Exit(1)

## Phase 7 — Wrap-up

- [x] `make agent-check` clean
- [x] `make agent-test` green (full suite)
- [x] Run the full-suite coverage measurement (command above) and capture new per-module percentages
- [x] Update `wip/tests/missing-tests-menu.md` section A lines with evolved coverage %s (mark items done/improved)
- [x] Update this file's checkpoint statuses; changelog entry if warranted

### CHECKPOINT 3 — section A complete

Status: **CLEARED 2026-06-12 — SECTION A COMPLETE.** Full non-inference suite green with `--cov` (same marker expression as `make agent-test`, run without `--exitfirst` — strictly stronger); `make agent-check` clean; changelog [Unreleased] entry added. Final full-suite coverage (written into the menu doc): doctor_cmd 21→92, _run_core 32→94, show_cmd 27→73, which_cmd 27→66, _output_core 41→74, _runner_core 21→76, _inputs_core 21→72, structures_cmd 41→69, readiness 20→97, error_handlers 51→99; overall pipelex ~72→75%. **Bug found & fixed along the way:** pytest's default `norecursedirs` includes `build`, so everything under `tests/unit/pipelex/cli/commands/build/` was silently skipped in full runs — including the pre-existing cross-package refines regression test, which had never been running. Fixed via a `norecursedirs` override in pyproject.toml `[tool.pytest]` (defaults minus `build`). Phase 6 build-core tests mock the registry getters at the module namespace so the module-scoped Pipelex's real class/func registries are never torn down. NEXT menu section: **C — inference plumbing** (pure-function factories: img_gen_args_factory, llm/img_gen worker factories, structured_output, backend_credentials, model_deck_check, gateway/mistral completions factories).

## Phase B — Temporal distributed execution (menu section B)

User-prioritized ahead of section C. Deploy-critical entry points: bugs here only surface inside a live cluster. All offline unit tests in `tests/unit/pipelex/temporal/` (existing dir, no conftest; reference style: `test_storage_payload_codec.py` with class-level `@pytest.mark.asyncio(loop_scope="class")`).

### B1 — `temporal/codec/codec_server.py` (baseline 0%)

New file `tests/unit/pipelex/temporal/test_codec_server.py`. Drive the real aiohttp app via `aiohttp.test_utils.TestClient(TestServer(app))` (no pytest-aiohttp plugin needed). Real `StoragePayloadCodec` + `InMemoryStorageProvider` for happy paths; raising stub codec (cast) for error branches.

- [x] CORS preflight (`OPTIONS /encode`, `/decode`): allowed origin → headers set; disallowed/missing origin → no CORS headers
- [x] Content-type guard: non-JSON POST → 415 (with CORS headers when origin allowed)
- [x] Malformed Payloads JSON → 400
- [x] Happy `/encode` → large payload becomes storage-ref payload (JSON parse of response proto); `/decode` of that response restores original bytes (full HTTP round-trip)
- [x] Codec raising `StorageFileNotFoundError` → 404; `OSError` → 502
- [x] Success response: content-type JSON + CORS headers on allowed origin

### B2 — `temporal/temporal_connect.py` (baseline 24%)

New file `tests/unit/pipelex/temporal/test_temporal_connect.py`. Mock at the `temporal_connect` module namespace: `TemporalClient` (class replaced, `.connect` AsyncMock), `get_config`, `get_secret`, `get_required_env`, `make_codec_from_config`, `make_data_converter`. Real `TemporalServerConfig` instances.

- [x] `connect_to_temporal_server()` api_key matrix: NONE → api_key=None/tls=False/empty metadata; ENV_VAR → `get_required_env(api_key_id)`, tls=True, `{"temporal-namespace": ns}`; SECRET_PROVIDER → `get_secret(secret_id=...)`; ENV_VAR/SECRET_PROVIDER with empty api_key_id → `TemporalConfigError`
- [x] Payload codec wiring: enabled → `make_codec_from_config()` + `make_data_converter(payload_codec=...)` passed as converter; disabled → module-level `data_converter`
- [x] `TemporalClient.connect` raising `RuntimeError` → `TemporalServerError` carrying `full_description`
- [x] `connect_to_temporal_selected_server()`: known name → connects with that config; unknown name → `TemporalConfigError`
- [x] `connect_to_temporal()`: uses `temporal_config.selected_server`

### B3 — `temporal/worker_cli.py` (baseline 0%)

New file `tests/unit/pipelex/temporal/test_worker_cli.py`. Test `configure()` directly (sync; mock `Pipelex.make`, `get_config`, `load_toml_from_path`, hub getters at `pipelex.hub`, `run_worker` AsyncMock — `asyncio.run` consumes its coroutine) plus a Typer `CliRunner` pass for arg wiring. `run_worker()` tested async with `get_task_manager` mocked.

- [x] `run_worker()`: forwards all kwargs to `get_task_manager().run_worker`; both project None and explicit project log paths
- [x] Project resolution: explicit arg skips pyproject; `project.name`; `tool.poetry.name` fallback; neither → `ValueError`
- [x] `--is-unit-testing` → `runtime_manager.set_run_mode(RunMode.UNIT_TEST)`; not set → no call
- [x] Fast-fail task-queue check: explicit `--task-queue` vs `worker_config.default_task_queue` fallback passed to `validate_task_queue_known`; validation error propagates before library load
- [x] Library load: dirs resolved → `load_libraries` with them; empty → not called; `open_library`/`set_current_library` with `worker_base`
- [x] `temporal.is_enabled` False → forced on via `model_copy(update={"is_enabled": True})` and reassigned
- [x] CliRunner arg wiring: `--task-queue/--scope/--profile/--is-unit-testing/--is-not-sandboxed` reach `run_worker` positionally correct

### CHECKPOINT 4 — Phase B (Temporal entry points) done

Status: **CLEARED 2026-06-12 — PHASE B COMPLETE.** New files: `test_codec_server.py`, `test_temporal_connect.py`, `test_worker_cli.py` in `tests/unit/pipelex/temporal/`. Full non-inference suite green with `--cov` (same marker expression as `make agent-test`, run without `--exitfirst` — strictly stronger); `make agent-check` clean; targeted temporal unit+integration dirs green; changelog [Unreleased] entry added. Final full-suite coverage (written into the menu doc): worker_cli 0→100, codec_server 0→96, temporal_connect 24→98 — the only missed lines in all three are `TYPE_CHECKING` import blocks. Decisions: codec server driven over real HTTP with `aiohttp.test_utils.TestClient(TestServer(app))` (no pytest-aiohttp plugin needed) — real `StoragePayloadCodec` + `InMemoryStorageProvider` for happy paths, a raising stub codec (cast) for the 404/502 error mapping; temporal_connect mocked entirely at its module namespace (whole `TemporalClient` class replaced so `.connect` is an AsyncMock — never touches the real SDK class), real `TemporalServerConfig` instances; worker_cli's `configure()` tested directly as a sync function (its `asyncio.run` consumes a patched `run_worker` AsyncMock's coroutine) plus Typer `CliRunner` passes for arg wiring — hub getters patched at `pipelex.hub` (they're imported inside the function), `runtime_manager.set_run_mode` patched on the CLASS (pydantic model instances reject attribute patching). Adjacent gap noted, deliberately skipped: `codec/codec_server_cli.py` (0%) is the thin arg-parse + `run_app` wrapper — interface layer, same category as the Typer wrappers excluded in section A. NEXT menu section: **C — inference plumbing** (pure-function factories: img_gen_args_factory, llm/img_gen worker factories, structured_output, backend_credentials, model_deck_check, gateway/mistral completions factories).
