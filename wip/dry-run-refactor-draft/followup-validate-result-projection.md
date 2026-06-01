# Follow-ups — validate-result JSON projection (`build_validated_pipes`) — RESOLVED

The three follow-ups that surfaced from the self-review of the Phase-3a caller-migration fixes are **resolved** on branch `feature/Validate-with-signatures-4-fix-dry-run` by **unifying every validate surface on the namespaced `pipe_ref`**. One cross-repo task remains (skills — see bottom).

## What was decided and done

The decision (Item A) was to **unify on `pipe_ref`** rather than keep the bare-vs-namespaced split. That choice dissolved Item B and folded in Item C.

- **Item A (identity inconsistency) — resolved by unification.** Every `validated_pipes` entry now carries the namespaced `pipe_ref` (`domain.code`), on all surfaces: agent `validate all` / `validate bundle` / `validate pipe` / `validate pipe --bundle`, and all builder validate ops. The same pipe can no longer be reported under two identifiers from the same CLI. `build_validated_pipes` (in `pipelex/pipeline/validate_bundle.py`) dropped its now-vestigial `use_ref` parameter and always emits `output.pipe_ref`.

- **Item B (single-pipe echo: input-arg → resolved-bare) — moot under unification.** Verification found this delta actually spanned **four** functions, not the two the original draft named: the two non-bundle single-pipe paths (`validate_pipe`, `validate_pipe_core`) **and** the two bundle-slice paths (`validate_pipe_in_bundle`, `validate_pipe_in_bundle_core`) all echoed the caller's input arg before Phase-3a and emitted the bare resolved code after. The behaviour was reachable (`get_required_pipe` resolves a namespaced ref by direct `domain.code` lookup) but untested (every existing test passed a bare code). Unifying on `pipe_ref` makes the question moot — all four now emit the namespaced ref regardless of the form the caller passed, so there is nothing left to revert or pin.

- **Item C (loose `dict[str, str]` return type) — resolved.** Introduced `ValidatedPipeEntry(TypedDict)` with `pipe_code: str` and `status: DryRunStatus`; `build_validated_pipes` now returns `list[ValidatedPipeEntry]`. The `pipe_code` key name is kept for the published JSON contract, but its value is the qualified ref. Passes pyright + mypy.

## In-repo changes

- `pipelex/pipeline/validate_bundle.py` — `build_validated_pipes` rewritten (no `use_ref`, always `pipe_ref`); added the `ValidatedPipeEntry` TypedDict.
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py` — dropped `use_ref=True` from the all/bundle call sites; trimmed the now-obsolete per-surface identity comments (the C-8 status-truthfulness note stays).
- `pipelex/builder/operations/validate_ops.py` — no call-site edits needed (the five ops were already param-less); they now emit namespaced refs via the changed helper.
- `tests/integration/pipelex/cli/test_agent_validate_pipe_in_bundle.py` — the two bare-identity asserts updated to the namespaced form (`slice_bundle.implemented_pipe`, `slice_xpkg.cross_parallel`).
- `pipelex/cli/agent_cli/CLAUDE.md` — documented the unified namespaced-identity contract.
- `CHANGELOG.md` — `[Unreleased] → Changed` entry (consumer-facing contract change).

Green on the working tree: `make agent-check` clean (pyright 0 / mypy 0); targeted validate + builder + full CLI suites pass.

## Remaining — cross-repo (NOT done here)

The MTHDS **skills** repo (`../skills/skills/`, not checked out in this workspace) consumes the agent-CLI `validate` JSON, and the single-pipe `validate pipe` surfaces flipped from bare to namespaced `domain.code` (the `validate all` / `validate bundle` surfaces were already namespaced and are unchanged). A self-contained SWE-agent handoff for that update — what changed, the highest-risk pattern, where to look, how to verify — lives alongside this doc: [`handoff-skills-validate-namespaced-identity.md`](handoff-skills-validate-namespaced-identity.md). This is the one open item; it could not be verified or changed from this repo.
