# Suspects — package `cli`

Reviewed: 112 Section A + 30 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/cli/cli_factory.py:31` — `make_pipelex_for_cli` — `def make_pipelex_for_cli(context: ErrorContext, *, library_dirs: ..., needs_inference: bool, ...) -> Pipelex` — `context` is error-reporting metadata (an `ErrorContext` enum used to shape error messages), not the object being created. The function builds a `Pipelex` instance; `context` is a side-channel tag. Every call site uses `context=...` as a keyword (confirmed across all call sites). Suggested fix: make fully keyword-only (`def make_pipelex_for_cli(*, context: ErrorContext, library_dirs: ..., ...)`)

- `pipelex/cli/agent_cli/commands/run/_output_helpers.py:14` — `build_run_output` — `def build_run_output(with_memory: bool, *, main_stuff_json: dict, working_memory_dump: dict, compact_result: ..., extra_metadata: ...) -> dict` — `with_memory: bool` is a mode flag, not the semantic object being assembled. Both call sites pass it as `with_memory=with_memory` (keyword). `main_stuff_json` is arguably the more central data. Suggested fix: move `*` before `with_memory` (make it keyword-only too).

- `pipelex/cli/commands/init/command.py:182` — `determine_needs` — `def determine_needs(reset: bool, *, check_config: bool, check_inference: bool, ...) -> tuple[bool, bool, bool, bool]` — `reset: bool` is a mode flag among several other boolean flags; it's not semantically more "the subject" than `check_config`, `check_inference`, etc. The single call site passes it as `reset=reset` (keyword). Suggested fix: move `*` before `reset` (make it keyword-only too, consistent with the other boolean flags).

## Medium / low confidence

- `pipelex/cli/agent_cli/commands/init_cmd.py:173` — `_configure_backends` — `def _configure_backends(config: dict[str, Any], *, backends_toml_path: Path, template_backends_path: Path) -> list[str]` — the function's primary action is modifying `backends_toml_path`; `config: dict` is read-only input/context from which backend selection is extracted. The call site passes it as `_configure_backends(parsed_config, backends_toml_path=..., ...)` (positional use). This is a private helper so the impact is contained, and `config` as "data being acted upon" is defensible. Low confidence — calling convention is actually used positionally here, so no immediate caller-side benefit.
