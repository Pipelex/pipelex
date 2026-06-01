# Signature-Based Validation for Partially-Defined Pipelines

Status: **Implemented and landed** on `feature/Validate-with-signatures-3` — Phases 1–7.4 complete; `make agent-check`, `make agent-test`, `make ccs` (config-sync) and `make plxt-lint` (against the bundled schema) all green. The cross-repo merge-gate is **closed**: `pipelex-tools` 0.6.0 ships a bundled MTHDS schema that knows `type = "PipeSignature"` (and now requires `type` on every pipe variant), the branch-local schema rule has been removed from both `.pipelex/plxt.toml` and the `pipelex/kit/configs/plxt.toml` template, and the `plxt` floor is bumped to `>=0.6.0`. The branch is ship-ready. The CHANGELOG `[Unreleased]` section is the user-facing record; this doc is the engineering current-state plus a reviewer verification map.

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
| Type system: `PipeType.PIPE_SIGNATURE`, `PipeCategory.PIPE_SIGNATURE`, `is_signature`, default `pipe_dependencies()` on `PipeAbstract` + per-controller override | `pipelex/core/pipes/pipe_abstract.py`, `pipelex/pipe_controllers/pipe_controller.py`, pipe type/category enums | exhaustive-match enum tests; integration suite below |
| Union membership + registry wiring (the pipe type is recognized and `PipeSignatureFactory` resolves) | `pipelex/core/bundles/pipelex_bundle_blueprint.py` (`PipeBlueprintUnion`), `pipelex/core/registry_models.py` (`PIPE_SIGNATURES`, `PIPE_SIGNATURES_FACTORY`) | `tests/integration/pipelex/pipe_signature/` |
| Blueprint + runtime + factory; dry-run mints a mock `Stuff` from the declared output (multiplicity included) | `pipelex/pipe_signature/pipe_signature_blueprint.py`, `pipe_signature.py`, `pipe_signature_factory.py`, `pipelex/core/memory/working_memory_factory.py` (`make_mock_content`) | `tests/integration/pipelex/pipe_signature/` |
| Spec layer: `PipeSignatureSpec` (literal `type`, optional `signature_for`, multiplicity inputs, no `result`) | `pipelex/builder/pipe/pipe_signature_spec.py` | `tests/unit/pipelex/builder/pipe/test_pipe_signature_spec.py` |
| Strict pre-check: `collect_signature_refs` / `collect_signature_paths`, `SignaturesNotAllowedError`, `allow_signatures` threading + cross-batch aggregation, `ValidateBundleError.signature_check_error` | `pipelex/pipe_signature/signature_walk.py`, `pipelex/pipe_run/dry_run.py`, `pipelex/pipeline/validate_bundle.py`, `pipelex/pipe_signature/exceptions.py` (`SignaturesNotAllowedError`), `pipelex/pipeline/exceptions.py` (`ValidateBundleError`) | `tests/integration/pipelex/pipe_signature/test_dry_run_strict_mode.py`, `tests/e2e/test_signature_validation_mthds.py` |
| Main CLI: `validate pipe/bundle [--allow-signatures]`, `--all` filters signatures, lenient summary suffix, friendly `SignaturesNotAllowedError` rendering | `pipelex/cli/commands/validate/_validate_core.py`, `pipelex/cli/error_handlers.py` | `tests/integration/pipelex/cli/test_validate_signatures_cli.py`, `test_validate_signatures_summary.py`, `tests/e2e/test_signature_validation_cli.py` |
| Agent CLI: same flags (strict default), `--pipe` single-slice validation | `pipelex/cli/agent_cli/commands/validate/_validate_core.py`, `bundle_cmd.py` | `tests/integration/pipelex/cli/test_agent_validate_defaults_strict.py`, `test_agent_validate_pipe_in_bundle.py` |
| Live-run guard (`PipeSignatureNotExecutableError`) | `pipelex/pipe_signature/pipe_signature.py` (raise), `pipelex/pipe_signature/exceptions.py` (class) | `tests/e2e/test_signature_validation_mthds.py` (live-run case) |
| Schema generator strips `pipe_category` from `PipeSignatureBlueprint` | schema generator (`pipelex-dev generate-mthds-schema`) | runs clean in `make agent-check` |
| Schema generator requires `type` on every pipe blueprint variant (set derived from `PipeBlueprintUnion`, no hardcoded drift) so a type-less pipe table fails with a clear "missing type" instead of an ambiguous `oneOf` multi-match | `pipelex/language/mthds_schema_generator.py` (`_require_type_on_pipe_definitions`) | `tests/unit/pipelex/language/test_mthds_schema.py` |
| Docs + CHANGELOG | `docs/building-methods/pipes/signature-pipes.md`, `docs/tools/cli/validate.md`, `docs/tools/cli/agent-cli.md`, `mkdocs.yml` (nav), `pipelex/builder/CLAUDE.md`, CHANGELOG `[Unreleased]` | — |

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

## Done: Phase 7.4 — cross-repo schema merge-gate (closed)

The merge-gate is closed. `pipelex-tools` 0.6.0 (PyPI) and the matching `vscode-pipelex` extension release bundle an MTHDS schema that knows `type = "PipeSignature"` and requires `type` on every pipe variant. On this branch, in lock-step:

1. ✅ `vscode-pipelex` / `pipelex-tools` 0.6.0 shipped the schema-aware bundled `plxt`.
2. ✅ The branch-local `[[rule]] / [rule.schema]` block was removed from **both** `.pipelex/plxt.toml` and the `pipelex/kit/configs/plxt.toml` template (the two are byte-identical again, with no net change versus `dev`), the `pipelex-tools` floor in `pyproject.toml` is bumped to `>=0.6.0`, and the now-vestigial `generate-mthds-schema-quiet` prerequisite on the `plxt-lint` / `merge-check-plxt-lint` Makefile targets (which existed only to feed the branch-local rule) was reverted — `plxt lint` now validates `.mthds` against the bundled schema directly.
3. ✅ Re-verified with the bundled `plxt` 0.6.0 installed and the branch-local rule gone: `make plxt-lint` is green across the repo — including `tests/e2e/fixtures/signature_bundles/*.mthds`, which use `type = "PipeSignature"` and now validate against the bundled schema — and `make ccs` (config-sync) passes.

The earlier ⚠️ counter-item — the branch-local schema block having been copied into the user-shipped `pipelex/kit/configs/plxt.toml` template — is resolved by step 2: the block is gone from the template, so `pipelex init` no longer points end-user projects at a `derived/mthds_schema.json` path that does not exist for them.

## History

The phase-by-phase TDD implementation log lives at [`archive/signature-based-validation-tdd-plan.md`](archive/signature-based-validation-tdd-plan.md) (kept as the build record; this doc is the live current-state reference).
