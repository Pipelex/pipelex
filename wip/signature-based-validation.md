# Signature-Based Validation for Partially-Defined Pipelines

Status: **Implemented and landed** on `feature/Validate-with-signatures-3` — Phases 1–7.3 complete, `make agent-check` and `make agent-test` green. The single open item is the **Phase 7.4 cross-repo merge-gate** (retire the branch-local MTHDS schema rule once `vscode-pipelex` ships a bundled schema that knows `type = "PipeSignature"` — see the end of this doc). The CHANGELOG `[Unreleased]` section is the user-facing record; this doc is the engineering current-state plus a reviewer verification map.

## What it does

`PipeSignature` is a first-class pipe type (`type = "PipeSignature"`) that declares a pipe's `inputs`, `output`, and `description` without an implementation — a contract. Any pipe in a bundle can use one as a placeholder, so an author or agent can sketch a complete pipeline top-down and fill implementations one pipe at a time, validating at every step.

Use cases: AI agents iteratively building pipelines; library authors publishing contract bundles; refactors that stub a pipe with its prior contract while the body is rewritten.

## Two validation modes (as built)

Validation has two distinct purposes, so it has two modes. The mode is the contract — there is no "detect intent" heuristic.

- **Strict (default)** — fails if any pipe reachable from the target *is* or *reaches* a `PipeSignature`. This is the "ready to run in production" semantic. Raises `SignaturesNotAllowedError` listing every reachable signature plus the controller chain (`signature_refs`, `dep_paths`) and the suggested fix.
- **Lenient (`--allow-signatures`)** — accepts signatures; they participate in dry-run by minting a mock `Stuff` from their declared output contract (multiplicity included). For authoring and agent flows.

**Defaults: both the main CLI and the agent CLI are strict by default.** (This corrects an earlier design note that had the agent CLI lenient-by-default — it is not; see `test_agent_validate_defaults_strict.py`.) Lenient is opt-in via `--allow-signatures` everywhere.

Strict and lenient are complementary with live-run safety: `_live_run_pipe` on a signature always raises `PipeSignatureNotExecutableError`, so even if strict validation is skipped or a signature is added between validate and run, live execution fails loudly.

### Whole-bundle vs single-pipe strict semantics

- `validate bundle <file>` (strict) rejects a bundle that *contains* any signature, reached or not — an unimplemented placeholder means the bundle is not fully runnable. (Mechanically: the strict pre-check fires for every signature in the batch because a signature reaches itself.)
- `validate --all` (strict) filters signature pipes out of the iteration, then runs each remaining pipe's strict pre-check — so an orphan signature with no caller does not fail `--all`, but a non-signature pipe that reaches one does.
- To validate just the implemented slice of a partially-stubbed bundle, select it with `--pipe <code>`: only that pipe is dry-run (others are loaded so dependencies resolve). Strict mode is still enforced on the selected pipe.

## Reviewer verification map

Each row names where the behavior lives and the test that pins it.

| Concern | Shipped in | Verified by |
|---|---|---|
| Type system: `PipeType.PIPE_SIGNATURE`, `PipeCategory.PIPE_SIGNATURE`, `is_signature`, default `pipe_dependencies()` | `pipelex/core/pipes/pipe_abstract.py`, pipe type/category enums | exhaustive-match enum tests; integration suite below |
| Blueprint + runtime + factory | `pipelex/pipe_signature/pipe_signature_blueprint.py`, `pipe_signature.py`, `pipe_signature_factory.py` | `tests/integration/pipelex/pipe_signature/` |
| Spec layer: `PipeSignatureSpec` (literal `type`, optional `signature_for`, multiplicity inputs, no `result`) | `pipelex/builder/pipe/pipe_signature_spec.py` | `tests/unit/pipelex/builder/pipe/test_pipe_signature_spec.py` |
| Strict pre-check: `collect_signature_refs` / `collect_signature_paths`, `SignaturesNotAllowedError`, `allow_signatures` threading + cross-batch aggregation | `pipelex/pipe_signature/signature_walk.py`, `pipelex/pipe_run/dry_run.py`, `pipelex/pipeline/validate_bundle.py` | `tests/integration/pipelex/pipe_signature/test_dry_run_strict_mode.py`, `tests/e2e/test_signature_validation_mthds.py` |
| Main CLI: `validate pipe/bundle [--allow-signatures]`, `--all` filters signatures, lenient summary suffix, friendly `SignaturesNotAllowedError` rendering | `pipelex/cli/commands/validate/_validate_core.py`, `pipelex/cli/error_handlers.py` | `tests/integration/pipelex/cli/test_validate_signatures_cli.py`, `test_validate_signatures_summary.py`, `tests/e2e/test_signature_validation_cli.py` |
| Agent CLI: same flags (strict default), `--pipe` single-slice validation | `pipelex/cli/agent_cli/commands/validate/_validate_core.py`, `bundle_cmd.py` | `tests/integration/pipelex/cli/test_agent_validate_defaults_strict.py`, `test_agent_validate_pipe_in_bundle.py` |
| Live-run guard (`PipeSignatureNotExecutableError`) | `pipelex/pipe_signature/pipe_signature.py` | `tests/e2e/test_signature_validation_mthds.py` (live-run case) |
| Schema generator strips `pipe_category` from `PipeSignatureBlueprint` | schema generator (`pipelex-dev generate-mthds-schema`) | runs clean in `make agent-check` |
| Docs + CHANGELOG | `docs/building-methods/pipes/signature-pipes.md`, CHANGELOG `[Unreleased]` | — |

## Review fixes (post-merge, 2026-05-31, commit `4cc60c52`)

After `dev` was merged in, the review bots surfaced reconciliation issues; the confirmed ones landed with regression tests:

- **`--pipe` validates only the requested pipe.** `validate_bundle` gained a `dry_run_pipe_codes` param (with a `_pipes_to_dry_run` helper); `validate_pipe_in_bundle_core` now loads the bundle but dry-runs only the selected pipe, so an unrelated signature or otherwise-broken pipe no longer blocks validating an implemented slice. A typo'd `--pipe` raises `PipeNotFoundError` instead of passing vacuously. — `test_agent_validate_pipe_in_bundle.py`
- **`validate --all` renders `SignaturesNotAllowedError` as a friendly CLI error** (`handle_signatures_not_allowed_error`) instead of an unhandled traceback, matching the bundle/pipe paths. — `test_validate_signatures_cli.py`
- **`handle_signatures_not_allowed_error` honors `--traceback`**, consistent with every other `handle_*`.
- **`PipeSignatureSpec.rendered_pretty` escapes dynamic values** before Rich markup, so concept multiplicity (`Doc[]`, `Img[3]`) and bracketed descriptions render literally instead of being parsed as markup. — `test_pipe_signature_spec.py`
- **Strict whole-bundle docstrings clarified** (`dry_run_pipes`, `PipeSignatureSpec`): whole-bundle strict rejects any bundle containing a signature; `--pipe` / `--allow-signatures` are the escape hatches.
- A separate `.pipelex/plxt.toml` "schema rule clobbers formatting" report was reviewed and confirmed a **false positive** (taplo merges formatting across matching rules; schema is resolved independently) — no change.

## Architecture (Option A, as built)

Three layers, parallel additions; the discriminator stays `type`:

```
spec/builder    PipeSignatureSpec       (pipelex/builder/pipe/pipe_signature_spec.py)
blueprint/core  PipeSignatureBlueprint  (pipelex/pipe_signature/pipe_signature_blueprint.py)
runtime         PipeSignature           (pipelex/pipe_signature/pipe_signature.py)
```

Signatures are a third pipe *category* (not operator, not controller): no inference, no sub-pipe orchestration. The separate category surfaces them cleanly in tooling and the `is_signature` property, and the exhaustive-match rule for enums forces every match-case to acknowledge the new value (the linter catches every place that needs to know). The factory lookup convention (`f"{pipe_type}Factory"`) needed no dispatch changes — just registering `PipeSignatureFactory`.

The dependency-graph walk lives as free functions in `pipelex/pipe_signature/signature_walk.py`, downstream of `pipelex.hub`, **not** as methods on `PipeAbstract` — `pipe_abstract` importing `hub` forms a real runtime import cycle (`pipe_abstract → hub → libraries.library → libraries.pipe.pipe_library → pipe_abstract`). `PipeAbstract` keeps only `is_signature` and a default `pipe_dependencies()`.

`PipeSignature._dry_run_pipe` mints a `Stuff` of the declared output concept/multiplicity (via `WorkingMemoryFactory.make_mock_content`); `_live_run_pipe` raises `PipeSignatureNotExecutableError`; the static/library validators are no-ops.

## Design rationale & tradeoffs (for the record)

- **MTHDS surface grows** — kept `PipeSignature` deliberately minimal so it reads as obviously-a-contract.
- **Strict gate must be wired at every entry** — default `allow_signatures=False` guards against missed code paths; the test matrix covers the rest.
- **Mock fidelity has limits** — a signature describes structure, not values; downstream pipes whose prompts reference specific content shapes may dry-run but fail live (the general DRY-mode limitation).
- **`required_variables` loses dotted-path info** for signatures (no prompt/template). Acceptable for the target use cases.
- **No signature mode for concepts** — out of scope.

Rejected alternatives: compiling signatures to `PipeFunc` at load (layering violation, silent live success on mock data); a parallel `signature` table in `.mthds` (two resolution paths); implicit "skeletal" pipes such as a prompt-less `PipeLLM` (bug-vs-feature is indistinguishable from field presence).

## Open: Phase 7.4 — cross-repo schema merge-gate (the one remaining item)

The bundled `plxt` schema (shipped from `vscode-pipelex/`) does not yet know `type = "PipeSignature"`. On this branch the canonical schema for `*.mthds` is the locally-regenerated `derived/mthds_schema.json`, wired in via a `[[rule]] / [rule.schema]` block in `.pipelex/plxt.toml` scoped to `**/*.mthds`. That block is the **intended** configuration on this branch (and `plxt lint` is green against it), not a workaround — the fast-path PostToolUse hook picks it up automatically too.

Merge-gate, in lock-step:

1. Land the `vscode-pipelex` release that bundles an updated schema knowing `PipeSignature`.
2. Remove the branch-local `[[rule]]` block from `.pipelex/plxt.toml` in the same merge.
3. Re-verify `plxt lint` stays green with the new bundled `plxt` installed and the branch-local rule gone — that cross-check, not the branch-local lint, is the ship-readiness signal.

Until step 3 is green, the branch is **not** ship-ready; do not mark "Ready to ship".

⚠️ **Counter-to-merge-gate item to resolve first:** the working tree currently carries an uncommitted edit to `pipelex/kit/configs/plxt.toml` (the kit template shipped to users via `pipelex init`) that copies this same branch-local schema block into it. That points end-user projects at a `derived/mthds_schema.json` path that will not exist for them, and it propagates the exact rule Phase 7.4 says to retire. It should be dropped before merge — the branch-local schema rule belongs only in `.pipelex/plxt.toml` on this branch, never in the shipped user template.

## History

The phase-by-phase TDD implementation log lives at [`archive/signature-based-validation-tdd-plan.md`](archive/signature-based-validation-tdd-plan.md) (kept as the build record; this doc is the live current-state reference).
