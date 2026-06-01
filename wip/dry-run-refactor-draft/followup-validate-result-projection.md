# Follow-ups — validate-result JSON projection (`build_validated_pipes`)

Three follow-ups surfaced by the **self-review of the Phase-3a caller-migration fixes** (the work that fixed the hardcoded-`"SUCCESS"` bug, the builder masking bug, and extracted the shared `build_validated_pipes` projection). Branch: `feature/Validate-with-signatures-4-fix-dry-run`.

These are about the `validated_pipes` JSON envelope that `validate` commands return to skills/agents — its per-pipe identity and its type. None is a correctness bug in the landed fix; they are a tracked **product decision** (Item A) and two **quality/contract items** (Items B, C). The numbering here (A/B/C) is local to this doc; it maps to self-review items **#1 / #2 / #4** respectively.

## Background — what `build_validated_pipes` does

`pipelex/pipeline/validate_bundle.py` now hosts:

```python
def build_validated_pipes(dry_run_result: dict[str, DryRunOutput], *, use_ref: bool = False) -> list[dict[str, str]]:
    return [{"pipe_code": output.pipe_ref if use_ref else output.pipe_code, "status": output.status} for output in dry_run_result.values()]
```

Every `validate` surface in `pipelex/builder/operations/validate_ops.py` (builder) and `pipelex/cli/agent_cli/commands/validate/_validate_core.py` (agent CLI) calls it to turn a `DryRunOutput` map into the `{"validated_pipes": [{"pipe_code", "status"}], "total_pipes"}` envelope. `DryRunOutput` (in `pipelex/pipeline/bundle_validator.py`) carries `pipe_code` (bare), `pipe_ref` (namespaced `domain.code`), `status: DryRunStatus`, `error_message`.

## Cold-start protocol (verifying these in a fresh session)

1. Read this file. **Verify by symbol, not line number** — grep the function names below; the migration may have moved lines.
2. Confirm the `use_ref` matrix (Item A) is still as described: grep `build_validated_pipes(` across `validate_ops.py` and `_validate_core.py` and note the `use_ref` value per caller.
3. Tests that pin the current identity contract (run them before/after any change):
   - `tests/integration/pipelex/cli/test_agent_validate_pipe_in_bundle.py` — asserts the **bare** `"implemented_pipe"` in `pipe_codes`.
   - `tests/integration/pipelex/cli/test_agent_validate_defaults_strict.py::test_agent_validate_allow_signatures_succeeds` — asserts the **namespaced** `"agent_sigcli.agent_sig"` / `"agent_sigcli.agent_seq"`.
   - Targeted run: `.venv/bin/pytest -p no:randomly -q tests/integration/pipelex/cli/test_agent_validate_pipe_in_bundle.py tests/integration/pipelex/cli/test_agent_validate_defaults_strict.py tests/unit/pipelex/cli/agent_cli/test_validate_format.py`
4. The skills that consume this JSON live in `../skills/skills/` (e.g. `mthds-check`, `mthds-fix`) and `pipelex/cli/agent_cli/CLAUDE.md` documents the `validate` markdown/JSON contract — any identity change (Item A) is a consumer-facing contract change, check there.

---

## Item A — Agent-CLI pipe identity is inconsistent (namespaced vs bare) — PRODUCT DECISION (self-review #1)

**Status:** open decision. Not a bug; the landed fix preserved the pre-existing behavior. Tracking it because it's a real consumer-facing inconsistency that the `build_validated_pipes` extraction *centralized* but did **not** resolve.

**The inconsistency.** The `pipe_code` field of each `validated_pipes` entry is sometimes the bare code, sometimes the namespaced ref, depending on the surface:

| Surface | Function | `use_ref` | entry `pipe_code` value |
|---|---|---|---|
| agent `validate all` | `validate_all_core` | `True` | namespaced `pipe_ref` (`domain.code`) |
| agent `validate bundle` | `validate_bundle_core` | `True` | namespaced `pipe_ref` |
| agent `validate pipe` | `validate_pipe_core` | `False` | bare `code` |
| agent `validate pipe --bundle` | `validate_pipe_in_bundle_core` | `False` | bare `code` |
| builder (all 5 ops) | `validate_*` in `validate_ops.py` | `False` | bare `code` |

So `pipelex-agent validate all` reports `slice_bundle.implemented_pipe` while `pipelex-agent validate pipe implemented_pipe` reports `implemented_pipe` — the **same pipe under two identifiers**, from the same CLI. The original Phase-3a review's finding #9 named this divergence ("the two validate-all surfaces disagree on identity") as the smell; the extraction de-duplicated the mechanics but turned the divergence into a parameter rather than removing it.

**The decision to make.** Either:

- **(a) Unify on `pipe_ref` everywhere** (namespaced is the unambiguous identity; cross-domain collisions impossible). This is a **consumer contract change**: it changes the bare-emitting surfaces' output and would require updating the bare-asserting tests (`test_agent_validate_pipe_in_bundle.py`) and any skill that parses `pipe_code` expecting the bare form. Also resolves Item B for free (single-pipe paths would emit `pipe_ref`).
- **(b) Keep the dual contract** but document it as intentional (e.g. "single-pipe/slice surfaces echo the bare code the user asked for; whole-set surfaces use namespaced refs to disambiguate across domains"). If chosen, write that rationale where the contract is documented (`pipelex/cli/agent_cli/CLAUDE.md`) so it stops reading as an accident.

**Recommendation:** raise with whoever owns the agent-CLI/skill contract before changing — it touches the published JSON surface the skills parse. Do not silently flip it.

---

## Item B — Single-pipe paths echo the resolved bare code, not the input argument (self-review #2)

**Status:** open — small, unrequested behavior change introduced by the extraction; decide *revert* or *accept*.

**What changed.** Before the extraction, the single-pipe **non-bundle** paths echoed the caller's input argument verbatim:

```python
# old
"validated_pipes": [{"pipe_code": pipe_code, "status": dry_run_results[the_pipe.pipe_ref].status}]
```

After the extraction they build the entry from the resolved `DryRunOutput`:

```python
# new
"validated_pipes": build_validated_pipes(dry_run_results)   # use_ref=False → output.pipe_code (bare)
```

Affected functions:

- `pipelex/builder/operations/validate_ops.py::validate_pipe`
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py::validate_pipe_core`

**The behavior delta.** `output.pipe_code` is always the **bare** `.code`. So if a caller passes a **namespaced** ref (e.g. `pipelex-agent validate pipe my_domain.my_pipe`), the echoed `pipe_code` is now `my_pipe` instead of the `my_domain.my_pipe` the caller passed. For a bare input the two are identical — which is why the existing tests (all pass bare codes) stayed green and the change slipped through silently. There is **no test** covering a namespaced input to these two functions.

**Why it matters.** This is outside the scope of the fixes that were requested (status truthfulness + de-dup). It's arguably *more* consistent with the builder surface, but it's an untested, unrequested contract change.

**How to verify in a fresh session.**

1. Grep `validate_pipe(` in `validate_ops.py` and `validate_pipe_core` in `_validate_core.py`; confirm both build `validated_pipes` via `build_validated_pipes(dry_run_results)`.
2. Reproduce: call `validate_pipe_core(pipe_code="<domain>.<code>", ...)` against a loaded library and inspect `result["validated_pipes"][0]["pipe_code"]` — today it returns the bare `<code>`.

**Two ways to resolve.**

- **Revert the echo:** keep these two functions emitting the input `pipe_code` (build the one-entry list inline, or pass the desired id into the helper). Lowest-surprise; preserves the "echo what you asked for" contract for single-pipe calls.
- **Accept + lock it:** if Item A lands as "(a) unify on `pipe_ref`," this becomes moot (everything namespaced). If Item A lands as "(b) dual," then add a regression test asserting the single-pipe echo form you chose, so it stops being silent.

**Recommendation:** decide Item A first; Item B's resolution falls out of it. If Item A is deferred, revert the echo to the input arg (smallest, safest) and add the missing test.

---

## Item C — `build_validated_pipes` returns `dict[str, str]` while `status` is a `DryRunStatus` (self-review #4)

**Status:** open — type-honesty / self-documentation improvement on a fresh public helper. Cheap, no behavior change.

**The issue.** `build_validated_pipes` is annotated `-> list[dict[str, str]]`, but each dict is heterogeneous: `pipe_code` is a `str`, `status` is a `DryRunStatus` (a `StrEnum`). It only type-checks because `StrEnum` subclasses `str`. The dict-of-str annotation hides the real shape, and the JSON envelope has no named type. (This predates the extraction — the old hand-rolled projections had the same `dict[str, str]` annotation — but the extraction was the moment to fix it on the one shared helper.)

**Proposed change.** Introduce a `TypedDict` for the envelope entry and return it:

```python
from typing import TypedDict

class ValidatedPipeEntry(TypedDict):
    pipe_code: str
    status: DryRunStatus

def build_validated_pipes(dry_run_result: dict[str, DryRunOutput], *, use_ref: bool = False) -> list[ValidatedPipeEntry]:
    ...
```

This names the contract, makes `status` honest, and lets callers' `dict[str, Any]` return types be tightened later if desired.

**Watch-outs when verifying.**

- The dict values stay `DryRunStatus` instances at runtime (StrEnum) and serialize to their string value via `json.dumps` — confirm `pipelex/cli/agent_cli/commands/validate/_output_helpers.py::format_validate_markdown` and the JSON path still render correctly (they read `entry["pipe_code"]` / `entry["status"]`).
- The callers return `dict[str, Any]` envelopes, so `ValidatedPipeEntry` flows into an `Any` and won't ripple. No call-site signature changes required.
- `make agent-check` (pyright + mypy) is the gate — `TypedDict` with a `DryRunStatus` field must pass both.

**Recommendation:** apply standalone; it's a low-risk, self-contained typing improvement. Add no new test (pure typing); rely on `make agent-check` + the existing validate-format tests.

---

## Not tracked here (resolved or judged not worth it during self-review)

- **Iteration source / list order** (self-review #3): the bundle/all paths now iterate `dry_run_result.values()` instead of `result.pipes`, so SKIPPED pipes can sort first. Counts are provably equal (library enforces unique `pipe_ref`); order is not contract-tested. Judged a non-issue — noted only so a future reviewer doesn't re-flag it.
- **Helper location/naming** (self-review #5): `build_validated_pipes` lives in `validate_bundle.py` (lowest common import ancestor for builder + CLI); `use_ref` is terse. Minor; left as-is. A `DryRunOutput.to_validated_entry(...)` method would be the cleaner alternative if Item C is done.
- **Comment redundancy** (self-review #6): the C-8 rationale appears in the helper docstring and two call sites. Trivial.
