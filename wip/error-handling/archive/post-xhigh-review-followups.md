# Plan — verify and fix the 7 findings from the xhigh `/code-review`

A second xhigh `/code-review` pass (recall mode) over the 8 commits added in the
previous session surfaced 7 findings (3 HIGH, 2 MEDIUM, 2 LOW). This plan is
the work-tracker for verifying each finding against the current code and
landing the fix. The plan is laid out so a fresh session can cold-start from
it.

## Branch context (cold start)

- **Branch**: `feature/post-pr933-followups`, stacked on `feature/API-readiness-2`.
  PR #933 still open against `dev` at time of writing — do NOT rebase onto
  `dev` until PR #933 lands.
- **Prior plans on this branch**:
  - [`./post-pr933-review-followups.md`](./post-pr933-review-followups.md) — the
    original 4-phase (A/B/C/D) plan that drove the first 12 commits.
  - [`./post-pr933-followups-code-review.md`](./post-pr933-followups-code-review.md) —
    the F1-F6 plan that drove 4 commits.
  - [`./post-pr933-xhigh-followups.md`](../post-pr933-xhigh-followups.md) — the
    15-finding xhigh plan that drove the 8 commits this xhigh pass reviewed.
- **State at cold start** (check on entry):
  - `git log --oneline feature/API-readiness-2..HEAD` should show 22 commits.
    The 8 most recent (top of the log) are this xhigh pass's targets:
    - `ab07bd2c` docs(plan)
    - `b4d454fc` test(validate): pin PipeValidationError sibling
    - `7cfb6a20` fix(temporal): whitespace-only message
    - `d8ad53ff` test(errors): pin wrapper-wins provider_metadata
    - `0554303b` fix(validate): concept/pipe ValidationError framing
    - `52325498` refactor(errors): unify STRICT projection
    - `366a8aad` fix(validate): teardown LibraryManager on failure
    - `1fccafd2` fix(validate): translate result-construction errors
  - `git status` should be clean (or only this plan file unstaged).
- **Baseline**: `make agent-check` and `make agent-test` are both green at the
  start of this session — confirm before touching anything.

## How to start (cold start)

1. **Read this whole file** — every finding names the exact `file:line`, the
   verify step, the decision needed, and the fix work.
2. **Confirm branch state**: `git status`, `git log --oneline feature/API-readiness-2..HEAD | head -10`.
3. **Confirm baseline is green**: `make agent-check` + `make agent-test` BEFORE
   touching anything. If either fails on entry, stop and investigate.
4. **Findings are independent** — pick by phase. Phase A is the
   teardown-leak triage (3 leaks tightly related); Phase B is the helper-shape
   issues; Phase C is the test/contract-pin issues.
5. **Make each finding a fresh commit on top** of the existing 22-commit
   history. Do NOT rewrite history.

## Ground rules

- `make agent-check` after every code change. `make agent-test` before each
  phase checkpoint.
- No backward-compat shims (project policy).
- One `TestClass` per test module; use `pytest-mock` (`MockerFixture`), not
  `unittest.mock`. See `.claude/rules/pytest-standards.md`.
- StrEnum rule: never `enum_var.value`, just `{enum_var}`. See
  `.claude/rules/python-standards.md`.
- Project policy forbids generic `except Exception:` (see
  `.claude/rules/python-standards.md`). Use `try/finally` with a `success`
  flag (precedent: `pipeline_run_setup.py:345-360` and the A.2 commit
  `366a8aad`).
- `case _:` on exhaustive matches is forbidden by python-standards. Use
  `case _ as unreachable: assert_never(unreachable)` from `typing` only when
  the runtime contract is genuinely unenforceable (Literal at a call site).

---

## Phase A — HIGH severity: pre-`try` library leaks (3 findings, one fix shape)

All three are the same underlying defect: in each of the four bundle-loading
entry points, code runs between `library_manager.open_library()` and the new
`try:` block that holds the teardown `finally`. Any exception in that window
— including `asyncio.CancelledError` at the `await asyncio.sleep(0)` yield —
leaks the just-opened library. The new lifecycle tests don't exercise
cancellation or pre-`try` raises.

### A.1 — CancelledError leak on `await asyncio.sleep(0)`

**File**: `pipelex/pipeline/validate_bundle.py:127-137` (`validate_bundle`).

**What**: After `open_library()` at line 127 and `set_current_library()` at
line 128, control reaches `await asyncio.sleep(0)` at line 135 BEFORE entering
the `try:` at line 137. `asyncio.CancelledError` (a `BaseException`) raised at
that yield propagates without entering the `try`, so the new `finally` never
runs.

**Why it matters**: the lifecycle-fix's stated use case is an IDE/server that
cancels in-flight validation on every keystroke. That's exactly the trigger
for cancellation at an `await` point. The fix protects against everything
EXCEPT cancellation — silently the worst case for the stated use case.

**Verify**:

- [ ] `grep -n "await asyncio.sleep\|open_library\|^    try:\|^    finally:" pipelex/pipeline/validate_bundle.py | head -30`
      — confirm `await asyncio.sleep(0)` is between `open_library()` and
      `try:` in `validate_bundle`. Other entry points don't have `await
      asyncio.sleep(0)`, but they do have other pre-`try` work — see A.2.

### A.2 — Pre-`try` raises from `resolve_library_dirs` / `set_current_library`

**File**: `pipelex/pipeline/validate_bundle.py`
- `validate_bundle` lines 127-137 (`open_library` → `set_current_library` →
  `resolve_library_dirs` → variable init → `await asyncio.sleep(0)` → `try:`)
- `load_concepts_only` lines 248-258 (same pattern, no `await`)
- `validate_bundles_from_directory` lines 184-193 (open → set_current → try:)
- `load_concepts_only_from_directory` lines 316-321 (open → set_current → try:)

**What**: `resolve_library_dirs(library_dirs)` is called between
`open_library()` and the `try:` in `validate_bundle` and `load_concepts_only`.
It can raise `TypeError` (e.g. `Path(None)` in `hub.py:511` when a caller
passes a malformed `library_dirs` element). `set_current_library` is also
outside the try in all four entry points and could in principle raise.

**Why it matters**: the contract the lifecycle test (commit `366a8aad`) pins
is "teardown fires on the failure path". Any of these pre-`try` raises
silently breaks that contract.

**Verify**:

- [ ] Read `pipelex/pipeline/validate_bundle.py:120-145` and confirm
      `resolve_library_dirs(library_dirs)` is at line 131 (in `validate_bundle`)
      and line 254 (in `load_concepts_only`), both BEFORE the `try`.
- [ ] Read `pipelex/hub.py:491-525` (`resolve_library_dirs`) and confirm
      `Path(...)` is called on user-supplied dir elements (the `TypeError`
      path).
- [ ] Read `pipelex/hub.py:486-488` (`teardown_current_library`) — it just
      resets the contextvar to None.

### A.3 — One unified fix for A.1 + A.2

The same restructuring closes all three leak windows. There are two clean
options.

**Decision needed** (two options):

- **A-fix-1** (recommended — move-into-try): move every line between
  `open_library()` and the existing `try:` INTO the try block, including
  `set_current_library`, `resolve_library_dirs`, the variable inits, and the
  `await asyncio.sleep(0)`. Apply uniformly to all four entry points. Net
  effect: any exception in that window now triggers the existing teardown
  path.
- **A-fix-2** (extract context manager): replace the open/set/teardown
  scaffolding with a `library_session(...)` `@contextmanager` that yields
  `(library_id, library)` and tears down on `__exit__` only when the inner
  body raised. Costs an extra abstraction; gains clarity. Recommend A-fix-1
  unless the duplication across the four entry points triggers the same fix
  somewhere else.

Recommend **A-fix-1** — minimal, no new abstraction, surgical to the four call
sites.

**Fix** (A-fix-1):

- [ ] For each of the four entry points, move every statement between
      `library_manager.open_library()` and `try:` INTO the `try:` block. The
      `success = False` flag stays just before the `try`. Order:
      ```python
      library_id, library = library_manager.open_library()
      success = False
      try:
          set_current_library(library_id=library_id)
          effective_dirs, source_label = resolve_library_dirs(library_dirs)
          # ... other variable init ...
          await asyncio.sleep(0)  # only in validate_bundle
          with _translate_to_validate_bundle_error(category="..."):
              # ... body ...
              result = ...Result(...)
          success = True
          return result
      finally:
          if not success:
              library_manager.teardown(library_id=library_id)
              teardown_current_library()
      ```
- [ ] Confirm the four entry points still pass `agent-check` (no unused
      imports, no shadowed locals).

**Test**:

- [ ] Add `tests/integration/pipelex/pipeline/test_validate_bundle_preflight_leak.py`
      (or extend the existing `test_validate_bundle_library_lifecycle.py` —
      pick whichever has the right scope). Cover:
  - Cancellation at `await asyncio.sleep(0)`: in `validate_bundle`, wrap the
    call in an `asyncio.Task`, cancel it just after creation, assert teardown
    fired. Use `mocker.spy` on `library_manager.teardown` AND on
    `library_manager.open_library` so the test can ALSO assert the
    teardown's `library_id` matches the opened id (see C.5).
  - `TypeError` from `resolve_library_dirs`: call `validate_bundle(library_dirs=[None])`
    or similar invalid input, assert teardown fired with the right id.
  - Same two scenarios for `load_concepts_only`.
- [ ] Teeth check: temporarily revert one entry point's move-into-try; the
      new test must fail.

**Commit**: `fix(validate): close pre-try leak window in bundle entry points`

### ⛔ CHECKPOINT A — STOP, verify, record

- [ ] `make agent-check` clean.
- [ ] `make agent-test` clean (full suite — these are async / lifecycle tests
      and may surface flakiness).
- [ ] Append a dated entry to the Session log below.

---

## Phase B — MEDIUM severity: helper shape gaps

### B.1 — `PipeValidationError` arm uses pipe framing on concept entry points

**File**: `pipelex/pipeline/validate_bundle.py:75-80`
(`_translate_to_validate_bundle_error`'s `except PipeValidationError` arm).

**What**: The B.2 fix from the previous xhigh round made the
`except ValidationError` arm category-aware (line 88-91: "Could not load
blueprints because of: ..." vs "Could not load concepts because of: ..."). But
the helper has FIVE other arms (`PipelexInterpreterError`, `PipeFactoryError`,
`PipeValidationError`, `PipeRunError`, `DryRunError`), and the
`PipeFactoryError` and `PipeValidationError` arms still produce pipe-specific
framing ("Pipe factory error: ...", "Pipe validation failed: ...") regardless
of category.

The helper's docstring asserts that those handlers are "dead code in the
concepts-only paths" because concept-only entry points "never instantiate
pipes or run dry runs." But that's an unverified claim — if a future change
to `load_concepts_only_from_blueprints` ever surfaces a `PipeValidationError`
or `PipeFactoryError` (e.g. through a shared validator on a concept's
`refines` chain), a concepts-only caller would see "Pipe validation failed
..." framing — exactly the B.2 mislabel the previous round was supposed to
fix.

**Verify**:

- [ ] Read `pipelex/pipeline/validate_bundle.py:54-92` — re-confirm only the
      `ValidationError` arm is category-aware after the B.2 commit.
- [ ] Grep for the dead-code claim:
      `grep -rn "raise PipeValidationError\|raise PipeFactoryError" pipelex/libraries/ pipelex/core/concepts/` —
      if any concept-loading path can raise these, the gap is real.

**Decision needed** (three options):

- **B.1-a** (recommended — make all framing arms category-aware): pass
  `category` to all framing arms. Use a `match category` at one place
  (extract a small `_format_message_with_category(category, kind, detail)`
  helper) so the four entry points see one place when adding a new framing.
- **B.1-b** (rely on the docstring): document the dead-code claim with a
  test that asserts the concept-loading paths never call into pipe-validation
  helpers. Cheaper; relies on the test never going stale.
- **B.1-c** (accept the gap): leave it. Pipe-framing on concept paths is a
  diagnostic-quality issue only if those exceptions ever fire.

Recommend **B.1-a** — closes the loop on B.2's intent and removes the
unverified docstring claim. Cost: small parametrize of the helper.

**Fix** (B.1-a):

- [ ] Either pass `category` to each framing string and switch on it inline,
      or factor out a small helper:
      ```python
      def _categorized_intro(category: Literal["pipe", "concept"], kind: str) -> str:
          subject = "Pipe" if category == "pipe" else "Concept"
          return f"{subject} {kind}"
      ```
      and use it in PipeFactoryError, PipeValidationError, and ValidationError
      arms.
- [ ] Update the helper docstring to drop the "dead code" claim — replaced by
      the categorized framing.

**Test**:

- [ ] Extend `tests/integration/pipelex/pipeline/test_validate_bundle_category_framing.py`
      with cases that trigger PipeFactoryError / PipeValidationError from a
      concepts-only entry point — use `mocker.patch.object` on the relevant
      LibraryManager method to raise the right exception. Assert the
      resulting message uses "Concept ..." framing, not "Pipe ...".
- [ ] Teeth check: revert one framing arm to hard-code "Pipe"; the test
      must fail.

**Commit**: `fix(validate): make all helper framing arms category-aware`

### B.2 — `match category:` has no `case _: assert_never(...)`

**File**: `pipelex/pipeline/validate_bundle.py:85-89` (the
`except ValidationError` arm in the helper).

**What**: `Literal["pipe", "concept"]` is not enforced at runtime. A typo at
a call site (e.g. `category="concepts"`) makes the match fall through, leaves
`msg` unbound, and the next line `raise ValidateBundleError(message=msg, ...)`
raises `UnboundLocalError` — bypassing the helper's translation contract.
Today the four call sites are correct, but the gap is real for a fifth caller
or a refactor.

**Why it matters**: the helper's whole purpose is to translate the bundle-loading
exception surface into a single `ValidateBundleError`. Letting `UnboundLocalError`
escape silently breaks that contract.

**Verify**:

- [ ] `grep -n "match category\|case \"" pipelex/pipeline/validate_bundle.py |
      head -10` — confirm no `case _:` arm.
- [ ] Re-read `.claude/rules/python-standards.md` enum section — confirm the
      project forbids `case _: ...` on exhaustive matches but allows
      `assert_never` for unenforced Literal at runtime.

**Decision needed**: the rule against `case _` is about enum-exhaustive
matches (where the linter catches missing arms). A `Literal[...]` parameter
is different — the runtime can receive any value. Add `assert_never` so the
runtime contract is loud.

**Fix**:

- [ ] Add a fallthrough arm:
      ```python
      from typing import assert_never  # at top of file
      ...
      match category:
          case "pipe":
              msg = f"Could not load blueprints because of: {validation_error_msg}"
          case "concept":
              msg = f"Could not load concepts because of: {validation_error_msg}"
          case _ as unreachable:
              assert_never(unreachable)
      ```

**Test**:

- [ ] Add `tests/unit/pipelex/pipeline/test_validate_bundle_helper.py` (the
      file from C.3 in the previous round — append a new test method):
      ```python
      def test_translate_helper_rejects_unknown_category_at_runtime(self) -> None:
          from pipelex.pipeline.validate_bundle import _translate_to_validate_bundle_error
          with pytest.raises(AssertionError):  # assert_never raises AssertionError
              with _translate_to_validate_bundle_error(category="concepts"):  # type: ignore[arg-type]
                  raise ValidationError.from_exception_data(...)  # trigger the ValidationError arm
      ```

**Commit**: `fix(validate): assert_never on unknown category in helper`

### ⛔ CHECKPOINT B — STOP, verify, record

- [ ] `make agent-check` clean.
- [ ] `make agent-test` clean.
- [ ] Each fix as its own commit.

---

## Phase C — LOW severity: latent / future-proofing

### C.1 — `to_dict` `match disclosure_mode:` is not future-proof

**File**: `pipelex/base_exceptions.py:229-253` (the `match disclosure_mode`
in `to_dict`).

**What**: The match covers VERBOSE and STRICT, the only current
DisclosureMode values. If a future variant is added (e.g. `AUDIT`) without
updating the match, the function silently returns `None` (no `case _`, no
implicit final return). Pyright would catch this statically — but a
`# type: ignore` or a runtime-constructed enum (e.g. via `DisclosureMode(string_value)`)
slips past static checking.

**Why it matters**: `to_problem_document` at line 297 does `payload["message"]`
— a `None` return crashes the HTTP adapter at `TypeError: 'NoneType' object
is not subscriptable`.

**Decision needed**: add `assert_never` on the fallthrough.

**Fix**:

- [ ] Add `case _ as unreachable: assert_never(unreachable)` to the
      `to_dict` match. Same shape would protect the `error_domain_to_http_status`
      match (see C.2).

**Test**: not strictly required (static check catches the regression), but
optional:

- [ ] Add a test that bypasses static checking and constructs an invalid
      DisclosureMode at runtime, asserting `assert_never`'s `AssertionError`
      fires.

**Commit**: `fix(errors): assert_never on unknown DisclosureMode in to_dict`

### C.2 — `error_domain_to_http_status` is not future-proof (pre-existing)

**File**: `pipelex/base_exceptions.py:163-174` (`error_domain_to_http_status`).

**What**: Same non-exhaustive-match shape as C.1 but pre-existing — not
touched by the previous xhigh round. Match covers INPUT, CONFIG | RUNTIME,
None. A future `ErrorDomain.SECURITY` value without a match arm silently
returns `None` from a `-> int` function.

**Decision needed**: bundle the fix with C.1 (one assert_never pattern in
both functions) or split. Recommend bundle.

**Fix**:

- [ ] Same `case _ as unreachable: assert_never(unreachable)` pattern.

**Commit** (bundled with C.1): `fix(errors): assert_never on unknown DisclosureMode and ErrorDomain matches`

### C.3 — Lifecycle tests don't assert the library_id value on teardown

**File**: `tests/integration/pipelex/pipeline/test_validate_bundle_library_lifecycle.py:73,95,113,131`.

**What**: The tests assert `"library_id" in latest_call.kwargs` but never
assert the value matches the actually-leaked library_id. A regression that
tore down a wrong library_id (e.g. a closure-captured stale id) would still
pass the test.

**Why it matters**: the test is the only thing pinning the A.2 fix from the
previous xhigh round. Weakening it means a regression could slip in
unnoticed.

**Decision needed**: split off as a separate test-quality fix, or fold into
the A.3 test commit. Recommend fold — the A.3 test also adds open_library
spying, which is exactly what's needed to close this gap.

**Fix** (fold into A.3 test):

- [ ] In the new A.3 test (and in the existing lifecycle tests), `mocker.spy`
      on `library_manager.open_library` AND `library_manager.teardown`. Assert
      `teardown.call_args.kwargs["library_id"] == open_library.spy_return[0]`
      (or equivalent).

**Commit**: covered by the A.3 commit.

### ⛔ CHECKPOINT C — STOP, verify, record

- [ ] `make agent-check` clean.
- [ ] `make agent-test` clean.
- [ ] Each fix as its own commit (C.1+C.2 bundled is one commit).

---

## Out of scope (recorded, not planned here)

These were surfaced by the xhigh pass but verified as REFUTED or already
documented:

- **teardown_current_library() clobbers caller's contextvar**: REFUTED.
  `set_current_library` already overwrites the caller's contextvar BEFORE the
  `try` block — the new `finally`'s `teardown_current_library()` just changes
  the post-failure state from "set to validate_bundle's failed library" to
  "set to None". No production caller currently sets a library_id then calls
  validate_bundle.
- **`_WrapperCogtError` violates error-class-location convention**: REFUTED.
  The convention test (`tests/unit/pipelex/errors/test_error_class_location_convention.py`)
  explicitly excludes modules whose `__module__` starts with `"tests."`. The
  docs generator's `_force_load_all_error_modules` only `rglob`s the
  `pipelex/` package, not `tests/`.
- **Trailing whitespace in `raw_message` produces doubled-space in fallback marker**:
  REFUTED as bug. Cosmetic; the marker is still parseable as a substring. No
  downstream consumer depends on whitespace normalization here.
- **`python -O` strips the `assert mthds_file_path is not None`**:
  UNREACHABLE. The preflight check at line 119-121 uses `if`, not `assert`,
  so all-None state raises ValidateBundleError before reaching the else.
- **Wrapper-wins provider_metadata OR-merge**: already documented + pinned by
  test (C.1-b in the previous xhigh round, commit `d8ad53ff`).
- **STRICT allowlist narrowing vs prior denylist**: already documented as
  intentional in B.1-a (previous xhigh round, commit `52325498`) — "single
  source of truth, adding a new field is one decision".

---

## Decisions

Record each decision here as it is taken, with date and rationale.

### 2026-05-24 — Phase A: A-fix-1 (move-into-try)

Applied **A-fix-1** as recommended in the plan. Moved every statement between
`library_manager.open_library()` and the existing `try:` INTO the try block
in all four bundle-loading entry points. The `success = False` flag stays
just before the `try`. No new abstraction.

### 2026-05-24 — Phase B.1: skipped (B.1-c, accept the gap)

REJECTED the plan's B.1-a recommendation. Reasoning:

- Verified by grep that `PipeFactoryError` / `PipeValidationError` are raised
  only from `pipelex/core/pipes/pipe_factory.py` and `pipe_abstract.py`.
  Concept-loading paths (`load_concepts_only_from_blueprints`) don't reach
  those modules — the dead-code claim in the docstring is correct.
- Renaming the framing to "Concept factory error" / "Concept validation
  failed" would be semantically dubious (concepts don't have factories) AND
  would HIDE the actual error type for the speculative future case where
  those arms ever do fire from a concepts-only path. The current framing is
  diagnostically accurate when those arms fire.
- The plan's worry — "if a future change ever surfaces a PipeValidationError
  from concept loading" — is speculative; if/when that happens, the right
  fix is at the source, not at the framing layer.

### 2026-05-24 — Phase B.2: applied (assert_never on Literal)

Added `case _ as unreachable: assert_never(unreachable)` to the
`match category:` block. The Literal at the call site is the right place
for runtime backup — even though pyright catches it statically, the failure
mode without `assert_never` is a silent `UnboundLocalError` on `msg`, which
would silently break the helper's translation contract. Loud beats silent.

### 2026-05-24 — Phase C.1 / C.2: skipped

REJECTED the plan's recommendation to add `assert_never` on the
`DisclosureMode` (`to_dict`) and `ErrorDomain | None` (`error_domain_to_http_status`)
matches. Reasoning:

- `python-standards.md` explicitly forbids `case _:` on exhaustive enum
  matches.
- `pyright` config has `reportMatchNotExhaustive = "error"` — a new enum
  variant without updating the match fails the typecheck at the match site.
  This is the linter feedback the rule relies on.
- No precedent for `assert_never` in `pipelex/`.
- `DisclosureMode("audit")` raises `ValueError` at enum construction —
  before the match. A dynamically-constructed enum can't be "wrong" without
  raising on construction.
- `# type: ignore` is an explicit developer opt-out; the codebase trusts
  static checking for these.

### 2026-05-24 — Phase C.3: folded into Phase A commit

Folded the library_id-value assertion into the existing lifecycle tests
during the A.3 commit, as recommended. Each lifecycle test now spies on
`library_manager.open_library` as well as `library_manager.teardown` and
asserts `teardown.call_args.kwargs["library_id"] == open_library.spy_return[0]`,
so a regression that tore down a stale closure-captured id would fail.

## Session log

Append one dated entry per session / checkpoint. Each entry must leave the
next session enough to cold-start: what landed, decisions taken, current
code state, what is broken or deferred, and the exact next action.

### 2026-05-24 — Phase A + B.2 landed, B.1 + C.1 + C.2 declined

**Landed commits** (on top of the 22-commit baseline `ab07bd2c`):

- `4b7683cb` `fix(validate): close pre-try leak window in bundle entry points`
  — Phase A + folded C.3. Moves all pre-`try` work into the `try` block in
  all four entry points. Extends lifecycle tests with `library_id` value
  assertion (C.3) + adds new tests for `BaseException` (simulated
  `CancelledError`) and `TypeError` raised in the pre-try window.
  Teeth-checked.
- `01f911cd` `fix(validate): assert_never on unknown category in shared helper`
  — Phase B.2. Adds `assert_never` to the `match category:` block, swaps
  silent `UnboundLocalError` for loud `AssertionError`. Teeth-checked.

**Declined** (recorded in Decisions above):

- B.1 (B.1-a recommendation): skipped — framing would mislead in the
  speculative case it was supposed to fix.
- C.1, C.2: skipped — go against the codebase rule forbidding `case _:` on
  exhaustive enum matches; pyright already enforces exhaustiveness.

**Current state**: working tree clean except this plan file. `make agent-check`
green; pipeline unit + integration tests green.

**Next action**: none — all 7 plan findings triaged and either landed or
declined with rationale recorded. Ready for review.
