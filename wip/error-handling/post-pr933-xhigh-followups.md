# Plan — post-PR #933 xhigh `/code-review` follow-ups

Action plan for the 15 findings surfaced by the xhigh-effort `/code-review` pass
over the branch `feature/post-pr933-followups`. Each finding has a verify step
(cold-start: confirm the bug/behavior still matches the description), then a
decision needed from the user, then the fix/test work where applicable.

The first 9 findings are NEW concerns not raised in the prior review. The last
6 are re-surfaced versions of the already-decided findings from
[`./post-pr933-followups-code-review.md`](./post-pr933-followups-code-review.md) —
included here for recall completeness and quick re-verification, not for
re-deciding.

## Branch context (cold start)

- **Branch**: `feature/post-pr933-followups`, stacked on `feature/API-readiness-2`
  (PR #933 still open against `dev` at time of writing). Do NOT rebase onto
  `dev` until PR #933 lands.
- **Prior plans on this branch**:
  - [`./post-pr933-review-followups.md`](./post-pr933-review-followups.md) — the
    original 4-phase (A/B/C/D) plan that drove the first 12 commits.
  - [`./post-pr933-followups-code-review.md`](./post-pr933-followups-code-review.md) —
    a pre-PR `/code-review` pass that flagged 6 findings (F1-F6); all 6 were
    resolved in a follow-up session (4 commits' worth of changes: CHANGELOG
    fix, `DisclosureMode.STRICT` docstring extension, new pinning test,
    `_translate_to_validate_bundle_error` extended to `load_concepts_only*`,
    plus decision-recording entries).
- **State at cold start** (check on entry):
  - The 4 follow-up commits resolving F1-F6 may or may not have been committed.
    Check `git status` and `git log --oneline feature/API-readiness-2..HEAD`.
  - If uncommitted: a `git diff HEAD --stat` should show changes to
    `CHANGELOG.md`, `pipelex/base_exceptions.py`,
    `pipelex/pipeline/validate_bundle.py`,
    `tests/unit/pipelex/test_error_report_disclosure_mode.py`, and a new entry
    in `wip/error-handling/post-pr933-followups-code-review.md`.
  - Either way, this plan layers ON TOP of that state — verify each finding
    against the current code, not the pre-resolution code.
- **What this plan is**: the xhigh `/code-review` pass ran 5 finder angles (40
  raw candidates), 7 verifiers (2 CONFIRMED, 5 PLAUSIBLE, 1 REFUTED), and a
  sweep (8 more, 2 actionable). After dedup against the prior 6 findings: 9
  NEW concerns + 6 re-verifications. This is the resulting work plan.

## How to start (cold start)

1. **Read this whole file** — every finding names the exact `file:line`, the
   verify step, the decision needed, and the fix/test work.
2. **Confirm branch state**: `git status`, `git log --oneline feature/API-readiness-2..HEAD`.
3. **Confirm baseline is green**: `make agent-check` + `make agent-test` BEFORE
   touching anything. If either fails on entry, stop and investigate — this
   plan assumes a green baseline.
4. **Phases are independent** — pick the one that matches the available time
   budget. Phase A is the smallest (2 small fixes); Phase B needs a design
   decision per finding before action; Phase D is verification-only.
5. **Make each finding a fresh commit on top** of the existing branch history.
   Do NOT rewrite history of the 12 phase commits or the 4 F1-F6 resolution
   commits.

## Ground rules

- `make agent-check` after every code change. `make agent-test` before each
  phase checkpoint.
- No backward-compat shims (project policy).
- One `TestClass` per test module; use `pytest-mock` (`MockerFixture`), not
  `unittest.mock`. See `.claude/rules/pytest-standards.md`.
- StrEnum rule: never `enum_var.value`, just `{enum_var}`. See
  `.claude/rules/python-standards.md`.
- Pyright catches `model_copy` validator-skip drift only through behavior —
  not the call shape. Pin behavior with tests, not type annotations.

---

## Phase A — HIGH severity (CONFIRMED real bugs)

Two clean fixes. No design ambiguity. Land as two separate commits.

### A.1 — Unify return-placement across the 4 `validate_bundle*` entry points

**File**: `pipelex/pipeline/validate_bundle.py:176` (`validate_bundles_from_directory`)
and `:291` (`load_concepts_only_from_directory`).

**What**: After the Phase C.2 refactor (extracting
`_translate_to_validate_bundle_error`) and the F5 working-diff extension to
`load_concepts_only*`, the four bundle-loading entry points split into two
shapes:

- `validate_bundle` (block at 121-159): `return ValidateBundleResult(...)` at
  lines 135, 142, 159 — INSIDE the `with`.
- `validate_bundles_from_directory` (block at 169-175): `return ValidateBundleResult(...)`
  at line 176 — OUTSIDE the `with`.
- `load_concepts_only` (block at 227-260): `return LoadConceptsOnlyResult(...)`
  at lines 240, 245, 260 — INSIDE.
- `load_concepts_only_from_directory` (block at 285-290):
  `return LoadConceptsOnlyResult(...)` at line 291 — OUTSIDE.

`ValidateBundleResult` / `LoadConceptsOnlyResult` are plain pydantic BaseModels
with typed `list[…]` fields and no `arbitrary_types_allowed`. A wrong-typed
list element raises `pydantic.ValidationError` at construction. From inside the
`with`, the helper's `except ValidationError` arm translates it to a
user-facing `ValidateBundleError(pipe_validation_errors=...)`. From outside
the `with`, it propagates raw.

**Why it matters**: same internal contract bug → two different error envelopes
depending on which entry point the caller used. Inconsistent for downstream
handlers that only `except ValidateBundleError`.

**Verify**:

- [ ] `grep -n "with _translate_to_validate_bundle_error\|return ValidateBundleResult\|return LoadConceptsOnlyResult" pipelex/pipeline/validate_bundle.py`
      and confirm the line numbers above still match.
- [ ] Confirm `ValidateBundleResult` and `LoadConceptsOnlyResult` are plain
      `BaseModel` with no `model_config` override (around lines 29 and 179) —
      so they CAN raise `pydantic.ValidationError` from construction.

**Decision needed**: confirm Plan A (move returns inside) is the right
direction vs Plan B (move all returns outside, drop translation of result-
construction errors). Default to Plan A — translating result-construction
errors as `ValidateBundleError` is the more useful envelope for callers, and
all four entry points already share a `ValidateBundleError`-as-public-surface
contract.

**Fix** (Plan A):

- [ ] In `validate_bundles_from_directory`: move the `return
      ValidateBundleResult(blueprints=all_blueprints, pipes=loaded_pipes,
      dry_run_result=dry_run_results)` from line 176 to just above the `with`
      block exit (i.e. at the new last line inside `with`). Indent accordingly.
- [ ] Same for `load_concepts_only_from_directory` at line 291 → move
      `return LoadConceptsOnlyResult(blueprints=all_blueprints,
      concepts=loaded_concepts)` inside the `with` block.

**Test**:

- [ ] Add `tests/unit/pipelex/pipeline/test_validate_bundle_return_placement.py`
      (or extend the existing concepts-only test file at
      `tests/integration/pipelex/pipeline/test_load_concepts_only.py` — pick
      whichever already has the right fixtures). Use `mocker.patch.object` to
      replace `ValidateBundleResult.__init__` (or the model itself) with a
      stub that raises `pydantic.ValidationError`. Then call each of the four
      entry points and assert each raises `ValidateBundleError` — not raw
      `ValidationError`.
- [ ] Teeth check: temporarily revert the fix in one entry point; the test
      for that entry point must fail. Restore.

**Commit**: `fix(validate): translate result-construction errors uniformly across all 4 bundle entry points`

### A.2 — Tear down `open_library()` on translated re-raise (library_id leak)

**File**: `pipelex/pipeline/validate_bundle.py:112-113`, `:167-168`,
`:219-220`, `:283-284` — all four entry points.

**What**: Every entry point calls `library_manager.open_library()` +
`set_current_library(library_id=library_id)` BEFORE entering the `with`
block, with no `try/finally` teardown. When the helper translates and
re-raises a `ValidateBundleError`, the opened `library_id` is leaked. Phase
C.2 + F5 consolidated the duplication and now surface this leak as a shared
anti-pattern across all four callers (pre-existing, but easier to fix in one
sweep now).

**Why it matters**: an IDE/server process that calls `validate_bundle` once
per user save accumulates one un-torn-down Library per failed validation.
Library count grows monotonically; stale entries can shadow re-loads of the
same bundle path under the same key, producing confusing 'stale validation
result' bugs on subsequent saves. The leak amplitude depends on how often the
caller validates failing bundles — which is "every save while syntax-erroring"
for the IDE/agent build flow, i.e. high.

**Verify**:

- [ ] Read `pipelex/hub.py` (or wherever `get_library_manager()` resolves) to
      find the teardown API. Look for `close_library`, `release_library`,
      `__exit__`, or a context-manager wrapper.
- [ ] If none exists, the fix has TWO parts: (a) add teardown API to
      `LibraryManager`, (b) wire it into the four entry points. If one
      exists, just wire it in.
- [ ] Determine whether `set_current_library` also needs a "reset" call on
      teardown (it sets contextvar / thread-local state).

**Decision needed**:

- **A.2-1**: confirm teardown API exists (or how to add it).
- **A.2-2**: choose pattern — try/finally + explicit teardown call, OR
  context manager on `LibraryManager.open_library()` returning `(id, library)`
  via `__enter__`. Recommend context manager for self-documenting cleanup.
- **A.2-3**: in-scope here, or split off as a separate `library-leak`
  remediation plan? Recommend in-scope — it's a 4-call-site sweep and
  consolidated by the helper refactor.

**Fix**:

- [ ] If `LibraryManager` lacks teardown: add `close_library(library_id)` or
      a `library_session(...)` context manager. Document and test in
      isolation first.
- [ ] In each of the four entry points: wrap from `open_library()` through
      the final `return` in `try/finally` (or replace with `with library_session(...) as (library_id, library):`).
- [ ] Make sure the teardown also resets the `set_current_library` state if
      relevant (avoid stale contextvar across requests).

**Test**:

- [ ] `tests/unit/pipelex/pipeline/test_validate_bundle_library_lifecycle.py`:
      use `mocker.spy` on the teardown API. Trigger a `ValidateBundleError`
      from each entry point (e.g. malformed `mthds_contents`). Assert
      teardown was called exactly once. Assert the spy reports the same
      `library_id` that `open_library` returned.
- [ ] Teeth check: temporarily remove the `try/finally` in one entry point;
      the test for that entry point must fail.

**Commit**: `fix(validate): tear down LibraryManager on bundle-validation failure`

### ⛔ CHECKPOINT A — STOP, verify, record

- [ ] `make agent-check` clean.
- [ ] `make agent-test` clean.
- [ ] Each fix as its own commit.
- [ ] Append a dated entry to the Session log below.

---

## Phase B — MEDIUM severity (design discussion before action)

Two findings where the fix has design ambiguity. Open with the user before
acting.

### B.1 — V6: STRICT projection two-branch asymmetry

**File**: `pipelex/base_exceptions.py:226` (caller-facing branch) and
`:234` (redacted branch).

**What**: The two STRICT branches use opposite field-selection strategies:

- Caller-facing branch (line 226): `projected = {k: v for k, v in
  payload.items() if k not in _STRICT_PASSTHROUGH_DROPPED_FIELDS}` — EXCLUSION
  filter (denylist). Today's denylist is just `provider`, `model`,
  `caller_facing_message`.
- Redacted branch (line 234): `redacted = {k: payload[k] for k in
  _STRICT_KEPT_FIELDS if k in payload}` — INCLUSION filter (allowlist).
  Today's allowlist is `error_type`, `title`, `type_uri`, `error_domain`,
  `error_category`, `retryable`.

The two branches would diverge on any future top-level `ErrorReport` field:
caller-facing branch would emit it silently (not in dropped set), redacted
branch would silently drop it (not in kept set). The `user_action` field
already demonstrates the divergence pattern (kept on caller-facing because
caller-facing keeps the message context, intentionally dropped on redacted).
No test pins the canonical STRICT-emitted field set or asserts cross-branch
parity for non-divergent fields.

**Why it matters**: adding a new public ErrorReport field for finer client
routing (e.g. `error_subcategory`, `correlation_id`, `severity`) would
silently appear on one STRICT envelope and silently disappear from the other.
Downstream consumers that route on the new field see inconsistent behavior.
The redacted branch erring on the side of dropping is the safer default — no
accidental leak — but the divergence is a refactor trap.

**Verify**:

- [ ] Re-read `pipelex/base_exceptions.py` lines 193-244 and the constants
      `_STRICT_KEPT_FIELDS`, `_STRICT_PROVIDER_FIELDS`,
      `_STRICT_PASSTHROUGH_DROPPED_FIELDS`,
      `_STRICT_PROVIDER_METADATA_KEPT_FIELDS`.
- [ ] Confirm: no test in
      `tests/unit/pipelex/test_error_report_disclosure_mode.py` asserts the
      canonical STRICT field set, parity, or "all populated fields are
      accounted for".

**Decision needed** (three options):

- **B.1-a** (recommended — single source of truth): factor out a shared
  allowlist (extend `_STRICT_KEPT_FIELDS` or introduce `_STRICT_BASE_FIELDS`).
  The redacted branch uses just that set; the caller-facing branch uses the
  same set plus an explicit overlay of `message` + `user_action` (the two
  fields that legitimately diverge between branches). Both branches then go
  through one place when a new field is added. Cost: a small refactor of
  `to_dict`, possibly clearer.
- **B.1-b** (parity test only, no code change): add a test that constructs an
  `ErrorReport` with every populated field, runs STRICT on both branches,
  asserts the kept-key sets match modulo `message`/`user_action`. Future
  field additions break the test loudly. Cost: 1 test, ~10 lines.
- **B.1-c** (document and leave): add a paragraph to the `DisclosureMode.STRICT`
  docstring naming the asymmetry and the per-branch update protocol for
  future fields. Cost: just docs.

Recommend B.1-a — it eliminates the trap. B.1-b is the minimal change.

**Fix** (depends on decision):

- [ ] B.1-a: refactor `to_dict` to share one allowlist. Both branches read
      from the same set; caller-facing overlays the two diverging fields.
      Add the parity test from B.1-b as a bonus pin.
- [ ] B.1-b: add the parity test only.
- [ ] B.1-c: add the docstring paragraph only.

**Test** (always add, regardless of code-fix choice):

- [ ] `test_strict_branch_kept_field_parity` in
      `tests/unit/pipelex/test_error_report_disclosure_mode.py` — populate
      every optional field on a caller-facing report, STRICT-project, assert
      `set(strict_caller_facing) - {"message", "user_action"} == set(strict_redacted) - {"message"}`.

**Commit**: `refactor(errors): unify STRICT projection branch field-selection (B.1-a)` —
or `test(errors): pin STRICT branch field-set parity` for B.1-b.

### B.2 — S2: Concept ValidationError mislabeled as "Pipe Validation Errors"

**File**: `pipelex/pipeline/validate_bundle.py:65` (the `except ValidationError`
arm in `_translate_to_validate_bundle_error`).

**What**: The shared helper's `except ValidationError` arm calls
`categorize_pipe_validation_error(validation_error)` at
`pipelex/core/pipes/handle_pipe_errors.py:46`, which produces
`pipe_validation_errors=[...]` and a message framed as "Could not load
blueprints because of: ..." with pipe-specific categorization. Pre-F5
(working diff in
[`./post-pr933-followups-code-review.md`](./post-pr933-followups-code-review.md)),
`load_concepts_only*` had their own inline `except ValidationError` arm that
called the SAME categorizer — so the mislabeling is pre-existing for the
concepts-only path. F5 widened the surface (4 entry points now share it) and
the doc-review-followups doc made the helper docstring claim "single source
of truth", which makes the mislabeling more visible.

A concept-side validation error (a `Concept` field failing strict validation)
now reaches the user via a "Pipe Validation Errors" header. The error data
is preserved; the framing is wrong.

**Why it matters**: UX/diagnostic quality. A user searches for the pipe name
shown in the header, finds none, files a misleading bug. Not a correctness
bug; not a security bug. Worth fixing because the F5 consolidation made the
mislabeling cross-cutting.

**Verify**:

- [ ] Read `pipelex/core/pipes/handle_pipe_errors.py` —
      `categorize_pipe_validation_error` at line 46. Confirm it builds a
      pipe-framed error list independent of the source.
- [ ] Grep for downstream consumers of `ValidateBundleError.pipe_validation_errors`
      to see how the framing is surfaced.
- [ ] Trigger the bug: in a fresh `.mthds` bundle, declare a concept with a
      field that violates pydantic validation. Run `pipelex validate` and
      `load_concepts_only` against it. Observe the surfaced framing on each.

**Decision needed** (three options):

- **B.2-a** (parameterize): give the helper a `category: Literal["pipe", "concept"]`
  parameter that switches the categorizer (and the message framing). The two
  bundle-validation call sites pass `"pipe"` (default); the two concepts-only
  call sites pass `"concept"`. Cost: small refactor, two new categorizer
  variants (or one with a parameter).
- **B.2-b** (split helpers): keep the existing helper, add a sibling
  `_translate_to_validate_bundle_error_concepts_only` for the two
  concepts-only entry points. Re-introduces the duplication the F5 fix
  reduced. Not recommended.
- **B.2-c** (accept + document): document the mislabeling in the helper
  docstring; add a `concept_validation_errors` field on `ValidateBundleError`
  only if and when a downstream consumer needs the differentiation. Cheapest;
  preserves the UX bug.

Recommend B.2-a — adds one parameter, eliminates the mislabeling cleanly,
preserves the single-helper structure F5 introduced.

**Fix** (B.2-a):

- [ ] Add a sibling `categorize_concept_validation_error` in
      `pipelex/core/pipes/handle_pipe_errors.py` (or rename + parameterize
      the existing one — discuss).
- [ ] In `_translate_to_validate_bundle_error`, accept a `category` parameter
      and route to the right categorizer + message framing inside the
      `except ValidationError` arm.
- [ ] Update the four call sites: the two `validate_bundle*` pass `"pipe"`
      (or omit if default); the two `load_concepts_only*` pass `"concept"`.
- [ ] Optionally add a `concept_validation_errors` field to
      `ValidateBundleError` if the structured payload differs. Discuss.

**Test**:

- [ ] Extend the concepts-only test file (or add
      `test_concept_validation_error_framing.py`) with a case that triggers
      a concept-side pydantic ValidationError via `load_concepts_only` and
      asserts the resulting `ValidateBundleError`'s message + payload uses
      concept framing, not pipe framing.
- [ ] Teeth check: revert the categorizer-routing change; the test must
      fail.

**Commit**: `fix(validate): differentiate concept vs pipe ValidationError framing in shared helper`

### ⛔ CHECKPOINT B — STOP, verify, record

- [ ] `make agent-check` clean.
- [ ] `make agent-test` clean.
- [ ] Each fix as its own commit.
- [ ] Append a dated entry to the Session log below.

---

## Phase C — LOW severity (latent footguns, mixed action)

Five findings. Mix of trivial fixes, pin-with-test, and accept-as-documented.

### C.1 — V1: Whole-object `or` suppresses cause's actionable `provider_metadata`

**File**: `pipelex/cogt/exceptions.py:102` (`CogtError.to_error_report` —
`"provider_metadata": self.provider_metadata or base_report.provider_metadata`)
and `pipelex/base_exceptions.py:500`
(`_enrich_error_report_from_cause` — `report.provider_metadata or cause_report.provider_metadata`).

**What**: Both use whole-object OR on always-truthy Pydantic models
(`bool(ProviderErrorMetadata(...))` is always True regardless of internal
state). A wrapper that explicitly constructs a `ProviderErrorMetadata` with
no actionable hints (`status_code=None, retry_after_seconds=None`) — for
attribution-only purposes — would discard the cause's actionable
`status_code=429, retry_after_seconds=12.0`. Latent today: grep confirms only
leaf workers (`pipelex/cogt/inference/error_render.py:112,119`,
`pipelex/plugins/azure_rest/azure_img_gen_worker.py:84,191,210`) set
non-None `provider_metadata` — they raise from the SDK exception, not from
another CogtError. No wrapper currently triggers this.

**Why it matters**: the Phase D.1 STRICT-disclosure work specifically
preserves `retry_after_seconds` for the HTTP adapter to emit `Retry-After`
headers. If a future contributor adds a wrapper `CogtError` that attaches
attribution-only metadata, the OR-chain silently loses the retry hint — the
very thing Phase D.1 was designed to preserve.

**Verify**:

- [ ] Re-read both call sites. Confirm the OR pattern.
- [ ] `grep -rn "ProviderErrorMetadata(" pipelex/ --include="*.py"` to
      confirm no wrapper currently constructs one. (At time of writing: only
      leaves.)

**Decision needed** (three options):

- **C.1-a** (per-field merging): switch both call sites to per-field merging:
  ```python
  if self.provider_metadata is not None or base_report.provider_metadata is not None:
      merged_metadata = ProviderErrorMetadata(
          provider=(self.provider_metadata and self.provider_metadata.provider)
                   or (base_report.provider_metadata and base_report.provider_metadata.provider),
          ...
      )
  ```
  Heavier; restores semantics for the latent future case. Risk: drift between
  the two call sites if the merge logic isn't shared in a helper.
- **C.1-b** (pin current behavior, document the trap): add a test that pins
  the wrapper-wins semantics (so a future contributor changing to per-field
  merging makes a deliberate decision), and add a comment naming the
  no-actionable-hints case. No behavior change.
- **C.1-c** (leave as-is, ignore): no trigger today; YAGNI.

Recommend C.1-b — pinning behavior is the right discipline for a documented
latent footgun. C.1-a is overkill for a latent.

**Fix** (C.1-b):

- [ ] Add a test `test_wrapper_provider_metadata_wins_even_when_cause_has_richer_metadata`
      in the appropriate place (`tests/unit/pipelex/cogt/`?) — construct a
      wrapper CogtError with attribution-only `provider_metadata` raised
      `from` a leaf CogtError with actionable `provider_metadata`. Assert the
      resulting `ErrorReport.provider_metadata` equals the wrapper's (i.e.
      empty curated subset under STRICT).
- [ ] Add a one-line comment at both call sites naming the wrapper-wins
      semantics and pointing at the test.

**Test**: see Fix above.

**Commit**: `test(errors): pin wrapper-wins provider_metadata semantics (latent OR-suppression trap)`

### C.2 — V3: `recover_error_report` whitespace-only message bypasses `or` fallback

**File**: `pipelex/temporal/tprl/temporal_error.py:125`.

**What**: `recovered_message = report_dict.get("message") or _message_from_exc(exc)`.
A whitespace-only message (`" "`, `"\n"`, etc.) is truthy in Python, so the
fallback never fires. The function then emits `f"{recovered_message}
{_ERROR_REPORT_VALIDATION_FAILED_MARKER}"` = `" [error report failed schema
validation]"` — a visually broken preamble. The Phase A.3 regression net at
`tests/unit/pipelex/temporal/test_recover_error_report.py:112` pins only the
empty-string case, even though its docstring claims coverage of "empty or
whitespace".

No in-tree writer demonstrably emits whitespace-only messages today, but
nothing prevents one either (e.g. `PipelexError(f"{maybe_empty_var}")` with
a bad substitution). Impact: cosmetic/diagnostic — classification info
(`error_type`, `error_domain`, marker presence) is preserved; only the
human-readable preamble is degraded.

**Verify**:

- [ ] Read the code at the cited line. Confirm the `or` pattern.
- [ ] Read the existing test
      `test_invalid_report_with_empty_message_falls_back_to_exc_chain` —
      confirm it parametrizes only `""`.

**Decision needed**: trivial fix or skip?
Recommend FIX — one-line change, the test pin is already there but
incomplete.

**Fix**:

- [ ] Change line 125 to: `report_message = report_dict.get("message")` then
      `recovered_message = report_message.strip() if report_message and
      report_message.strip() else _message_from_exc(exc)` (or the walrus
      `(msg := report_dict.get("message")) and msg.strip() if (msg :=
      report_dict.get("message")) is not None else None` — pick the more
      readable shape).
- [ ] Same check on line 83 (`_message_from_exc`) if it has the analogous
      truthy-fallback pattern — verify and fix if so.

**Test**:

- [ ] Extend the existing parametrize in
      `tests/unit/pipelex/temporal/test_recover_error_report.py:112` (or add
      a sibling case) with `" "`, `"\n"`, `"\t"`. Assert the fallback fires
      and the synthesized message contains the underlying ApplicationError
      text.
- [ ] Teeth check: revert the strip; the new cases must fail.

**Commit**: `fix(temporal): treat whitespace-only error report message as missing for fallback`

### C.3 — V5: Pin the `PipeValidationError` vs `pydantic.ValidationError` sibling relationship

**File**: `pipelex/pipeline/validate_bundle.py:36-81`
(`_translate_to_validate_bundle_error`).

**What**: The cascade orders `except PipeValidationError` BEFORE
`except ValidationError`. Works today because `PipeValidationError(ValueError)`
is NOT a subclass of `pydantic.ValidationError` (both siblings under
`ValueError`). A future refactor that unifies the hierarchy (e.g.
`class PipeValidationError(pydantic.ValidationError)` to share categorization
machinery) would silently route pydantic ValidationErrors into the
`PipeValidationError` arm. The sibling relationship is NOT pinned by test,
comment, or annotation. The helper docstring claims "single source of truth"
without naming the dependency.

**Verify**:

- [ ] Read `pipelex/core/pipes/exceptions.py` to confirm
      `class PipeValidationError(ValueError)` (sibling, not subclass).
- [ ] Confirm no existing test asserts `not issubclass(PipeValidationError,
      pydantic.ValidationError)`.

**Decision needed**: no design ambiguity. Add the pin.

**Fix + Test** (one commit):

- [ ] Add a test in `tests/unit/pipelex/pipeline/test_validate_bundle_helper.py`
      (or wherever the helper is tested):
      ```python
      def test_pipe_validation_error_is_not_a_pydantic_validation_error_subclass(self) -> None:
          """Cascade ordering in _translate_to_validate_bundle_error depends on this."""
          from pipelex.core.pipes.exceptions import PipeValidationError
          from pydantic import ValidationError
          assert not issubclass(PipeValidationError, ValidationError)
      ```
- [ ] Add a one-line comment in the helper above the
      `except PipeValidationError` clause: `# Cascade order: PipeValidationError must precede ValidationError; their sibling-under-ValueError relationship is pinned by tests/.../test_validate_bundle_helper.py`.

**Commit**: `test(validate): pin PipeValidationError sibling-of-pydantic-ValidationError contract`

### C.4 — V4: `_authors_caller_facing_message=True` inheritance for external `ValidateBundleError` subclasses

**File**: `pipelex/pipeline/exceptions.py` (`ValidateBundleError._authors_caller_facing_message = True`).

**What**: The flag is read via plain attribute access (`base_exceptions.py:456`),
so external subclasses inherit it. The Phase A.2 test
`test_caller_facing_message_inherits_for_validate_bundle_subclass`
deliberately pins this. The `DisclosureMode.STRICT` docstring explicitly says
"STRICT is a classification-projection, not a path-leak shield". So this is
documented design.

The concern is a downstream subclass-and-leak hazard: external packages
subclassing `ValidateBundleError` with a non-caller-facing message would leak
their message verbatim under STRICT.

**Decision needed**: this is a CONTRACT acceptance question, not a code-fix
question. Three options:

- **C.4-a** (no action): the contract is already documented; in-repo subclass
  count is 0 (only an ephemeral test class). External consumers are expected
  to read the docstring. Recommend default.
- **C.4-b** (add a Sphinx-style warning to the `ValidateBundleError` docstring):
  a `!!! note` block calling out the inheritance hazard for external
  subclassers, with a one-line opt-out (`_authors_caller_facing_message = False`)
  example. Cheap; defensive.
- **C.4-c** (change the contract): make the inheritance per-class via
  `cls.__dict__` (matching `_declared_title`). Breaks the Phase A.2 test;
  requires every subclass to opt in. Don't recommend.

**Fix** (C.4-b if chosen):

- [ ] Add a docstring note to `ValidateBundleError` (or its base
      `PipelexInterpreterError` if shared) about the inheritance contract.

**Commit** (only if C.4-b chosen): `docs(errors): note caller_facing_message inheritance hazard for external ValidateBundleError subclasses`

### C.5 — S1: `_RequestIdLog._logger` captured at class-definition time

**File**: `pipelex/temporal/log_temporal.py:96` (WorkflowLog._logger),
`:109` (ActivityLog._logger).

**What**: Phase B.1 hoist captured `workflow.logger` / `activity.logger` as
`ClassVar[Any]` at class-definition (module-import) time. Pre-B.1, each
severity method called `workflow.logger.log(...)` per invocation, picking up
any runtime reassignment of the module attribute. Post-B.1, `_logger` is
bound once. If temporalio ever swapped the module-level instance (vs in-place
mutation, which it does today), all `WorkflowLog` calls would route through
the stale captured adapter.

**Verify**:

- [ ] Read the file. Confirm the `ClassVar[Any] = workflow.logger` pattern.
- [ ] Confirm temporalio's current behavior (in-place mutation, not instance
      replacement) — read `temporalio.workflow` source if possible. If
      uncertain, leave the verify step as "TBD, low priority".

**Decision needed**: this is latent. Two options:

- **C.5-a** (no action): per the F6 decision (same file, same kind of
  concern), YAGNI.
- **C.5-b** (lazy property): change `_logger: ClassVar[Any] = workflow.logger`
  to a `@classproperty` (or plain `@property` on the instance) that reads
  `workflow.logger` fresh each call. Restores pre-B.1 semantics. Cost: small.

Recommend C.5-a unless temporalio's mutation behavior changes.

**Fix** (C.5-b if chosen): see decision above.

**Commit** (only if C.5-b chosen): `refactor(temporal): defer _logger resolution to call time so adapter swaps are picked up`

### ⛔ CHECKPOINT C — STOP, verify, record

- [ ] `make agent-check` clean.
- [ ] `make agent-test` clean.
- [ ] Each finding as its own commit (the ones with code changes).
- [ ] Append a dated entry to the Session log below: which items landed,
      which were deliberately left, and why.

---

## Phase D — Already-documented decisions (re-verify only)

The xhigh review re-surfaced the six already-decided findings from
[`./post-pr933-followups-code-review.md`](./post-pr933-followups-code-review.md)
(F1-F6) for recall completeness. The decisions taken in that session still
stand. This phase is just a sanity check that the documentation, tests, and
code state actually match those decisions — in case the resolution commits
got dropped or rebased.

Do NOT re-open these for re-decision. If the verify step reveals a real
deviation, raise it with the user.

### D.1 — Verify F1 resolution (in-repo CHANGELOG fixed; out-of-repo flagged)

- [ ] `grep -n "STRICT" CHANGELOG.md | head -5` — confirm the line in
      `[Unreleased]` reads "STRICT drops provider / model unconditionally and
      projects provider_metadata through a curated subset (only status_code
      and retry_after_seconds — actionable HTTP client hints, not provider
      attribution)" or similar wording.
- [ ] Confirm the PR description will carry the out-of-repo carryover note
      for `pipelex-api/wip/error-handling/pipelex-changes.md:137`.

### D.2 — Verify F2 resolution (model_copy validator-skip: leave as-is)

- [ ] `grep -n "model_copy" pipelex/cogt/exceptions.py
      pipelex/base_exceptions.py` — confirm both still use
      `model_copy(update={...})` without a hypothetical `validate=True` kwarg
      (which doesn't exist in Pydantic 2.13.4 anyway).
- [ ] Confirm the followups doc's Decisions section records the choice.

### D.3 — Verify F3 resolution (STRICT 5xx leak — documented)

- [ ] Read `pipelex/base_exceptions.py:71-130` (`DisclosureMode.STRICT` docstring).
      Confirm a paragraph names the curated `provider_metadata` subset's
      cause-chain inheritance and the deliberate-leak rationale.

### D.4 — Verify F4 resolution (STRICT from_dict failure — documented + pinned)

- [ ] Read the same docstring. Confirm a paragraph names that STRICT
      payloads with `provider_metadata` are NOT round-trippable via
      `from_dict` (`pydantic.ValidationError`).
- [ ] Confirm
      `test_strict_payload_with_provider_metadata_fails_from_dict_rehydration`
      exists in
      `tests/unit/pipelex/test_error_report_disclosure_mode.py` and uses
      `pytest.raises(ValidationError)`.

### D.5 — Verify F5 resolution (helper extended to load_concepts_only* — documented)

- [ ] Read `pipelex/pipeline/validate_bundle.py:36-49` (helper docstring).
      Confirm the docstring names all four call sites and the
      dead-but-harmless extra handlers.
- [ ] Confirm both `load_concepts_only` (line 227) and
      `load_concepts_only_from_directory` (line 285) wrap their body in
      `with _translate_to_validate_bundle_error():`.

### D.6 — Verify F6 resolution (_logger ClassVar typing — YAGNI)

- [ ] Read `pipelex/temporal/log_temporal.py:49` — confirm
      `_logger: ClassVar[Any]` is unchanged.
- [ ] No action; per F6 decision.

### ⛔ CHECKPOINT D — STOP, verify, record

- [ ] No code changes expected. Append a dated entry to the Session log
      noting that F1-F6 resolutions still hold (or, if any deviation was
      found, what was raised).

---

## Out of scope (recorded, not planned here)

- The 6 sweep-low-confidence candidates the xhigh pass surfaced but did NOT
  promote (S4-S8 except S1/S2/S3 which are in Phase A/B above):
  - **S4** — `test_invalid_report_with_empty_message_falls_back_to_exc_chain`
    substring-match brittleness. Cosmetic; revisit only if temporalio's
    `ApplicationError.__str__` format changes.
  - **S5** — `_redact_provider_metadata_for_strict` `status_code=0` contract
    violation. Speculative; no producer.
  - **S6** — `recover_error_report` future schema migration widening
    `message` type. Speculative.
  - **S7** — `importlib.import_module` patch in
    `test_error_pages_generator.py`. The patch target is correct (module-
    scoped via dotted path); the original sweep concern about "global
    collision" was wrong. No action.
  - **S8** — `test_wf_pipe_router_request_id_logging.py` single `side_effect`
    instance vs retries. Masked by `maximum_attempts=1` today; if Temporal
    retries are ever enabled in tests, revisit.
- The latent / hypothetical Angle-D findings flagged but not promoted (status
  code=0, mutable defaults, ConfigDict edge cases, etc.). Speculative; no
  trigger.

---

## Decisions

Record each decision here as it is taken, with date and rationale.

- **2026-05-24, A.1**: Plan A confirmed — moved returns inside the `with` block on
  the two outliers. Result-construction errors now translate to
  `ValidateBundleError` uniformly across all 4 entry points.
- **2026-05-24, A.2**: Teardown API already exists (`library_manager.teardown(library_id)`
  + `teardown_current_library()`); no new context manager needed. In-scope here.
  Pattern: `try/finally` with `success` flag (project policy forbids generic
  `except Exception`), only tear down on failure path — matches the
  "error-path-only cleanup" precedent at `pipeline_run_setup.py:345-360`.
- **2026-05-24, B.1**: Option B.1-a — refactored `to_dict` STRICT branches to share
  `_STRICT_KEPT_FIELDS` as single allowlist. Caller-facing overlays
  `message` + `user_action` on the shared base. Dropped unused
  `_STRICT_PROVIDER_FIELDS` / `_STRICT_PASSTHROUGH_DROPPED_FIELDS` constants.
  Parity test added.
- **2026-05-24, B.2**: Option B.2-a — added `category: Literal["pipe", "concept"]`
  parameter to `_translate_to_validate_bundle_error`. The two `validate_bundle*`
  call sites pass `"pipe"`, the two `load_concepts_only*` pass `"concept"`. Only
  the `except ValidationError` arm's framing changes per category; the
  structured payload (`pipe_validation_errors`) is unchanged because
  `categorize_pipe_validation_error` already detects PIPE/CONCEPT model-scope
  per error.
- **2026-05-24, C.1**: Option C.1-b — pinned wrapper-wins semantics with a test
  at `tests/unit/pipelex/cogt/test_cogt_provider_metadata_wrapper_wins.py`.
  Added comments at both OR-suppression call sites
  (`pipelex/cogt/exceptions.py` and `pipelex/base_exceptions.py`) pointing at
  the test.
- **2026-05-24, C.2**: Trivial fix — added `str.strip()` guard at both sites
  (`recover_error_report` line 125 + `_message_from_exc`). Extended existing
  parametrize to cover whitespace cases.
- **2026-05-24, C.3**: Added one-line test asserting
  `not issubclass(PipeValidationError, pydantic.ValidationError)`. Added
  comment in the helper above `except PipeValidationError` clause pointing at
  the test.
- **2026-05-24, C.4**: C.4-a (no action). The inheritance hazard for external
  `ValidateBundleError` subclasses is documented in the `DisclosureMode.STRICT`
  docstring ("STRICT is a classification-projection, not a path-leak shield");
  in-repo subclass count is 0 (only an ephemeral test class).
- **2026-05-24, C.5**: C.5-a (no action). Same rationale as F6: temporalio's
  in-place mutation behavior makes the captured-at-class-definition reference
  safe today.
- **2026-05-24, D.1-D.6**: All resolutions still hold — verified
  `CHANGELOG.md` STRICT line, `model_copy` no `validate=True` kwarg, STRICT
  docstring covers 5xx leak + from_dict failure, helper docstring names all 4
  call sites, `_logger: ClassVar[Any]` unchanged.

## Session log

Append one dated entry per session / checkpoint. Each entry must leave the
next session enough to cold-start: what landed, decisions taken, current
code state, what is broken or deferred, and the exact next action.

- **2026-05-24**: Worked through all 15 findings in one session.

  **Phase A** — both committed (`1fccafd2`, `366a8aad`).
  - A.1 moved returns inside the `with` block on `validate_bundles_from_directory`
    and `load_concepts_only_from_directory` (the two outliers). Added
    `tests/integration/pipelex/pipeline/test_validate_bundle_return_placement.py`
    with one test per entry point — teeth-checked one by reverting (failed
    as expected, then restored).
  - A.2 wrapped each entry point in `try/finally` with a `success` flag that
    teardowns `library_manager` + `teardown_current_library()` only on the
    failure path. Added imports for `teardown_current_library`. Added
    `tests/integration/pipelex/pipeline/test_validate_bundle_library_lifecycle.py`
    spying on `library_manager.teardown` for each entry point — teeth-checked
    by reverting one entry point.

  **Phase B** — both committed (`52325498`, `0554303b`).
  - B.1-a unified the two STRICT branches in `ErrorReport.to_dict` to share
    `_STRICT_KEPT_FIELDS` as a single allowlist; caller-facing branch overlays
    `message` + `user_action`. Dropped `_STRICT_PROVIDER_FIELDS` and
    `_STRICT_PASSTHROUGH_DROPPED_FIELDS`. Updated the constant's docstring.
    Added `test_strict_branch_kept_field_parity`.
  - B.2-a added `category: Literal["pipe", "concept"]` to the helper signature.
    The four call sites now pass their category explicitly. Only the
    `except ValidationError` arm's message framing changes (Could not load
    blueprints vs Could not load concepts). Structured payload unchanged.
    Added `test_validate_bundle_category_framing.py`.

  **Phase C** — three committed (`d8ad53ff`, `7cfb6a20`, `b4d454fc`), two
  skipped per recommendation.
  - C.1-b added a test pinning wrapper-wins `provider_metadata` semantics
    (`tests/unit/pipelex/cogt/test_cogt_provider_metadata_wrapper_wins.py`) and
    a one-paragraph comment at both OR-suppression call sites
    (`pipelex/cogt/exceptions.py` and `pipelex/base_exceptions.py`).
  - C.2 added `str.strip()` guards at both
    `_message_from_exc` and `recover_error_report` line 125. Extended the
    existing parametrize to cover empty/space/tab/newline/mixed-whitespace.
    Teeth-checked.
  - C.3 added `test_pipe_validation_error_is_not_a_pydantic_validation_error_subclass`
    plus a one-line comment in the helper above the `except PipeValidationError`
    clause.
  - C.4 skipped per recommendation (C.4-a — no action; documented in
    `DisclosureMode.STRICT` docstring).
  - C.5 skipped per recommendation (C.5-a — no action; same rationale as F6).

  **Phase D** — all six F1-F6 resolutions verified intact. No code changes.

  **State at end of session**: baseline green (`make agent-check` clean,
  `make agent-test` passes). Branch is `feature/post-pr933-followups`, 8 new
  commits on top of `e73cb5a9`. PR #933 not yet landed at time of writing —
  do NOT rebase onto `dev` until it does.
