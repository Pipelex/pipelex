# Phase 7 — /code-review fix list

**Throwaway doc.** Self-contained for a cold-start session. Apply the fixes below, run the final verification block, delete this file. No PR description, no permanent doc value.

## Context

`feature/API-readiness-2` is at HEAD. Phase 7 just landed uncommitted (changes the user has staged in working tree): a `_force_load_all_error_modules()` helper in `pipelex/errors/error_pages_generator.py`, an xfail removal in `tests/unit/pipelex/errors/test_error_class_location_convention.py`, 34 regenerated `docs/errors/*.md` pages, and tracker updates (`CHANGELOG.md`, `TODOS.md`, `wip/api-readiness-2-handoff-drafts.md`). A high-effort `/code-review` ran across 5 finder angles + a sweep; the verified findings are below.

**None of the findings is a correctness regression.** The helper works, discovery is complete (241 of 241 AST classes reachable at runtime), production bootstrap is unaffected (`Pipelex.make()` still loads only ~203 subclasses; the helper is not called). What follows is the cleanup pass.

## Fix order

Apply top-down. Findings 1–3 are blocking. 4–7 are doc coherence (project Phase 0 policy: "every time a doc contradicts the code, review bots get confused"). 8–11 are minor footgun mitigations.

---

## 1. Helper docstring: precondition 2 is not enforced by any test

**File:** `pipelex/errors/error_pages_generator.py` (docstring claim) + `tests/unit/pipelex/errors/test_error_class_location_convention.py` (new test)
**Symptom:** Docstring of `_force_load_all_error_modules` claims `precondition 2` (no SDK imports in `*_exceptions.py`) is "enforced by `tests/unit/pipelex/errors/test_error_class_location_convention.py`". That test only checks file-name placement (precondition 1). Nothing enforces the import-weight contract; the claim is empirically true but unverified by CI.

**Fix (decided: Option A — add the AST check).** Phase 7 reintroduces force-import, so the docstring's safety claim deserves a real automated check. Extend `tests/unit/pipelex/errors/test_error_class_location_convention.py` with a new method on `TestErrorClassLocationConvention`:

```python
def test_no_heavy_third_party_imports_in_error_modules(self) -> None:
    """Every exceptions.py / *_exceptions.py imports only base error classes — no SDK pulls.

    Phase 7's discovery helper force-loads every match. If a *_exceptions.py
    were to import a plugin SDK (anthropic, boto3, openai, mistralai, google-genai,
    portkey-ai, azure-identity, pypdfium2, fal-client, etc.), the SDK would be
    pulled into every pytest collection and every dev CLI invocation — defeating
    the deferred-import design that keeps optional plugin deps optional.
    """
    forbidden_top_level = {
        "anthropic", "boto3", "botocore", "openai", "mistralai", "google",
        "portkey_ai", "azure", "pypdfium2", "fal_client",
    }
    offenders: list[tuple[Path, str]] = []
    for path in sorted(_PIPELEX_ROOT.rglob("*.py")):
        if path.name != "exceptions.py" and not path.name.endswith("_exceptions.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in forbidden_top_level:
                        offenders.append((path, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in forbidden_top_level:
                    offenders.append((path, node.module))
    if offenders:
        lines = ["Error modules import third-party SDKs — would slow every CI run:", ""]
        for path, name in offenders:
            lines.append(f"  - {path.relative_to(_PIPELEX_ROOT.parent)}: {name}")
        raise AssertionError("\n".join(lines))
```

Note: `google` is on the forbidden list because `google.generativeai` / `google.cloud.aiplatform` are the heavy ones; if any future error module legitimately needs `google.api_core.exceptions` or similar lightweight typed-exception imports, narrow the entry to `google.generativeai` / `google.cloud` rather than the whole `google` namespace.

**Verify the test has teeth** before moving on: temporarily add `import anthropic` to the top of `pipelex/plugins/anthropic/anthropic_exceptions.py`, re-run the convention test, confirm it fails with the offender listed, then revert.

The docstring claim in `pipelex/errors/error_pages_generator.py` stays as-is (now accurate — both preconditions enforced by the convention test).

---

## 2. Test-fixture filter gap: `pipelex/test_extras/` and friends

**File:** `pipelex/errors/error_pages_generator.py`, line 79 (and `_top_level_branch_label` indirectly)
**Symptom:** `cls.__module__.startswith("tests.")` does not exclude shipped fixture packages. Confirmed via `find`:

```
pipelex/test_extras/                   (has __init__.py)
pipelex/temporal/test_extras/          (has __init__.py)
pipelex/temporal/test_helpers/         (has __init__.py)
```

None of those currently define a `PipelexError` subclass (`grep` clean), but if anyone adds `pipelex/temporal/test_extras/wf_test_exceptions.py` with `class WfTestError(PipelexError): ...` (legitimate test fixture), `_force_load_all_error_modules` will rglob-match it, the runtime walk will yield it, `__module__` is `pipelex.temporal.test_extras.wf_test_exceptions` (does NOT start with `tests.`), and it will leak into `docs/errors/` and the URI uniqueness check.

**Fix.** Drive the production filter off the file path, not the module string. In `pipelex/errors/error_pages_generator.py`, just above `iter_pipelex_error_subclasses`:

```python
_PIPELEX_ROOT = Path(pipelex.__file__).resolve().parent
_FIXTURE_DIR_NAMES = frozenset({"test_extras", "test_helpers"})


def _is_production_subclass(cls: type[PipelexError]) -> bool:
    """True when ``cls`` should appear in the production discovery set.

    Excludes synthetic subclasses created inside test modules (``tests.*``) and
    classes defined inside shipped fixture packages (``pipelex/.../test_extras/``,
    ``pipelex/.../test_helpers/``) — those are test infrastructure that happens
    to be packaged alongside production code so it can be reused across
    downstream test suites.
    """
    if cls.__module__.startswith("tests."):
        return False
    module = sys.modules.get(cls.__module__)
    if module is None:
        return True
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        return True
    try:
        rel = Path(module_file).resolve().relative_to(_PIPELEX_ROOT)
    except ValueError:
        return True
    return _FIXTURE_DIR_NAMES.isdisjoint(rel.parts)
```

Then in `iter_pipelex_error_subclasses`, replace `if not cls.__module__.startswith("tests."):` with `if _is_production_subclass(cls):`.

Add `import sys` to the imports.

Add a test in `tests/unit/pipelex/errors/test_error_pages_generator.py`:

```python
def test_fixture_package_subclasses_are_filtered_out(self) -> None:
    """A PipelexError subclass defined under pipelex/.../test_extras/ must NOT leak into the production discovery set."""
    # Synthesize a class whose __module__ resolves to a fixture-dir file. We
    # can't actually create one without a write — so assert the filter on a
    # mock-style fake module via sys.modules manipulation, OR (simpler) assert
    # _is_production_subclass directly on a tuple of (cls.__module__, fake __file__).
    # Simplest: parametrize _is_production_subclass against known paths.
    ...
```

The simplest pin is a parametrized unit test calling `_is_production_subclass` (export it with a leading underscore but reachable via `# noqa: PLC2701`) on synthetic class objects whose `sys.modules[__module__].__file__` is monkey-patched. If that's too clever, leave it as an "untested by direct unit test but covered by the convention test" — the bigger win is the filter itself.

---

## 3. Handoff drafts contradict Phase 7 in the same commit

**File:** `wip/api-readiness-2-handoff-drafts.md`
**Symptom:** Section 5 in both Form-1 (human Slack) and Form-2 (agent prompt) says: "docs/errors/ site is currently incomplete... until Phase 7 closes the discovery contract" and "Awareness only — no code change needed in pipelex-api; the gap closes when Phase 7 lands." Phase 7 IS in this commit-set. 34 new doc pages shipped. AST set = runtime set. The handoff is internally inconsistent with the CHANGELOG and the new Checkpoint 7 entry.

**Fix.** Rewrite section 5 in both forms. In Form 1 (around line 12), remove the bullet entirely (the gap is closed; nothing for the API team to be aware of). In Form 2 (around line 57, the "5. `docs/errors/` is incomplete" subsection), replace with:

```markdown
**5. `docs/errors/` is complete.** This branch's Phase 7 commit closes the previously-known discovery gap — every `PipelexError` subclass now has a generated reference page; every `type_uri` value resolves to a live page on docs.pipelex.com. No action in pipelex-api.
```

Re-number the subsequent "Webhook signing" entry from 6 to 5.

---

## 4. TODOS.md Phase 6 acceptance text now contradicts Phase 7

**File:** `TODOS.md`, lines 215 and 230
**Symptom:** Phase 6 spec still reads:

- Line 215: "Normal imports load everything now — no force-import phase needed, no allowlist to maintain."
- Line 230 (Acceptance): "discovery has no runtime side effects"

Phase 7 (added below in the same doc) reverses both. Per the doc's own Phase 0 policy this is exactly the contradiction that confuses review bots.

**Fix.** Edit both lines in-place with a short forward-reference, preserving the historical Phase 6 intent:

Line 215 — append: " *(Refined by Phase 7: discovery is rehydrated by a dev/test-time `_force_load_all_error_modules` helper. Production bootstrap remains untouched.)*"

Line 230 — change "discovery has no runtime side effects" to "discovery has no production-runtime side effects (the dev/test-time `_force_load_all_error_modules` helper added in Phase 7 walks the filesystem inside the docs generator and the URI uniqueness test only)".

---

## 5. `wip/error-handling/api-companion-revisions.md` references a deleted file

**File:** `wip/error-handling/api-companion-revisions.md`, around line 262
**Symptom:** Still describes `pipelex/errors/error_module_registry.py` as the live discovery mechanism (deleted in Phase 6), claims `*_errors.py` is a recognized pattern (dropped in Phase 6), and references a "small explicit list of non-standard locations" (the allowlist that no longer exists).

**Fix.** Replace the stale paragraph with:

```markdown
- **`pipelex/errors/error_pages_generator.py::iter_pipelex_error_subclasses`** — yields every `PipelexError` subclass. Calls `_force_load_all_error_modules()` (a `functools.cache`-d helper) on first invocation to rglob the package for `exceptions.py` / `*_exceptions.py` modules and force-import each. Discovery is complete (AST set = runtime set, enforced by `tests/unit/pipelex/errors/test_error_class_location_convention.py`); the helper runs only inside dev/test-time consumers (the docs generator and the URI uniqueness test), never on production bootstrap.
```

---

## 6. dev CLI command docstring stale

**File:** `pipelex/cli/dev_cli/commands/generate_error_pages_cmd.py`, line 19
**Symptom:** Docstring says "Bootstraps Pipelex so every PipelexError subclass is imported and thus discoverable". Since Phase 7, discovery is driven by the helper inside `iter_pipelex_error_subclasses`, not by `Pipelex.make()`. Verified empirically: the page count is identical with or without `Pipelex.make()`.

**Fix (minimal).** Edit lines 18–22 to:

```python
def generate_error_pages_cmd(output: Path | None = None, quiet: bool = False) -> None:
    """Generate per-class error documentation pages.

    Bootstraps Pipelex (kept for parity with other dev CLI commands and to surface
    config / setup errors loudly), then calls :func:`generate_error_pages`. The
    underlying discovery rgrobs every ``exceptions.py`` / ``*_exceptions.py``
    via :func:`iter_pipelex_error_subclasses` — no manual import or class-list
    update is needed when a new error class lands. Pages already carrying
    ``<!-- gstack:authored -->`` are preserved so hand-edited reference content
    is never clobbered.
    ...
    """
```

**Out of scope (do not act, just note):** removing the `Pipelex.make()` call would let docs generate on a fresh checkout without inference setup. Worth raising in a follow-up after this PR lands; not a blocker.

---

## 7. CHANGELOG framing implies the fix is plugin-only

**File:** `CHANGELOG.md`, line 11
**Symptom:** The Phase 7 line in the "Per-class error documentation pages" entry leads with "plugin error classes whose home module is only reached via a deferred import (gateway, anthropic, bedrock, mistral, portkey, google, openai/vertex, azure, plus standalone classes like `FalCredentialsError`, `GraphSpecError`, `PipeBatchFactoryError`, etc.)". The helper actually imports every `*_exceptions.py` regardless of plugin status. `ConceptSpecError`, `PyPdfium2RendererError`, `GraphSpecError` are not plugin classes.

**Fix.** Reword the appended sentence on line 11 to:

```markdown
The generator's discovery walks every `exceptions.py` / `*_exceptions.py` module the Phase 6 filename convention enforces — including modules whose home file is only reached via a deferred import path (plugin worker / factory chains for anthropic, bedrock, gateway, google, mistral, openai/vertex, azure, portkey, plus standalone classes like `FalCredentialsError`, `GraphSpecError`, `PipeBatchFactoryError`, `PyPdfium2RendererError`, `ConceptSpecError`). No manifest to maintain; adding a new error class is one step.
```

---

## 8. Helper has no try/except around `importlib.import_module`

**File:** `pipelex/errors/error_pages_generator.py`, line 60 area
**Symptom:** A single broken `*_exceptions.py` (a typo'd import, a removed base class) aborts the entire force-load. `functools.cache` does not cache on exception, so subsequent calls re-walk and re-fail. The failure surfaces in three tests with the same opaque `ImportError` framed inside `error_pages_generator.py` rather than the buggy module.

**Fix (small, defensible).** Wrap the import in a per-module try/except, accumulate failures, raise once:

```python
@functools.cache
def _force_load_all_error_modules() -> None:
    """..."""
    pipelex_root = Path(pipelex.__file__).resolve().parent
    failures: list[tuple[str, BaseException]] = []
    for path in sorted(pipelex_root.rglob("*.py")):
        name = path.name
        if name != "exceptions.py" and not name.endswith("_exceptions.py"):
            continue
        rel = path.relative_to(pipelex_root.parent).with_suffix("")
        dotted = ".".join(rel.parts)
        try:
            importlib.import_module(dotted)
        except ImportError as exc:
            failures.append((dotted, exc))
    if failures:
        lines = ["One or more error modules failed to import during discovery:"]
        lines.extend(f"  - {name}: {exc}" for name, exc in failures)
        msg = "\n".join(lines)
        raise RuntimeError(msg)
```

Then `functools.cache` correctly caches only the success path (the no-exception case), and a single bad module surfaces with the dotted module name in the failure message.

**Trade-off note:** if you skip this, you stay aligned with the deleted `error_module_registry.py`'s pre-Phase-6 behavior (no try/except either). Today no module is broken, so the practical cost is zero. Worth doing for the diagnostic quality.

---

## 9. Test docstring overclaims symmetry

**File:** `tests/unit/pipelex/errors/test_error_class_location_convention.py`, around line 165
**Symptom:** Docstring of `test_runtime_walk_discovers_every_ast_classified_subclass` says "the AST set and the runtime set are equal by construction" — but the body checks `missing = ast_names - runtime_names` (subset, not equality). The asymmetry is intentional and correct, but the docstring overstates the test.

**Fix.** Replace the second paragraph with:

```python
        """Discovery completeness: AST-discovered subclasses are reachable via ``__subclasses__()`` after the discovery helper runs.

        Failing here means a properly-named ``exceptions.py`` exists on disk but
        the discovery helper did not import it — the symptom that previously
        shipped as silently-dropped docs pages and missed ``type_uri``
        uniqueness checks. The Phase 7 fix wires
        :func:`_force_load_all_error_modules` into ``iter_pipelex_error_subclasses``
        so every AST-discovered class is reachable at runtime; this is a
        one-sided subset check (runtime ⊇ AST) — runtime-only classes
        (e.g. dynamically constructed via ``type()``) are intentionally
        allowed and not caught here.
        """
```

---

## 10. Middle convention test silently skips the helper

**File:** `tests/unit/pipelex/errors/test_error_class_location_convention.py`, around line 130
**Symptom:** `test_runtime_subclasses_walk_every_loaded_pipelex_error_subclass_lives_in_a_properly_named_module` walks `PipelexError.__subclasses__()` directly. In isolation it sees 19 subclasses; only ~241 if a prior test fired the helper. The test name suggests broader coverage than it provides.

**Fix.** Make the test deterministic by firing the helper first:

```python
    def test_runtime_subclasses_walk_every_loaded_pipelex_error_subclass_lives_in_a_properly_named_module(self) -> None:
        """Walk ``PipelexError.__subclasses__()`` transitively after the discovery helper has fired and assert every loaded subclass lives in an accepted module."""
        # Trigger the Phase 7 discovery helper so the runtime set matches the AST set.
        # Without this, the test silently runs against only the ~19 naked-import
        # subclasses, which all happen to be convention-compliant — green for the
        # wrong reason.
        list(iter_pipelex_error_subclasses())

        seen: set[type[PipelexError]] = set()
        stack: list[type[PipelexError]] = [PipelexError]
        # ... rest of the body unchanged
```

---

## 11. `functools.cache` has no documented reset path

**File:** `pipelex/errors/error_pages_generator.py`
**Symptom:** Long-lived dev sessions (pytest-watch, IDE test runners, REPL) cannot pick up a newly added `*_exceptions.py` without restarting Python. No docstring mentions the escape hatch.

**Fix (one-line docstring nudge).** Append to the `_force_load_all_error_modules` docstring:

```
    To clear the cache (e.g. inside a long-lived dev session after adding a
    new ``*_exceptions.py``), call ``_force_load_all_error_modules.cache_clear()``.
```

---

## Final verification

After applying all fixes:

```bash
# Lint + type check
make agent-check

# Convention + generator + uniqueness tests
.venv/bin/pytest -n auto -o log_level=WARNING --tb=short -q \
  tests/unit/pipelex/errors/ \
  tests/unit/pipelex/test_pipelex_error_type_uri_uniqueness.py

# Confirm Finding 1's new SDK-import test has teeth: temporarily edit
# pipelex/plugins/bedrock/bedrock_exceptions.py to add `import boto3`, rerun
# the convention test, confirm it fails listing bedrock_exceptions.py as the
# offender, then revert.

# Confirm production bootstrap unchanged
.venv/bin/python -c "
from pipelex.pipelex import Pipelex
Pipelex.make()
from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_pages_generator import _force_load_all_error_modules
def walk(c, s):
  if c in s: return
  s.add(c)
  for x in c.__subclasses__(): walk(x, s)
s = set(); walk(PipelexError, s)
print(f'Pipelex.make() alone: {len(s)} subclasses (expect ~204 including PipelexError root)')
print(f'Helper triggered: {_force_load_all_error_modules.cache_info().currsize > 0}')
"

# If the docs generator output changes, regenerate and inspect
.venv/bin/pipelex-dev generate-error-pages
git status --short docs/errors/

# Full suite before commit
make agent-test
```

Expected: all tests green, `Helper triggered: False` confirms production isolation, no new orphan or missing pages in `docs/errors/`.

## After applying

- Commit the fixes (one commit, or staged by group: blocking-3, doc-coherence-4, footguns-4).
- Delete this file: `rm wip/phase-7-code-review-fixes.md`.
- Move on to opening the PR.
