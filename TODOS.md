# TOML pipeline inputs — feature/Inputs

Status: **CHECKPOINT 3 CLEARED (2026-07-06)** — all four phases done. Phases 1+2 committed (`9041c6986`), Phase 3 committed (`1fdfd26d0`), Phase 4 (docs + changelog) complete with full `make agent-check` + `make agent-test` green. Feature is ready for PR to dev — nothing pushed. This tracker replaces the retired hello-plugin tracker (that track completed and merged to dev via PR #1015).

## Goal

Accept pipeline inputs as TOML in addition to JSON, discriminated by file extension, on both CLI surfaces (`pipelex run pipe|bundle|method` and `pipelex-agent run ...`). Also let the input-template generators (`pipelex build inputs ...`, `pipelex-agent inputs ...`) emit TOML via `--format toml`. TOML's multi-line strings make text-heavy inputs much more pleasant to author than JSON.

## Current state (verified against this tree)

- Both surfaces take `--inputs` and discriminate by content prefix, not extension: `startswith("{")` → inline JSON, else → JSON file via `load_json_dict_from_path` + `resolve_inputs_paths`. Main CLI: `pipelex/cli/commands/run/_run_core.py:140-164`. Agent CLI: `pipelex/cli/agent_cli/commands/run/stdin_resolver.py` (`parse_cli_inputs` → `_parse_inputs_arg`).
- The agent CLI additionally reads JSON from stdin (flat dict or `working_memory` envelope) — `stdin_resolver.py:_read_stdin_inputs`.
- `run bundle <dir>` auto-detects `inputs.json` (`DEFAULT_INPUTS_FILE_NAME` in `pipelex/builder/conventions.py`) — main `cli/commands/run/bundle_cmd.py:149`, agent `cli/agent_cli/commands/run/bundle_cmd.py:118`.
- TOML loading machinery already exists and is unused on this path: `pipelex/tools/misc/toml_utils.py` (`load_toml_from_path` via `tomli`, raising `TomlError`; `tomlkit` for writing).
- Template generation: main CLI `build inputs` uses `render_inputs` (`pipelex/core/pipes/inputs/input_renderer.py`) → `InputStuffSpecs.render_inputs` (`input_stuff_specs.py:153`) which builds a dict then `json.dumps` — the dict is trivially extractable for a TOML serializer. Agent CLI `inputs` uses `build_inputs_for_pipe` (`pipelex/builder/operations/inputs_ops.py`) which already returns the dict.
- The API runner receives the already-parsed dict, so this feature is purely client-side parsing — no wire or server change.

## Decisions (settled with Louis, 2026-07-06)

- **D1 — extension discrimination.** `.toml` suffix → TOML loader; every other value (including `.json` and extensionless) keeps today's JSON behavior. No content sniffing.
- **D2 — inline and stdin stay JSON-only.** The `{`-prefix inline path is untouched; inline TOML is ambiguous with file paths. Agent-CLI stdin (flat dict + `working_memory` envelope) stays JSON-only.
- **D3 — auto-detect both, error on ambiguity.** `run bundle <dir>` auto-detects `inputs.toml` alongside `inputs.json`; if both exist, hard error telling the user to pass `--inputs` explicitly.
- **D4 — TOML datetimes rejected for now.** `tomli` parses TOML datetime/date/time into Python objects with no JSON equivalent. Adding `DATETIME` to `NativeConceptCode` is deferred to its own track; until then the loader rejects any datetime-typed value with an explicit not-implemented error.
- **D5 — template generation gets `--format json|toml`** (default `json`) on both surfaces; when `toml` is selected and no explicit output path is given, the default filename becomes `inputs.toml`.
- **D6 — everything lands in pipelex first.** No `docs/specs/` or `conformance/` edits ride this branch: conformance pins the released pipelex, so its tests can't go green until this ships in a release. Spec + conformance + skills + mthds-js sweep is an explicitly deferred follow-up wave (see "Deferred" below).

## Phases

### Phase 1 — Shared inputs-file loader — DONE

- [x] New module `pipelex/cli/commands/run/_inputs_file_loader.py`: `load_inputs_dict_from_path(path: Path) -> dict[str, Any]`. Suffix match: `.toml` → `load_toml_from_path`; else → `load_json_dict_from_path`. Also hosts the shared auto-detect probe `find_default_inputs_file(directory)` (D3).
- [x] Datetime guard: recursive walk rejecting `datetime.datetime` / `date` / `time` instances, run on both formats. New `pipelex/cli/commands/run/exceptions.py` with `InputsDatetimeNotSupportedError` and `AmbiguousInputsFilesError` — both carry class-level `error_domain = INPUT` + `user_action` (CHANGE_INPUT), so the agent envelope self-describes and they must NOT get `AGENT_ERROR_HINTS`/`AGENT_ERROR_DOMAINS` entries (enforced by `test_agent_output_drift.py`). Messages include the offending key path (e.g. `record.entries[0].when`) and the quote-as-string workaround.
- [x] `pipelex-dev generate-error-pages` run — new pages `docs/errors/inputs-datetime-not-supported-error.md`, `docs/errors/ambiguous-inputs-files-error.md` (+ index update).
- [x] Unit tests: `tests/unit/pipelex/cli/commands/run/test_inputs_file_loader.py` (loads, extension rule, TomlError, datetime top-level/nested/all four TOML datetime flavors, JsonTypeError, multi-line string) and `test_inputs_file_probe.py` (json-only / toml-only / neither / both-ambiguous).

### Phase 2 — Wire into both run surfaces — DONE

- [x] Main CLI `_run_core.py`: swapped to the shared loader; new except branches for `TomlError` and `InputsDatetimeNotSupportedError`; also fixed a pre-existing gap — invalid JSON in an inputs *file* (`json.JSONDecodeError`) previously escaped to the generic traceback handler, now gets a friendly message on both surfaces. The `JsonTypeError` wording stays JSON-specific (it can only fire on the JSON branch).
- [x] Agent CLI `stdin_resolver.py::_parse_inputs_arg`: same swap; `agent_error` branches for `TomlError` / `InputsDatetimeNotSupportedError` / `json.JSONDecodeError`. `AGENT_ERROR_HINTS` + `AGENT_ERROR_DOMAINS` got `TomlError` entries (it has no class-level metadata — kept generic since TomlError also fires outside inputs loading); the two new errors self-describe (see Phase 1).
- [x] Auto-detect + ambiguity (D3): `DEFAULT_INPUTS_TOML_FILE_NAME` in `conventions.py`; both `bundle_cmd.py` sites probe via the shared `find_default_inputs_file`. The probe is skipped entirely when `--inputs` is passed, so the ambiguity rule only bites on auto-detect (both surfaces).
- [x] Verified `run method --inputs relative/path.toml` comes free: main-CLI `method_cmd.py` joins `method_dir / inputs_path` preserving the suffix. Also fixed a pre-existing asymmetry (Louis's call): the *agent* CLI `run method` used to treat `--inputs` as cwd-relative; both surfaces now resolve relative `--inputs` file paths against the method dir via the shared `resolve_inputs_arg_against_dir` helper in `_inputs_file_loader.py` (inline JSON and absolute paths pass through).
- [x] Tests: e2e subprocess dry run with `inputs.toml` + relative `url` resolution (`tests/e2e/pipelex/cli/test_toml_inputs_run.py`, staged csv_demo fixture); main-CLI auto-detect/ambiguity/explicit-bypass (`tests/unit/pipelex/cli/commands/run/test_bundle_cmd_auto_inputs.py`); agent-CLI auto-detect + ambiguity envelope + bypass (`tests/unit/pipelex/cli/agent_cli/test_run_bundle_auto_inputs.py`); `.toml` branch + error envelopes in `test_stdin_resolver.py`; TOML load/resolve + error exits in `test_run_core_execution.py`; method-dir `--inputs` resolution helper (`test_inputs_arg_resolution.py`) + agent `run method` relative-path resolution (`test_run_method_inputs_resolution.py`).

**CHECKPOINT 1 — CLEARED 2026-07-06.** TOML inputs load end-to-end on both surfaces; `make agent-check` fully green (pyright/mypy/ruff/keyword-only); the full CLI unit, integration, and e2e test paths pass, including the new subprocess TOML dry run against the real binary. Work is uncommitted — commit before starting Phase 3.

### Phase 3 — Template generation `--format toml` — DONE

- [x] `InputStuffSpecs.build_inputs_template() -> dict` exposed; `render_inputs` (both the method and the module-level function in `input_renderer.py`) is now the JSON serializer over it.
- [x] TOML serializer `serialize_inputs_template_to_toml` in `pipelex/core/pipes/inputs/input_renderer.py` (tomlkit), plus `render_inputs_toml(pipe)` and the `InputsTemplateFormat` StrEnum (`json|toml`). Verified the generator never emits `None` placeholders (Optionals are unwrapped to their inner type), but the pinned defensive policy is: None → `""` recursively, so keys stay visible in the template (`test_inputs_template_toml.py`).
- [x] Main CLI `pipelex build inputs pipe|bundle|method`: `--format json|toml` (param `template_format`, default `json`); `toml` defaults the output filename to `inputs.toml` (next to bundle / `results/` / method `results/` — all three default-path sites).
- [x] Agent CLI `pipelex-agent inputs pipe|bundle|method`: same `--format json|toml`; `toml` prints the raw TOML template to stdout via shared `emit_inputs_result`/`emit_no_inputs_result` helpers in agent `_inputs_core.py` (no-inputs case prints a TOML comment line — valid TOML, loads as `{}`). Deviation documented in `pipelex/cli/agent_cli/CLAUDE.md` (output-format section + commands table); `test_inputs_format_unaffected.py` reworked to pin the new contract (InputsTemplateFormat, still no `--error-format`).
- [x] Round-trip tests: unit (`test_inputs_template_roundtrip.py` — TOML template loads through the Phase-1 loader identically to its JSON twin) and e2e (`test_toml_inputs_build.py` — real binary generates `inputs.toml` from the csv_demo fixture, then a dry run consumes it).

**CHECKPOINT 2 — CLEARED 2026-07-06.** Template generation done on both surfaces; `make agent-check` fully green; targeted CLI + core + builder unit/integration/e2e suites pass (incl. the generate→dry-run e2e chain and a manual raw-TOML smoke of the agent CLI). Committed at this boundary.

### Phase 4 — Docs, changelog, final gates — DONE

- [x] `docs/tools/cli/run.md`: reworked "Input JSON Format" → "Input File Formats" section (extension rule, JSON + TOML examples with multi-line strings, datetime-limitation warning, auto-detect/ambiguity note); all three `--inputs` option lines and the `run bundle` intro updated to mention JSON-or-TOML + inputs-file auto-detect.
- [x] `docs/building-methods/pipes/provide-inputs.md`: new "Input Files: JSON or TOML" section (extension rule, equivalent JSON/TOML example, datetime-limitation warning, pointer to run CLI reference); `build inputs` tip mentions `--format toml`.
- [x] `docs/tools/cli/build/inputs.md`: `--format json|toml` on all three subcommands, `--output` default-filename behavior (`inputs.json`/`inputs.toml`), `--format toml` example, TOML output + multiplicity examples; frontmatter/intro reworded.
- [x] `docs/tools/cli/agent-cli.md`: `run --inputs` JSON-or-TOML + stdin-stays-JSON/auto-detect note; `inputs --format json|toml` deviation note; Output Contract updated for inputs' dual output. (`pipelex/cli/agent_cli/CLAUDE.md` was already updated in Phase 3.)
- [x] `CHANGELOG.md` under `[Unreleased]`: Added — TOML inputs (extension-discriminated) + `--format toml` template generation; TOML-datetime limitation noted.
- [x] Full `make agent-check` (pyright/mypy/ruff/plxt/keyword-only all green) + `make agent-test` (full suite green).

**CHECKPOINT 3 (final) — CLEARED 2026-07-06.** All phases done; gates fully green; docs + changelog landed. Phase 4 changes uncommitted at this boundary — commit, then open the PR to dev. Nothing pushed.

## Deferred — follow-up wave AFTER this ships in a pipelex release (NOT this branch)

- **Spec + conformance sync (D6).** Grep `docs/specs/` (workspace root) for the `--inputs` surface (command-surface-map, protocol spec); add the extension rule + `--format toml` to the spec prose and matching conformance tests with the bidirectional `> Verified by:` ↔ `pytest.mark.spec` links. Gated on the conformance venv's pipelex pin reaching the release that carries this feature (same de-gate pattern as the Optionals track).
- **Skills sweep.** `mthds-plugins` skills (`mthds-run`, `mthds-inputs`) document `inputs.json`; update after release (published plugin, separate repo).
- **mthds-js check.** Verify `mthds-agent` passes `--inputs` through opaquely (no client-side `.json` assumption) — expected no-op.
- **DATETIME native concept.** Add `DATETIME` to `NativeConceptCode`, then replace the Phase-1 datetime guard with real support. Own track.
