# Follow-up — surface `pending_signatures` / `is_runnable` on the protocol-level `validate`

> **Status: 📋 PLANNED — not started.** Deferred from the v0.33.0 merge into `feature/Support-recursive-design` (deliberately kept out of the merge to keep it minimal).

## Context (cold start)

v0.33.0 (PR #985) turned the runner into a local MTHDS Protocol implementation: `PipelexMTHDSProtocol` in `pipelex/pipeline/runner.py`. Its `validate(mthds_contents, allow_signatures=False)` method wraps our `validate_bundle` and maps the result onto `PipelexValidationReport`, currently returning only `blueprint`, `graph_spec=None`, and `pipe_structures`.

Meanwhile this branch's recursive-design work made `validate_bundle` compute the runnability verdict: `ValidateBundleResult.pending_signatures` (`pipelex/pipeline/validate_bundle.py` — `build_pending_signatures`, library-wide, cross-package refs excluded). It is surfaced as `pending_signatures: string[]` + `is_runnable: bool` on the agent-CLI / builder validate envelopes (`pipelex/cli/agent_cli/commands/validate/_validate_core.py`, `pipelex/builder/operations/validate_ops.py` — `is_runnable = not pending_signatures` everywhere), but **not** on the protocol `validate` — so a top-down build driving the runtime through the MTHDS Protocol (instead of the agent CLI) can't see what remains to implement.

This is protocol-legal without any spec change: the protocol base `mthds.protocol.models.ValidationReport` deliberately declares **no body fields** and sets `extra="allow"` — "implementations may include their own artifacts". `PipelexValidationReport` already follows that pattern with `blueprint` / `graph_spec` / `pipe_structures` as Pipelex extension fields.

## Plan

1. **Add the two extension fields to `PipelexValidationReport`** (`pipelex/pipeline/runner.py`): `pending_signatures: list[str] = Field(default_factory=list)` and `is_runnable: bool = True`.
2. **Populate them in `PipelexMTHDSProtocol.validate`** from the `validate_bundle` result, mirroring the CLI convention: `pending_signatures=result.pending_signatures, is_runnable=not result.pending_signatures`. The wrapper already holds `result` in hand where it builds the report — a two-line change.
3. **Tests — note there is currently NO test coverage for `PipelexMTHDSProtocol.validate` at all** (grep `\.validate(` under `tests/` finds nothing against the protocol wrapper). So this needs a first integration test, e.g. `tests/integration/pipelex/pipeline/test_protocol_validate.py`:
   - a complete bundle → `pending_signatures == []`, `is_runnable is True`;
   - a bundle with an unsatisfied `PipeSignature`, `allow_signatures=True` → the signature's qualified ref in `pending_signatures`, `is_runnable is False`;
   - reuse the `.mthds` fixtures under `tests/e2e/pipelex/pipes/additive_multi_file_library/signature_only/` (header + concepts, no definition) rather than authoring new ones.
   - While there, the test can also pin the wrapper's library-lifecycle contract (restores the caller's current library, tears the validation library down) — it's documented in a comment in `validate` but untested.
4. **Changelog** — entry under `[Unreleased]` (Changed, alongside the existing additive-multi-file entry that already documents `pending_signatures` on the CLI surfaces).

## Verify

`make agent-check` clean + `make agent-test` green (per repo standard).

## Watch-outs

- **Strict-mode interplay:** with `allow_signatures=False` (the protocol default), an unsatisfied signature makes `validate_bundle` *raise* (`ValidateBundleError` from the strict refusal) — the report fields only matter on the lenient path. Don't try to populate them on the failure path; failures are RFC 7807 problems per the protocol docstring.
- **Downstream:** `pipelex-api` (the HTTP runner) serializes whatever `validate` returns; once it picks up a pipelex version with this change, the fields appear on its `/validate` response automatically. No pipelex-api change needed, but the hosted-platform consumers (mthds-plugins hook, webapp build chatbot) may want to read `is_runnable` from the API path too — flag it when bumping the pin.
- A related deliberate omission: `validate all` / `validate pipe` intentionally omit `pending_signatures` (it's a per-bundle, top-down-build nudge — rationale in the comments at `pipelex/builder/operations/validate_ops.py` `validate_all` and `pipelex/cli/agent_cli/commands/validate/_validate_core.py`). The protocol `validate` is bundle-shaped, so it takes the field; don't propagate it to the all/pipe surfaces. The original feature record is Task 1 in [`recursive-followups.md`](recursive-followups.md).
