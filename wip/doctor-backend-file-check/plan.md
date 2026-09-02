---
status: draft
item: L-260902-376d51
---

# Doctor: validate backend files leniently

## Problem

`pipelex doctor` on a stock installation reports a hard "Backend configuration error" for `pipelex_gateway`, and the Models row never gets to run its own check. Verified on `dev` on 2026-09-03, on a config directory copied straight from the kit with no edits.

The cause is one call. `check_backend_files` in `pipelex/cli/commands/doctor_cmd.py` probes each enabled backend by loading the whole backend library through `InferenceBackendLibrary.load` with neither a gateway config nor `lenient=True`. The loader's gateway branch in `pipelex/cogt/model_backends/backend_library.py` treats a missing gateway config in strict mode as a caller's omission and raises `InferenceBackendLibraryError` with a message addressed to a library caller ("pass `gateway_config`, or disable the backend"). The kit ships `[pipelex_gateway] enabled = true` in `backends.toml` and ships `backends/pipelex_gateway.toml`, and that file's presence is what makes the probe validate the gateway at all, so the ordinary install is the reproduction.

`check_models` then returns as soon as `check_backend_files` reports any invalid file, before fetching the remote config, building the gateway config and validating the model deck. So on a stock install the model check is never reached, and the report points at a file identical to the kit template it offers to restore.

### Verified facts

Run against a scratch copy of `pipelex/kit/configs/inference`, with the doctor runtime set up by `setup_doctor_runtime()`:

- `check_backend_files(config_dir=<kit copy>)` returns `healthy=False`, "1 backend file(s) have validation errors", with `pipelex_gateway` carrying the loader's caller-facing message.
- **The false error masks real ones.** The gateway is the first table in the kit's `backends.toml`, so every per-backend probe dies on it before reading any other file. With an unknown table appended to `anthropic.toml`, the probe still reports `anthropic` as valid and only `pipelex_gateway` as invalid. On a stock install the file check can currently detect nothing.
- With `lenient=True`, the same load succeeds on the kit copy: the gateway backend is skipped ("gateway model specs not available") and every other kit backend loads, with the environment scrubbed of every API key.
- With `lenient=True`, the malformed `anthropic.toml` still raises `InferenceBackendLibraryError: Unknown key on model 'bogus_key_table' for backend 'anthropic' from file '…/backends/anthropic.toml'`, whether or not `ANTHROPIC_API_KEY` is set. Leniency does not swallow a malformed file, which is what the loader's docstring promises.
- Missing credentials do not fail the load in either mode: with the gateway disabled, a strict load over the kit copy succeeds under a scrubbed environment. So on a stock install the only behaviour leniency changes in this probe is the gateway branch.
- The lenient path logs through `log.verbose`, which needs a configured log. `check_models` already requires `setup_doctor_runtime` to have run, and unit tests get a configured log from the module-scoped `Pipelex.make` fixture in `tests/conftest.py`.

Not a regression from `feature/Two-gateways-2`: that branch renamed the loader parameter to `managed_gateway_configs` and reworded the message, and left both sites in the same shape. The fix is one keyword argument and rebases onto either.

## Decision

Pass `lenient=True` on the load in `check_backend_files`. The file check exists to catch a malformed per-backend file; whether the gateway's specs are reachable is the Models row's question (it fetches the remote config itself, behind the terms-accepted gate), and whether credentials resolve is the Credentials row's. Leniency is exactly that split: the loader skips a backend whose gateway specs or credentials are unavailable and stays fatal on a malformed file.

Rejected alternatives:

- Fetching the gateway config inside the file check. It would put a network fetch and the terms gate inside a check that should read files only, and duplicate what `check_models` does a few lines later.
- Dropping the early return in `check_models`. The return is right when a file is genuinely malformed: validating a model deck over a broken backend file reports the far more confusing "model not found". The bug was the false input to that return, not the return.

## Steps

1. **The fix.** In `check_backend_files`, pass `lenient=True` to `temp_library.load(...)` and replace the "Try to load just this backend's specs" comment with one that says why: the probe validates file shape, and a backend whose gateway specs or credentials are unavailable is another row's finding, not a malformed file.
2. **Docstring accuracy.** The `lenient` docstring on `InferenceBackendLibrary.load` says credentials are "the whole of the tolerance", but the gateway branch also skips under leniency when no gateway config was passed. Amend that sentence so the docstring matches the code.
3. **Tests**, in `tests/unit/pipelex/cli/test_doctor_backend_checks.py`, both built on a copy of `get_kit_configs_dir() / "inference"` into `tmp_path`, so the shipped defaults are the fixture:
    - A stock kit copy is healthy: `check_backend_files` returns healthy, every report valid, and the `pipelex_gateway` report present and valid. Mutation check: revert step 1 and this test must go red with the gateway message.
    - A malformed file is still caught under leniency and no longer masked: append an unknown table to `anthropic.toml`; expect unhealthy, `anthropic` invalid with a message naming `anthropic`, and `pipelex_gateway` valid.
    - The existing `check_models` short-circuit test keeps its meaning and stays.
4. **Docs.** `docs/under-the-hood/init-cli-flows.md` lists `check_backend_files` in its resolution table; add a sentence there stating that the backend-files probe loads leniently and what that leaves to the Credentials and Models rows. No user-facing page describes the doctor's rows individually today, so this is the one touch.
5. **Changelog.** A `### Fixed` entry under `[Unreleased]`: the doctor no longer reports a false backend-configuration error for the gateway on a stock install, the Models row runs its own check, and a malformed backend file is no longer hidden behind the gateway.
6. **Verify.** `make agent-check`; the two doctor test modules directly; `make agent-test`. By hand: `pipelex doctor` against a fresh `pipelex init config` directory, expecting the Backend Files row healthy and the Models row reporting its own verdict.
7. **PR** against `dev` with `Closes L-260902-376d51` in the body.

## Out of scope

- `check_backend_files` loads the whole library once per enabled backend and attributes an exception to a backend by substring match on its name or file path. It is quadratic in file reads, and a name that is a substring of another (`openai` inside `azure_openai`) can misattribute an error. A per-backend validation entrypoint on the loader would fix both. Not this fix; file a ledger item if it bites.
- The loader's message wording is a caller's message and stays one: after this fix no user-facing surface reaches it on a stock install.

## Verification record

The facts above were established on 2026-09-03 by calling `check_backend_files` and `InferenceBackendLibrary.load` directly from `.venv/bin/python` over scratch copies of the kit's `inference/` directory, under `env -i` so no API key was in the environment.
