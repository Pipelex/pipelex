# `/code-review` findings — `feature/post-pr933-followups`

Output of a 5-angle `/code-review` pass over the branch
`feature/post-pr933-followups` (stacked on `feature/API-readiness-2`, 12 commits
of `2409f78d..464d48c0`). The branch landed Phases A/B/C/D of
[`./post-pr933-review-followups.md`](./post-pr933-review-followups.md).

None of these are blocking, but each warrants a user decision before the branch
opens as a PR. The list is ranked most-severe first.

## How to start (cold start)

1. Read [`./post-pr933-review-followups.md`](./post-pr933-review-followups.md)
   first — it explains the four phases (test backfill, refactors, cleanup,
   STRICT-disclosure feature) the review pass targeted. The Session log at the
   bottom shows the 12 commits.
2. Read this file's findings in order; each names the exact `file:line`, the
   trigger, and the suggested action. Most need a yes/no from the user before
   acting.
3. Branch state: `feature/post-pr933-followups` stacks on `feature/API-readiness-2`.
   Wait for PR #933 to merge before opening a PR for this branch; rebase onto
   `dev` at that point.
4. Make any agreed changes as fresh commits on top — do NOT rewrite history of
   the 12 phase commits (they are coherent commit-by-commit).

## Ground rules

- `make agent-check` after every code change. `make agent-test` before pushing.
- Same project rules as the parent plan: no backward-compat shims, one
  `TestClass` per module, `pytest-mock` (`MockerFixture`) not `unittest.mock`,
  StrEnum never `.value`. See `.claude/rules/python-standards.md` and
  `.claude/rules/pytest-standards.md`.

---

## Finding 1 — CHANGELOG.md is stale on STRICT behavior

**File**: `CHANGELOG.md:9` (Unreleased section)

**What**: The Unreleased entry under `### Added` for
`ErrorReport.to_problem_document()` / `DisclosureMode` still states:

> `STRICT` always drops `provider` / `model` / `provider_metadata`

This is **no longer true** as of the last commit on this branch
(`75dfa941 fix(errors): preserve curated provider_metadata subset under STRICT
disclosure`). STRICT now drops only `provider` / `model` and projects
`provider_metadata` through a curated subset containing `status_code` and
`retry_after_seconds`.

**Why it matters**: downstream consumers (`pipelex-api`, `pipelex-relay`,
third-party SDKs) reading the CHANGELOG to learn the STRICT wire-format
contract will decide they never see `provider_metadata` on STRICT payloads,
then break or silently mis-render when the curated subset arrives.

**Suggested action** (low-risk, just doc):

Update the CHANGELOG line to read something like:

> `STRICT` drops `provider` / `model` and projects `provider_metadata` through
> a curated subset (only `status_code` and `retry_after_seconds` — actionable
> HTTP client hints, not provider attribution).

**Out-of-repo cousin**: the same stale claim appears in
`pipelex-api/wip/error-handling/pipelex-changes.md:137`. That repo is separate
— fix it in a follow-up there, but flag it in this PR's description so the
pipelex-api maintainers can pick it up.

**Decision needed**: just `do it` / `not yet`. No design ambiguity.

---

## Finding 2 — `error_category` type drift via `model_copy` skipping validation

**File**: `pipelex/cogt/exceptions.py:96-104`

**What**: The Phase B.3 refactor switched `CogtError.to_error_report` from
constructor-build to `super().to_error_report()` + `model_copy(update={...})`.
`model_copy` does **not** re-run Pydantic field validators by default. As a
result:

- **Fresh path**: `CogtError(error_category=InferenceErrorCategory.CAPACITY).to_error_report()`
  → `report.error_category` is an `InferenceErrorCategory` enum instance.
- **Round-trip path**: `ErrorReport.model_validate(report.model_dump())`
  → `report.error_category` is plain `str` (`"capacity"`).

The OLD constructor path always coerced through `ErrorReport`'s field validator
(`error_category: str | None`), so both paths produced `str` and reports were
type-identical.

**Why it matters**: `InferenceErrorCategory` is a `StrEnum`, so `isinstance(x,
str)`, equality, and JSON serialization all behave the same either way. The
only observable difference is `type(x) is str` (False fresh, True
round-tripped) — which is an anti-pattern, and the codebase doesn't appear to
have any such check today. So **no current consequence** — but it is a latent
asymmetry the OLD code did not have, and any future contributor doing strict
type-identity checks (or comparing reports across the serialization boundary
for equality) will be surprised.

**Suggested action** (one-line fix):

Pass `validate=True` to `model_copy`:

```python
return base_report.model_copy(
    update={...},
    validate=True,  # restore the constructor-path coercion symmetry
)
```

Same edit applies to `pipelex/base_exceptions.py:_enrich_error_report_from_cause`
(`report.model_copy(update={...})`) for the same reason. The Pydantic 2.x
`validate=True` kwarg re-runs field validators on the updated values.

**Decision needed**: do you want the fresh/round-tripped symmetry restored
(safe, defensive), or leave it (current behavior, faster by a few microseconds,
StrEnum-equality makes it invisible to all current callers)?

---

## Finding 3 — STRICT redacted branch leaks `status_code` from cause

**File**: `pipelex/base_exceptions.py:236-243`

**What**: When a wrapper `PipelexError` is raised `from` a `CogtError` that
carries `provider_metadata`, the cause-chain enrichment copies
`provider_metadata` onto the wrapper's `ErrorReport`. The Phase D.1 STRICT
projection then keeps the curated subset (`status_code` /
`retry_after_seconds`) on the **redacted** branch — even though the wrapper's
`error_type` (e.g. `PipelexUnexpectedError`) doesn't otherwise disclose any
provider relationship.

Concrete scenario:

```python
raise PipelexUnexpectedError("internal invariant violated") from CogtError(
    "openai returned 500",
    provider_metadata=ProviderErrorMetadata(provider=OPENAI, status_code=500, ...),
)
```

Wire payload (STRICT):

```json
{
  "error_type": "PipelexUnexpectedError",
  "title": "Unexpected internal error",
  "type_uri": ".../pipelex-unexpected-error/",
  "error_domain": "runtime",
  "detail": "An internal error occurred.",
  "provider_metadata": {"status_code": 500}
}
```

The consumer learns "some upstream returned HTTP 500" from an `error_type`
that advertises no provider relationship.

**Why it matters**: the Phase D.1 design discussion was framed around the
canonical 429-with-`Retry-After` case where the consumer *needs* the hint. On
the redacted branch (where the message is replaced and `user_action` is
dropped), surfacing a 5xx status from a wrapped provider call may surprise
ops/security reviewers. By the design call's rationale, this is acceptable
(`status_code` is not provider attribution); by the strictest reading of "an
external surface should learn nothing about internal failure topology", it
arguably is.

**Suggested action** (three options):

- **3a (leave as-is, document)**: this is the documented Phase D.1 Option 1
  behavior. Add a paragraph to the `DisclosureMode.STRICT` docstring at
  `pipelex/base_exceptions.py:79-106` calling out the cause-inheritance behavior
  so future readers don't think it's an oversight.
- **3b (narrow to 429 only)**: only emit `status_code` / `retry_after_seconds`
  on the STRICT redacted branch when the underlying `error_category` is
  retryable (or when `status_code == 429`). Preserves the actionable-hint use
  case while keeping internal 5xx topology hidden.
- **3c (redacted branch drops `provider_metadata` entirely; caller-facing keeps
  curated subset)**: matches the original "STRICT redacts non-caller-facing"
  framing more tightly — caller-facing errors get the HTTP hint, redacted
  errors get nothing.

**Decision needed**: which of 3a/3b/3c. Default to 3a if no concern.

---

## Finding 4 — STRICT no longer round-trips through `ErrorReport.from_dict`

**File**: `pipelex/base_exceptions.py:243` (the curated `provider_metadata`
return), `pipelex/base_exceptions.py:306` (`from_dict`)

**What**: The curated `provider_metadata` dict on a STRICT payload only
contains `status_code` and `retry_after_seconds`. `ProviderErrorMetadata`
requires `provider` and `sdk_exception_type`, so `ErrorReport.from_dict(strict_payload)`
now raises `pydantic.ValidationError`.

The OLD behavior (pre-Phase-D.1) was that STRICT dropped `provider_metadata`
entirely, so `from_dict` still succeeded — producing an `ErrorReport` with
`provider_metadata=None` and a redacted message. The Phase D.1 commit
explicitly rewrote `test_strict_does_not_round_trip` to read fields off the
dict directly rather than rehydrate, masking the regression in the test
suite.

**Why it matters**: no in-repo consumer does `from_dict(strict_payload)` (the
pipelex-api consumes the dict directly via `to_problem_document`), so this is
not a regression for known callers. But it is a sharper failure mode than the
existing "STRICT is lossy" framing suggested. Out-of-repo consumers that
previously could leniently rehydrate a STRICT payload now get a hard pydantic
ValidationError.

**Suggested action** (two options):

- **4a (document and accept)**: add a `!!! warning` block to the
  `DisclosureMode.STRICT` docstring explicitly stating "STRICT payloads cannot
  be passed to `ErrorReport.from_dict()` — consume the dict directly." Pin the
  behavior with a unit test that asserts `ErrorReport.from_dict(strict_payload)`
  raises `ValidationError`. Worth mentioning in the PR description so
  pipelex-api / pipelex-relay maintainers can verify they don't have a lenient
  rehydration codepath.
- **4b (make `provider` / `sdk_exception_type` Optional on
  `ProviderErrorMetadata`)**: restores lenient round-trip. Cost: every
  downstream test that asserts `metadata.provider == "google"` keeps working
  (workers always populate), but pyright now sees the fields as
  `ProviderName | None` and may flag a few additional `assert metadata.provider
  is not None` sites. Searched: `grep -rn 'provider_metadata\.provider\|provider_metadata\.sdk_exception_type' --include='*.py' pipelex/` returned zero production-code matches — all hits are in test files that work on freshly-raised errors. Type impact is bounded.

**Decision needed**: 4a (sharper failure, document it) or 4b (lenient
round-trip, semi-Optional fields). Prefer 4a unless an external consumer is
known to do round-trip.

---

## Finding 5 — `_translate_to_validate_bundle_error` doesn't cover `load_concepts_only*`

**File**: `pipelex/pipeline/validate_bundle.py` — helper at line ~34, used by
`validate_bundle` (line ~84) and `validate_bundles_from_directory` (line ~143),
but NOT by `load_concepts_only` (line ~200) or `load_concepts_only_from_directory`
(line ~290).

**What**: The Phase C.2 commit extracted the six-handler cascade into
`_translate_to_validate_bundle_error()` and updated the two `validate_bundle*`
call sites. The two `load_concepts_only*` functions kept their separate (smaller,
2-handler — `PipelexInterpreterError` + `ValidationError`) inline cascades.

**Why it matters**: this is a partial refactor. A future contributor adding a
new error type to the shared helper (say, wrapping a `LibraryManagerError`
translation) gets it picked up for `validate_bundle*` but silently misses it
for `load_concepts_only*`. The helper's docstring calls itself "single source
of truth" — which is misleading.

**Suggested action** (three options):

- **5a (extract a second helper)**: add a sibling
  `_translate_to_validate_bundle_error_concepts_only()` covering the smaller
  2-handler cascade, used by both `load_concepts_only*` functions.
- **5b (one helper, broader)**: extend the existing helper to be safe for the
  concepts-only path (the four handlers it carries beyond
  `PipelexInterpreterError` + `ValidationError` never fire there anyway). Use
  the same context manager in all four call sites. Lowest duplication.
- **5c (do nothing, just rename helper)**: rename the helper to
  `_translate_full_bundle_errors_to_validate_bundle_error` to clarify it
  covers only the full-validation paths, and add a one-line comment on each
  `load_concepts_only*` cascade pointing at it.

**Decision needed**: 5a / 5b / 5c. Probably 5b is cleanest (one source of
truth, smaller diff), 5c is the minimal change.

---

## Finding 6 — `_RequestIdLog._logger` is type-erased; subclass forgetting `_logger` crashes at runtime

**File**: `pipelex/temporal/log_temporal.py:47` (the `ClassVar[Any]`
declaration on the base)

**What**: Phase B.1 hoisted the severity methods onto `_RequestIdLog` and
declared `_logger: ClassVar[Any]` with no default. Each subclass
(`WorkflowLog`, `ActivityLog`) sets `_logger = workflow.logger` / `activity.logger`.

If a future contributor adds a third subclass (or refactors and accidentally
drops the `_logger` assignment), pyright cannot catch it because the type is
`Any`. The class instantiates fine, then crashes with
`AttributeError: NewLog has no attribute '_logger'` on the first
`.info()` / `.debug()` / etc. call.

**Why it matters**: low likelihood today (only two subclasses exist, both in
the same file), but the typing is doing zero work. If you mean for the base to
be "extension-safe", make the typing reflect it.

**Suggested action** (two options):

- **6a (tighten the type)**: change to `ClassVar[logging.LoggerAdapter]` and
  remove `Any`. Forces every subclass to declare a `LoggerAdapter` explicitly;
  pyright catches a missing assignment.
- **6b (enforce via `__init_subclass__`)**: add an `__init_subclass__` on
  `_RequestIdLog` that raises `TypeError` if the subclass doesn't define
  `_logger` in its own `__dict__`. Catches the gap at class-definition time
  rather than first severity call.
- **6c (do nothing)**: only two subclasses ever, both in the same file —
  YAGNI.

**Decision needed**: 6a / 6b / 6c. Probably 6c unless `_RequestIdLog` is
expected to gain more subclasses.

---

## Decisions

Record each decision here as it is taken, with date and rationale.

- **2026-05-24 — Finding 1: Update CHANGELOG now.** Replaced the stale `STRICT always drops provider / model / provider_metadata` claim in `CHANGELOG.md` `[Unreleased]` with the curated-subset wording. Pure doc fix; the stale claim would have misled downstream consumers (pipelex-api, pipelex-relay, third-party SDKs) reading the CHANGELOG to learn the STRICT wire-format contract. The stale claim in `pipelex-api/wip/error-handling/pipelex-changes.md:137` (out of repo) is flagged for the pipelex-api maintainers in the PR description but not fixed here.
- **2026-05-24 — Finding 2: Leave as-is.** The finding's suggested fix (`model_copy(update=..., validate=True)`) does not exist in Pydantic 2.13.4 (signature is `(self, *, update, deep)`). The real workaround — `cls.model_validate({**self.model_dump(), **update})` — is heavier (full re-validation, deep submodel rebuild) and inconsistent with the rest of the codebase, which uses `model_copy(update=...)` extensively without re-validation. The asymmetry the finding flagged (`error_category` is enum on fresh path, plain `str` on round-trip) is invisible to every current caller because `InferenceErrorCategory` is a `StrEnum` — `isinstance`, `==`, and JSON serialization all behave identically. Only `type(x) is str` differs, and the codebase has no such strict-identity checks. Revisit if a future contributor introduces one.
- **2026-05-24 — Finding 3: 3a — Document only.** Added a paragraph to the `DisclosureMode.STRICT` docstring explaining that the curated `provider_metadata` subset IS inherited up the `__cause__` chain via `_enrich_error_report_from_cause` and is preserved on both STRICT branches — including the redacted branch when a domain-less wrapper (e.g. `PipelexUnexpectedError`) is raised from a categorized `CogtError`. By the same reasoning as the existing path-leak-shield disclaimer, this is deliberate: `status_code` / `retry_after_seconds` are HTTP client hints, not provider attribution, and STRICT is a classification-projection, not a topology-hiding shield. 3b (narrow to retryable / 429) and 3c (redacted branch drops `provider_metadata` entirely) were rejected as inconsistent with the Phase D.1 design call.
- **2026-05-24 — Finding 4: 4a — Document + pin with test.** Added a paragraph to the `DisclosureMode.STRICT` docstring stating that STRICT payloads carrying `provider_metadata` cannot be rehydrated via `ErrorReport.from_dict` (the curated subset lacks the required `provider` / `sdk_exception_type` fields on `ProviderErrorMetadata`, so rehydration raises `pydantic.ValidationError`). Pinned the behavior with a new test `test_strict_payload_with_provider_metadata_fails_from_dict_rehydration` in `tests/unit/pipelex/test_error_report_disclosure_mode.py`. STRICT was already documented as a lossy projection; this is a sharper failure mode external consumers should know about. The pipelex-api / pipelex-relay maintainers should verify they don't have a lenient rehydration codepath — flagged for the PR description. 4b (make `provider` / `sdk_exception_type` Optional on `ProviderErrorMetadata`) was rejected: the spec-correct projection is to consume the dict directly, and weakening the model would propagate Optionality into every test that asserts on those fields.
- **2026-05-24 — Finding 5: 5b — Extend existing helper, use in all 4 call sites.** Refactored `pipelex/pipeline/validate_bundle.py` so `load_concepts_only` and `load_concepts_only_from_directory` now wrap their bodies in `with _translate_to_validate_bundle_error():` — single source of truth across all four entry points. The four pipe-loading / dry-run handlers (`PipeFactoryError`, `PipeValidationError`, `PipeRunError`, `DryRunError`) are dead code in the concepts-only paths but harmless, since those functions never instantiate pipes or run dry runs. Updated the helper's docstring to note this. Removed the now-redundant inline 2-handler cascades in both `load_concepts_only*` functions. 5a (separate helper) rejected as duplication; 5c (rename + comment) rejected as not actually fixing the partial refactor.
- **2026-05-24 — Finding 6: 6c — Do nothing.** YAGNI. Only two subclasses of `_RequestIdLog` exist today (`WorkflowLog`, `ActivityLog`), both in the same module. Tightening the `ClassVar[Any]` type or enforcing via `__init_subclass__` adds machinery for a hypothetical failure mode. If a third subclass is ever added, the AttributeError on first severity call would surface immediately in any test exercising it. Revisit then.

## Session log

### 2026-05-24 — Code-review follow-ups landed

- **All six findings resolved** as single commits per fix-bearing finding (F1 / F3 / F4 / F5). F2 and F6 are no-op "leave as-is" decisions, recorded above without code changes.
  - **F1 (CHANGELOG)**: `CHANGELOG.md` `[Unreleased]` line on STRICT behavior rewritten to reflect the curated-subset projection.
  - **F3 + F4 (docstring + test)**: `DisclosureMode.STRICT` docstring at `pipelex/base_exceptions.py:79-130` extended with two paragraphs — (a) the curated `provider_metadata` subset is inherited up the `__cause__` chain and preserved on both STRICT branches, including when a domain-less wrapper sits between caller and provider; (b) STRICT payloads carrying `provider_metadata` cannot be rehydrated through `from_dict`. Added a new test `test_strict_payload_with_provider_metadata_fails_from_dict_rehydration` in `tests/unit/pipelex/test_error_report_disclosure_mode.py` pinning the rehydration failure.
  - **F5 (validate_bundle refactor)**: `pipelex/pipeline/validate_bundle.py` — `load_concepts_only` (line ~218) and `load_concepts_only_from_directory` (line ~278) now share the `_translate_to_validate_bundle_error` context manager with `validate_bundle*`. Helper docstring updated to reflect the new 4-call-site coverage. Inline 2-handler cascades removed from both concepts-only functions.
- **Status**: `make agent-check` clean (0 errors, 0 warnings, 0 informations on pyright; mypy clean on 1905 source files). Targeted tests pass: 50 tests in `test_error_report_disclosure_mode.py` / `test_error_report_problem_document.py` / `test_load_concepts_only.py`; 55 tests in CLI + validation-related suites; 865 tests across `tests/unit/pipelex/exceptions/` and `tests/unit/pipelex/cogt/`.
- **Two doc carryovers for the PR description**:
  - The stale STRICT claim in `pipelex-api/wip/error-handling/pipelex-changes.md:137` mirrors the one fixed in this branch's CHANGELOG. That repo is separate — flag for pipelex-api maintainers.
  - STRICT payloads with `provider_metadata` no longer rehydrate via `from_dict`. No in-repo consumer does round-trip on STRICT payloads (pipelex-api consumes the dict directly via `to_problem_document`), but the F4 pinning test now makes the failure mode explicit. Worth a heads-up so downstream maintainers can verify they don't have a lenient rehydration codepath.
- **Next action**: this file is complete. The branch `feature/post-pr933-followups` is ready for PR once `feature/API-readiness-2` (PR #933) lands and the branch can rebase onto `dev`. Open the PR with both doc carryovers in the description.
