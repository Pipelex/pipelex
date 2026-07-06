# TOML pipeline inputs — feature/Inputs

Status: **CHECKPOINT 1 CLEARED (2026-07-06)** — Phases 1+2 implemented and green (`make agent-check` + targeted CLI unit/integration/e2e tests). Uncommitted in the worktree; next up is Phase 3. This tracker replaces the retired hello-plugin tracker (that track completed and merged to dev via PR #1015).

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

### Phase 3 — Template generation `--format toml`

- [ ] Refactor `InputStuffSpecs.render_inputs` to expose the template dict (e.g. `build_inputs_template() -> dict`), keeping `render_inputs` as the JSON serializer over it.
- [ ] TOML serializer for templates using `tomlkit` (pretty, preserves our intended layout). First verify what `render_stuff_spec` can emit: any `None` (or other TOML-unrepresentable value) in template placeholders must be handled deliberately (omit the key or substitute a placeholder string) — pin the choice with a test.
- [ ] Main CLI `pipelex build inputs pipe|bundle|method`: add `--format json|toml` (StrEnum from `pipelex.types`, default `json`); when `toml`, serialize with the new serializer and default the output filename to `inputs.toml` (`_inputs_core.py` default-path logic).
- [ ] Agent CLI `pipelex-agent inputs pipe|bundle|method`: same `--format json|toml` option. Note the deviation: elsewhere on the agent CLI `--format` means `markdown|json`; the `inputs` commands are currently format-less always-JSON. Keep the flag name, different enum, and document it in `pipelex/cli/agent_cli/CLAUDE.md` (commands table + output-contract section). TOML output goes to stdout raw, same spirit as the `concept`/`pipe` raw-TOML passthrough commands.
- [ ] Round-trip test: a `--format toml` generated template loads back through the Phase-1 loader and resolves to the same dict as the JSON template.

**CHECKPOINT 2** — template generation done both surfaces; commit boundary.

### Phase 4 — Docs, changelog, final gates

- [ ] `docs/tools/cli/run.md`: rework the "Input JSON Format" section into an inputs-file-formats section (extension rule, TOML example with multi-line strings, datetime limitation, ambiguity rule for auto-detect).
- [ ] `docs/building-methods/pipes/provide-inputs.md`: same PipelineInputs shapes shown in both JSON and TOML.
- [ ] `docs/tools/cli/build/inputs.md`: `--format toml` + default filename behavior.
- [ ] `docs/tools/cli/agent-cli.md` + `pipelex/cli/agent_cli/CLAUDE.md`: inputs `--format`, run `.toml` support, stdin-stays-JSON note.
- [ ] `CHANGELOG.md` under `[Unreleased]`: Added — TOML inputs (extension-discriminated) + `--format toml` template generation; note the TOML-datetime limitation.
- [ ] Full `make agent-check` + `make agent-test`.

**CHECKPOINT 3 (final)** — gates green, tracker updated with commit SHAs, ready for PR to dev.

## Deferred — follow-up wave AFTER this ships in a pipelex release (NOT this branch)

- **Spec + conformance sync (D6).** Grep `docs/specs/` (workspace root) for the `--inputs` surface (command-surface-map, protocol spec); add the extension rule + `--format toml` to the spec prose and matching conformance tests with the bidirectional `> Verified by:` ↔ `pytest.mark.spec` links. Gated on the conformance venv's pipelex pin reaching the release that carries this feature (same de-gate pattern as the Optionals track).
- **Skills sweep.** `mthds-plugins` skills (`mthds-run`, `mthds-inputs`) document `inputs.json`; update after release (published plugin, separate repo).
- **mthds-js check.** Verify `mthds-agent` passes `--inputs` through opaquely (no client-side `.json` assumption) — expected no-op.
- **DATETIME native concept.** Add `DATETIME` to `NativeConceptCode`, then replace the Phase-1 datetime guard with real support. Own track.
