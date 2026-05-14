# Template preprocessor — residual edge cases (deferred)

## Status: Superseded for the `@` cases by `wip/template-preprocessor-line-bounded-at.md` (2026-05-13). The strict line-bounded `@` rule eliminates Residual 1 and Residual 2 below — both are about inline `@var` shapes that are no longer valid under the new contract. The `$` variants of the same issues (`$name {{ jinja }}` not rewriting, `$user. info()` not rewriting) remain open and are explicit non-goals of the line-bounded plan; this doc stays as the reference if/when those `$` residuals are tackled in a follow-up PR.

## Original status (historical): Open. Two false-negatives observed during PR review of `fix/Template-preprocessor-footguns` (2026-05-13). Not blocking — the CSS / email / code collisions that motivated the original fix all work. These are subtle shapes that the heuristic still silently passes through without interpolation.

## Quick start (cold session)

Working directory: `/Users/lchoquel/repos/Pipelex/pipelex`.

Read in this order:

1. This file.
2. `wip/template-preprocessor-css-collision.md` — original design rationale (Strategy 2 + Strategy 3 from there shipped; this doc adds two more residuals on top).
3. `pipelex/cogt/templating/template_preprocessor.py` — ~85 lines, the file being changed.
4. `tests/unit/pipelex/cogt/templating/test_template_preprocessor.py` — the test file being extended (single `TestTemplatePreprocessor` class, 80 tests today).

Project conventions (from `pipelex/CLAUDE.md`):

- One `TestClass` per test module. New tests go inside `TestTemplatePreprocessor`.
- pytest-mock, never `unittest.mock`. Neither residual needs mocking.
- `make agent-check` after changes (Ruff + pyright + mypy + plxt).
- Targeted test: `.venv/bin/pytest -q tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`.

## Current state of the regex (post-CSS-collision fix)

`pipelex/cogt/templating/template_preprocessor.py:55-58`:

```python
_SIGIL_PATTERN = re.compile(
    r"(?:(?<!\w)(@\??)|(\$))(?![0-9])([a-zA-Z0-9_.]+)(?![a-zA-Z0-9_.])"
    r"(?!\s*(?:[({\"']|[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))))"
)
```

Three parts that matter here:

- **Identifier class** `[a-zA-Z0-9_.]+` — greedy, includes trailing dots; stripped in the dispatcher (`_replace_sigil`) when the captured name ends with `.`.
- **Direct opener arm** `[({\"']` — blocks `@var (...)`, `@var "..."`, `@var '...'`, `@var {`.
- **Inner-word arm** `[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))` — blocks one word + `(` or single `{` (the `\{(?!\{)` is the Jinja-aware part: `{{` is allowed).

Both residuals below stem from quirks of these three pieces.

---

## Residual 1 — `@var {{ jinja }}` / `$var {{ jinja }}` not rewritten

### Symptom

```python
preprocess_template("Hello @name {{ greeting }}")
# 'Hello @name {{ greeting }}'   ← @name NOT rewritten (expected: {{ name|tag("name") }})

preprocess_template("Hello $name {{ greeting }}")
# 'Hello $name {{ greeting }}'   ← same problem on the $ arm
```

### Root cause

The **inner-word arm** uses `\{(?!\{)` so it allows `{{` (it only blocks a single `{` that isn't part of Jinja's `{{`). The **direct opener arm** doesn't — `[({\"']` matches any single `{`, including the first `{` of `{{`.

So `@name {{` walks the direct arm:

- `\s*` matches the space.
- `[({\"']` tries `{` — matches. Direct arm fires.
- Negative lookahead fails → `@name` is not matched.

The inner-word arm and the direct arm are inconsistent: the design comment on `pipelex/cogt/templating/template_preprocessor.py:38-41` explicitly says `@var with {{ ... }}` should remain interpolated. Today it doesn't.

### Fix sketch

Split the `{` case out of the direct arm and reuse the `\{(?!\{)` trick:

```python
_SIGIL_PATTERN = re.compile(
    r"(?:(?<!\w)(@\??)|(\$))(?![0-9])([a-zA-Z0-9_.]+)(?![a-zA-Z0-9_.])"
    r"(?!\s*(?:[(\"']|\{(?!\{)|[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))))"
)
```

The change is `[({\"']` → `[(\"']|\{(?!\{)`. After the fix:

- `@var (...)` — `(` matches the bracket class. ✓ still blocked.
- `@var "..."`, `@var '...'` — same. ✓ still blocked.
- `@var {` — `\{(?!\{)` matches (single `{`). ✓ still blocked.
- `@page { margin }` — same as above. ✓ still blocked.
- `@var {{ jinja }}` — `\{(?!\{)` fails because next char is `{`. Direct arm doesn't fire. Inner-word arm starts with `[a-zA-Z]` — `{` not in class, fails. Whole lookahead doesn't fire. `@var` IS rewritten. ✓ fixed.

### Tests to add (red phase, inside `TestTemplatePreprocessor`)

```python
def test_at_var_then_jinja_open_rewrites(self):
    """`@var {{ jinja }}` must rewrite @var — the direct-opener arm must be Jinja-aware."""
    template = "Hello @name {{ greeting }}"
    result = preprocess_template(template)
    expected = 'Hello {{ name|tag("name") }} {{ greeting }}'
    assert result == expected

def test_dollar_var_then_jinja_open_rewrites(self):
    """`$var {{ jinja }}` must rewrite $var — same fix as the @ arm."""
    template = "Hello $name {{ greeting }}"
    result = preprocess_template(template)
    expected = "Hello {{ name|format() }} {{ greeting }}"
    assert result == expected
```

Also add a regression guard so `@var {` (single brace, not Jinja) stays blocked:

```python
def test_at_var_then_single_brace_pass_through(self):
    """`@var {` (single brace, not Jinja) is still a code-shape opener — must NOT rewrite."""
    template = "Try @var { but not jinja"
    result = preprocess_template(template)
    assert result == template
```

### Open question for the implementer

Is `@var {` (single brace) ever a legit Pipelex template construct? Probably not — the design doc says template variables aren't followed by `("'{` in practice. Keep the single-`{` block as-is; only `{{` becomes safe.

---

## Residual 2 — `@var.` (trailing dot) + ` Word (`  not rewritten

### Symptom

```python
preprocess_template("The transaction was @status. Amount (USD).")
# 'The transaction was @status. Amount (USD).'   ← @status NOT rewritten

preprocess_template("Reply @user. info()")
# 'Reply @user. info()'                          ← @user NOT rewritten
```

Realistic shape: a sentence-ending sigil followed by a new sentence that contains a parenthetical (very common in prose-heavy LLM prompts).

### Root cause

Two interacting design choices:

1. **Identifier class `[a-zA-Z0-9_.]+` includes `.`**, so the greedy match consumes the trailing dot — the dispatcher then strips it as sentence punctuation. This was the cheapest way to support both `@user.profile` (dotted access) and `@user.` (sentence end).

2. **Backtracking is locked out by `(?![a-zA-Z0-9_.])`** — the post-identifier check. The greedy match captures `status.`; if the lookahead fails, the engine tries `status` (no dot), but `(?![a-zA-Z0-9_.])` then fails because the next char is `.`. No shorter match works.

Concrete walk for `@status. Amount (USD)`:

- Identifier matches `status.` (greedy with dot).
- `(?![a-zA-Z0-9_.])` passes (next char is `S`).
- Inner-word arm: `\s*` consumes ` `, `[a-zA-Z][\w-]*` matches `Amount`, `\s*` consumes ` `, `(?:[(]|\{(?!\{))` matches `(`. Inner-word fires.
- Whole match rejected. Backtrack to `status` fails (next is `.`).
- Final: `@status.` passes through unchanged.

### Fix sketch (cleaner option)

Make the identifier class NOT include the trailing dot, and rely on dotted-access via a structured pattern:

```python
_SIGIL_PATTERN = re.compile(
    r"(?:(?<!\w)(@\??)|(\$))(?![0-9])([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)(?![a-zA-Z0-9_.])"
    r"(?!\s*(?:[({\"']|[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))))"
)
```

Identifier change: `[a-zA-Z0-9_.]+` → `[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*` (segments separated by single dots, no trailing dot allowed in the capture).

After this change:

- `@invoice_text.` — identifier captures `invoice_text` (no dot). The `.` is now text after the match, emitted literally by the surrounding template engine. Output: `{{ invoice_text|tag("invoice_text") }}.` — same as today.
- `@user.profile.bio` — identifier captures `user.profile.bio` via `(?:\.[a-zA-Z0-9_]+)*`. Same as today.
- `@status. Amount (USD)` — identifier captures `status`. The lookahead sees `. Amount (USD)`:
  - Direct arm: `\s*` zero, then `[({\"']` — `.` not in set, fails.
  - Inner-word arm: `\s*` zero, then `[a-zA-Z]` — `.` not in class, fails.
  - Lookahead doesn't fire. `@status` IS rewritten. ✓ fixed.

### Bonus: dispatcher simplification

If the identifier never has a trailing dot, the `trailing_dot` strip in `_replace_sigil` (`pipelex/cogt/templating/template_preprocessor.py:74-79`) becomes dead code. Delete it:

```python
def _replace_sigil(match: Match[str]) -> str:
    sigil = _Sigil(match.group(1) or match.group(2))
    variable: str = match.group(3)
    match sigil:
        case _Sigil.AT_OPTIONAL:
            return f'{{% if {variable} %}}{{{{ {variable}|tag("{variable}") }}}}{{% endif %}}'
        case _Sigil.AT:
            return f'{{{{ {variable}|tag("{variable}") }}}}'
        case _Sigil.DOLLAR:
            return f"{{{{ {variable}|format() }}}}"
```

### Tests to add

Drop or rewrite the existing trailing-dot tests — their assertions still hold after the fix (the dot is emitted via the surrounding text instead of the dispatcher), but make sure they continue to pass:

- `test_dollar_variable_with_trailing_dot`
- `test_at_variable_with_trailing_dot`
- `test_optional_at_variable_with_trailing_dot`
- `test_multiple_at_variables_with_trailing_dots`
- `test_nested_with_trailing_dot_in_complex_sentence`

Add the new red-phase tests for the residual:

```python
def test_at_var_trailing_dot_then_word_paren_rewrites(self):
    """`@var. Word (extra)` must rewrite @var — sentence-ending sigil followed by a new
    sentence with a parenthetical is a realistic prose shape.
    """
    template = "The transaction was @status. Amount (USD)."
    result = preprocess_template(template)
    expected = 'The transaction was {{ status|tag("status") }}. Amount (USD).'
    assert result == expected

def test_dollar_var_trailing_dot_then_word_paren_rewrites(self):
    template = "Reply $user. info()"
    result = preprocess_template(template)
    expected = "Reply {{ user|format() }}. info()"
    assert result == expected

def test_optional_at_var_trailing_dot_then_word_paren_rewrites(self):
    template = "Optional @?notes. See (next page)."
    result = preprocess_template(template)
    expected = 'Optional {% if notes %}{{ notes|tag("notes") }}{% endif %}. See (next page).'
    assert result == expected
```

### Risks / things to double-check

- **`@..foo` and similar malformed identifiers**: today, `[a-zA-Z0-9_.]+` matches `..foo` (greedy). After the fix, identifier must start with `[a-zA-Z0-9_]`, so `@.foo` fails to match — `@` stays literal. This is a behavior change for malformed input but seems harmless (no test covers it; nobody writes `@.foo`).
- **`@user.profile.`** (dotted access + trailing dot): today captures `user.profile.` and strips the dot → `{{ user.profile|tag("user.profile") }}.`. After the fix: captures `user.profile`, dot is text → same output. Verify with a parametrized test.
- **Inner-word arm interaction with the new identifier**: the inner-word arm is independent of the identifier class change. Existing tests for `@keyframes spin {`, `@layer reset {`, `@import url(...)` should be untouched. Re-run the full module.

---

## Suggested TDD plan

Both fixes are independent — land them in separate PRs or sequentially in one branch.

### Phase 1 — Residual 1 (Jinja `{{` in direct arm)

1. Add the three tests above (red).
2. Apply the regex change `[({\"']` → `[(\"']|\{(?!\{)`.
3. Re-run targeted tests — all green.
4. `make agent-check`.

### Phase 2 — Residual 2 (trailing dot + word + paren)

1. Add the three new red-phase tests.
2. Apply identifier change `[a-zA-Z0-9_.]+` → `[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*`.
3. Delete the `trailing_dot` block from `_replace_sigil`.
4. Re-run all 80+ existing tests — every trailing-dot test should still pass because the dot survives as literal text.
5. `make agent-check`.

### Phase 3 — Workspace sanity check

Same as the original fix's Phase 4: grep `.mthds` files in `/Users/lchoquel/repos/Pipelex/` for shapes that would behave differently under the new rules. Specifically:

```bash
# Mixed-Jinja templates that may now interpolate where they didn't:
grep -rn '@[a-zA-Z_][a-zA-Z_0-9.]*[[:space:]]*{{' --include="*.mthds" . | head -50
grep -rn '\$[a-zA-Z_][a-zA-Z_0-9.]*[[:space:]]*{{' --include="*.mthds" . | head -50

# Sentence-ending sigils followed by parentheticals:
grep -rn '@[a-zA-Z_][a-zA-Z_0-9.]*\.[[:space:]][A-Z][a-zA-Z]*[[:space:]]*[(]' --include="*.mthds" . | head -50
```

Decide per hit: accept (intended fix), document, or revert.

### Phase 4 — CHANGELOG + docs

Single `Fixed` entry under `[Unreleased]`. Cross-link to this doc. No new public API; no need to update `mthds-language-tutorial.md` or `pipe_compose_spec.py` (the escape mechanism is unchanged).

---

## Out of scope

- No new escape mechanism beyond `@@` / `$$`.
- No reserved-keyword list.
- No HTML/CSS-aware parsing.
- No changes to the call sites of `preprocess_template` — all benefit transparently.
