# Template preprocessor — sigil collision fix (TDD plan)

## Status: `$` sigil footgun fixes landed (Phase 7 — 2026-05-13)

The inline `$` sigil now mirrors the `@` candidate pattern's word-boundary lookbehind and uses a strict segmented identifier shape. Word-adjacent `$` (`micro$oft`, `user$host.com`, `P@ssw$rd123`, `a$b$c`) is now silent pass-through; `$name..` renders cleanly as `{{ name|format() }}..` (consecutive dots stay outside the match as literal punctuation). The trailing-dot kludge in `_replace_dollar_sigil` is gone — unreachable under the new identifier shape. `make agent-check` clean, `make agent-test` green.

### Deviations from Phase 7 plan

1. **One existing test updated to match the new contract.** `tests/unit/pipelex/pipe_operators/pipe_compose/test_structured_content_composer.py::TestStructuredContentComposerRuntimeParams::test_template_field_accesses_extra_context` used the template `"Summary for $fiscal_year Q$quarter"`, which relied on the pre-Phase-7 deviation that allowed word-adjacent `$` to interpolate (so `Q$quarter` → `Q1`). Under Phase 7's word-boundary lookbehind that shape is intentional silent pass-through. The template was changed to `"Summary for $fiscal_year, quarter $quarter"` (separator added so the second `$` is not word-adjacent) and the assertion updated to `"quarter 1" in result.generated_summary`. Test intent (verifying `extra_context` is merged into template rendering) is preserved.
2. **No `.mthds` workspace migration needed.** The Phase 7.3 grep flagged two lines in `mthds-ui/data/pipelines/pipeline_25/bundle.mthds` (`"# Text Report\n\n$classified.content"` and `"# Data Report\n\n$classified.content"`), but these are grep false positives — the `n` matched by `[[:alnum:]_]` is the `n` of the TOML `\n` escape; after TOML decoding the `$` is preceded by a real newline (whitespace), so the new regex still rewrites correctly.

## Status: declared-inputs gating planned (Phase 8 — open, 2026-05-13)

**Coding must stop here for checkpoint before Phase 8.** Phase 7 is delivered (regex tightening, tests, CHANGELOG entry). Phase 8 opens a new area of concern — function split, signature change, and call-site threading across 9 files — and should be picked up in a fresh session with this `TODOS.md` as the entry point.

The strict line-bounded `@` rule (landed earlier today) catches inline `@var` typos but is hostile to CSS in HTML templates — coding agents writing `<style>@media (...) { ... }</style>` get a `TemplateSigilSyntaxError` and have to learn the `@@` escape. Phase 8 relaxes the validator so that inline `@<ident>` only raises when `<ident>` is a declared input of the surrounding pipe; otherwise the candidate passes through silently. The rewriter (line-bounded substitution) is unchanged — alone-on-line `@var` still rewrites to `{{ var|tag("var") }}`. See "Phase 8 — Declared-inputs gating for the `@`-sigil validator" below for the TDD plan.

## Status: strict line-bounded `@` rule landed (2026-05-13)

The redesign described in `wip/template-preprocessor-line-bounded-at.md` shipped:

- `@var` / `@?var` must be alone on their own line. Inline candidates raise `TemplateSigilSyntaxError`
  at load time, surfaced through pydantic validation with line number + migration hint.
- `$var` keeps its inline contract (unchanged).
- `@@` and `$$` escapes preserved.
- Workspace `.mthds` files migrated; all tests green; `make agent-check` clean; `make agent-test` clean.

The history below documents the original heuristic CSS-collision fix, kept for context — the
heuristic regex it produced was replaced by the strict rule above.

## Status: heuristic CSS-collision fix complete (earlier)

All phases (1–6) landed. Full `make agent-test` is green and `make agent-check` is clean. The
work is ready to ship via `/release`.

### Deviations from the original plan

Two design points evolved during implementation. They are reflected in the code, the new tests,
and the CHANGELOG, but the prose below is the historical plan and was not rewritten to match —
read this block first, then the rest as TDD history.

1. **Single-pass regex instead of three sequential `re.sub` calls.** The plan's three
   `re.sub(...)` calls (one per sigil) cannot share the lookahead reliably: after the first pass
   rewrites `@var` to `{{ var|tag("var") }}`, the second pass's `(?!\s*[({"'])` lookahead sees
   the inserted `{` and aborts the next `$var` match. Combined into a single
   `_SIGIL_PATTERN` with an alternation `(?:(?<!\w)(@\??)|(\$))...` and a dispatch callback
   (`_replace_sigil`) so the lookahead only sees original-template characters. The original
   `replace_at_variable` / `replace_optional_at_variable` / `replace_dollar_variable` helpers
   were folded into the single callback.
2. **`$` arm omits the `(?<!\w)` lookbehind.** The plan applied the lookbehind uniformly to
   all three sigils, but it broke prose like `Summary for $fiscal_year Q$quarter` — `Q`
   precedes the `$`, blocking the match. Splitting the alternation so only the `@`/`@?` arm
   carries the lookbehind keeps emails (`user@example.com`) protected while letting
   word-adjacent `$var` interpolate. Dollar amounts (`$10`) remain protected by the
   `(?![0-9])` lookahead.
3. **Inner-word lookahead added for `@keyframes spin {`, `@layer reset {`, `@import url(...)`.**
   The plan's `(?!\s*[({"'])` only catches *direct* openers, but several CSS at-rules sit a
   word between the keyword and the brace. Added a second lookahead arm
   `\s*[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))` to cover them. The arm requires `(` or a *single* `{`
   (NOT `{{`) so legitimate Jinja constructs in the same template (e.g.
   `@var with {{ page | with_images }}`) aren't misclassified. `@namespace svg "..."` remains a
   residual (too easily confused with prose like `@name said "..."`); authors escape with
   `@@namespace`.

## Quick start (cold session)

Working directory: `/Users/lchoquel/repos/Pipelex/pipelex` (the `pipelex/` runtime repo inside the multi-repo workspace at `/Users/lchoquel/repos/Pipelex/`).

Read in this order:

1. This file (`TODOS.md`).
2. `wip/template-preprocessor-css-collision.md` — full design rationale and alternatives considered.
3. `pipelex/cogt/templating/template_preprocessor.py` — the file being changed (~100 lines).
4. `tests/unit/pipelex/cogt/templating/test_template_preprocessor.py` — the test file being extended.

Project conventions that apply (see `pipelex/CLAUDE.md` for the full list):

- One `TestClass` per test module. The existing class is `TestTemplatePreprocessor`. Add new test methods inside that same class — do **not** create a second class.
- Use pytest-mock, never `unittest.mock`. None of the new tests need mocking.
- Run `make agent-check` after code changes (lint + type check).
- Use `make agent-test` to validate, or for the targeted module: `.venv/bin/pytest -q tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`.

## Background (minimal)

The template preprocessor at `pipelex/cogt/templating/template_preprocessor.py` rewrites three sigils into Jinja2 before rendering: `@var` → `{{ var|tag("var") }}`, `@?var` → optional insertion, `$var` → `{{ var|format() }}`.

The current regexes are too permissive. CSS at-rules (`@media`, `@import`, `@keyframes`, …) inside `<style>` blocks of PipeCompose HTML templates get rewritten as variables and break rendering. Email addresses (`user@example.com`) and code constructs (Python decorators, bash subshells) have the same problem.

Fix has two parts:

1. **Heuristic regex tightening** — add a `(?<!\w)` lookbehind before each sigil (kills emails / word-adjacent `@`) and a `(?!\s*[({"'])` lookahead after the captured identifier (kills CSS at-rules and code constructs).
2. **Explicit escapes** — `@@` → literal `@`, `$$` → literal `$`. This is the documented opt-out for any residual case the heuristic can't predict.

## Current code (reference)

`pipelex/cogt/templating/template_preprocessor.py`, the three regex calls inside `preprocess_template`:

```python
# Replace @?variable patterns (optional insertion) - must come before @variable
new_template = re.sub(r"@\?(?![0-9])([a-zA-Z0-9_.]+)", replace_optional_at_variable, processed_template)
# ...
# Replace @variable patterns
new_template = re.sub(r"@(?![0-9])([a-zA-Z0-9_.]+)", replace_at_variable, processed_template)
# ...
# Replace $variable patterns
new_template = re.sub(r"\$(?![0-9])([a-zA-Z0-9_.]+)", replace_dollar_variable, processed_template)
```

The three `replace_*` helpers above them are unchanged by this work.

## Target code

New regex strings (Phase 2):

```python
r"(?<!\w)@\?(?![0-9])([a-zA-Z0-9_.]+)(?!\s*[({\"'])"
r"(?<!\w)@(?![0-9])([a-zA-Z0-9_.]+)(?!\s*[({\"'])"
r"(?<!\w)\$(?![0-9])([a-zA-Z0-9_.]+)(?!\s*[({\"'])"
```

Note: `(?<!\w)` is a fixed-width negative lookbehind (one char) — supported by `re`. The lookahead set `[({\"']` covers the four shapes CSS at-rules and code constructs take after the identifier; whitespace before them is allowed (`\s*`).

Escape implementation (Phase 3): use null-byte sentinels that templates cannot contain. Recommended scheme:

```python
_AT_ESCAPE_SENTINEL = "\x00PIPELEX_AT_ESCAPE\x00"
_DOLLAR_ESCAPE_SENTINEL = "\x00PIPELEX_DOLLAR_ESCAPE\x00"

def preprocess_template(template: str) -> str:
    processed_template = template.replace("@@", _AT_ESCAPE_SENTINEL).replace("$$", _DOLLAR_ESCAPE_SENTINEL)
    # ... existing three re.sub calls run on processed_template ...
    processed_template = processed_template.replace(_AT_ESCAPE_SENTINEL, "@").replace(_DOLLAR_ESCAPE_SENTINEL, "$")
    return processed_template
```

`str.replace("@@", …)` is non-overlapping left-to-right greedy, which gives the correct semantics:

- `@@var` → `<SENTINEL>var` → (no `@` left for the regex) → restored: `@var` (literal, no interpolation).
- `@@@var` → `<SENTINEL>@var` → regex matches `@var` → `<SENTINEL>{{ var|tag("var") }}` → restored: `@{{ var|tag("var") }}` (literal `@` + interpolated `var`).
- `@@@@var` → `<SENTINEL><SENTINEL>var` → no match → restored: `@@var` (two literal `@`s).

---

## Phase 1 — Extend tests with new expected behaviors (red)

All tests go inside the existing `TestTemplatePreprocessor` class in `tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`.

### 1.1 — CSS at-rule pass-through (heuristic lookahead)

Identifier followed by `\s*[({"']` must not be rewritten. Expected output equals the input (unchanged) for each:

- [x] `test_css_media_query_pass_through` — input `@media (max-width: 820px) { color: red; }`, output identical.
- [x] `test_css_supports_pass_through` — input `@supports (display: grid) { color: red; }`, output identical.
- [x] `test_css_import_string_pass_through` — input `@import "reset.css";`, output identical.
- [x] `test_css_import_url_pass_through` — input `@import url("reset.css");`, output identical.
- [x] `test_css_charset_pass_through` — input `@charset "UTF-8";`, output identical.
- [x] `test_css_namespace_pass_through` — input `@namespace svg "http://www.w3.org/2000/svg";`, output identical.
- [x] `test_css_keyframes_pass_through` — input `@keyframes spin { from { opacity: 0; } to { opacity: 1; } }`, output identical. (Both `@keyframes` and the `from`/`to` selectors are unaffected since they aren't preceded by a sigil.)
- [x] `test_css_page_pass_through` — input `@page { margin: 1in; }`, output identical.
- [x] `test_css_layer_named_pass_through` — input `@layer reset { color: red; }`, output identical.
- [x] `test_css_container_pass_through` — input `@container (width > 400px) { color: red; }`, output identical.
- [x] `test_css_font_face_pass_through` — input `@font-face { font-family: "X"; }`, output identical. Note: the identifier class today is `[a-zA-Z0-9_.]+`, which does not include `-`. So today `@font-face` already captures only `@font` and then encounters `-face` as literal — the lookahead `(?!\s*[({"'])` fires on `@font` because the next non-identifier character is `-`, not whitespace+brace. **Outcome under new regex**: `@font` captures, lookahead sees `-`, not whitespace+brace, so the lookahead does **not** fire — and `@font` would still be rewritten to `{{ font|tag("font") }}`. This is a residual case. **Decision for this test**: assert the heuristic does **not** save `@font-face` (input contains literal hyphen) and document `@@font-face` as the required author workaround. The test should assert the rewritten form so the limitation is visible:

  ```text
  input:    @font-face { font-family: "X"; }
  expected: {{ font|tag("font") }}-face { font-family: "X"; }
  ```

  Then add a companion `test_css_font_face_escaped_pass_through` that asserts `@@font-face { font-family: "X"; }` → `@font-face { font-family: "X"; }`.

- [x] `test_full_style_block_pass_through` — a realistic multi-rule `<style>` block (combining `@media`, normal selectors, and at least one nested ruleset) must pass through byte-for-byte. Use this fixture:

  ```html
  <style>
    .page { padding: 32px; }
    @media (max-width: 820px) {
      .page { padding: 24px; }
    }
    @supports (display: grid) {
      .grid { display: grid; }
    }
  </style>
  ```

### 1.2 — Email and word-adjacent `@` (heuristic lookbehind)

`@` preceded by a word character must not be treated as a sigil.

- [x] **Update** the existing `test_email_address_partially_processed` (lines 412–423 of the current test file): rename it to `test_email_address_pass_through` and replace its body to assert pass-through:

  ```text
  input:    Contact: someone@example.com
  expected: Contact: someone@example.com
  ```

- [x] `test_email_in_sentence_pass_through` — input `Contact us at hello@pipelex.com for help.`, output identical.
- [x] `test_word_adjacent_at_pass_through` — input `Send to noreply@anthropic.com immediately.`, output identical.

### 1.3 — `$` and `@` followed by code-like punctuation (regression guards)

These shapes already pass through today because the identifier class `[a-zA-Z0-9_.]+` does not match `(` or `{`. They're included as regression guards so the new lookahead doesn't accidentally regress them, and to lock in the documented behavior.

- [x] `test_jquery_call_pass_through` — input `$("body").addClass("x")`, output identical.
- [x] `test_bash_subshell_pass_through` — input `result=$(date +%s)`, output identical.
- [x] `test_dollar_brace_pass_through` — input `Use ${PATH} for the path.`, output identical.

### 1.4 — Escape sequences `@@` and `$$`

- [x] `test_double_at_escapes_to_literal_at`:
  ```text
  input:    @@media (max-width: 820px) { color: red; }
  expected: @media (max-width: 820px) { color: red; }
  ```

- [x] `test_double_at_makes_at_var_literal`:
  ```text
  input:    Use @@var here.
  expected: Use @var here.
  ```
  No `{{ … }}` in the output — the escape suppresses interpolation for that occurrence.

- [x] `test_double_dollar_escapes_to_literal_dollar`:
  ```text
  input:    Cost is $$10.
  expected: Cost is $10.
  ```

- [x] `test_double_dollar_makes_dollar_var_literal`:
  ```text
  input:    Use $$var here.
  expected: Use $var here.
  ```

- [x] `test_escape_does_not_consume_legit_variable`:
  ```text
  input:    @@media is literal, but @width is a variable.
  expected: @media is literal, but {{ width|tag("width") }} is a variable.
  ```

- [x] `test_triple_at_is_escape_plus_variable`:
  ```text
  input:    @@@var
  expected: @{{ var|tag("var") }}
  ```

- [x] `test_quadruple_at_is_two_escapes`:
  ```text
  input:    @@@@var
  expected: @@var
  ```

- [x] `test_escape_inside_style_block` — `<style>` block containing `@@font-face` (the residual heuristic case from §1.1) — verifies the recommended manual override:
  ```text
  input:    <style>@@font-face { font-family: "X"; }</style>
  expected: <style>@font-face { font-family: "X"; }</style>
  ```

### 1.5 — Confirm all legacy tests still apply

No test currently passing should regress. Skim each and confirm the new regexes don't break them. Quick reasoning for the non-obvious ones:

- `test_variable_in_parentheses` — `The value (@value) is important`: the `@` is preceded by `(` (non-word), lookbehind passes; the captured `value` is followed by `)` (not in lookahead set), so lookahead passes. ✓ Still rewrites.
- `test_email_address_partially_processed` — being replaced by `test_email_address_pass_through` (§1.2). Drop the old assertion.

All other legacy tests are unaffected by the lookbehind (sigil is preceded by space/newline/start-of-string) and unaffected by the lookahead (variables are followed by space/dot/punctuation, not `(` / `{` / `"` / `'`).

- [x] Re-run the full test module locally; legacy tests pass, new tests fail (red).

### 1.6 — Run the suite to confirm reds

- [x] `.venv/bin/pytest -q tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`
- [x] Confirm: all Phase 1 new tests fail with content mismatches (not import errors or syntax errors).

**Checkpoint A**: Phase 1 complete when all new tests are written, all legacy tests still pass, and the new tests fail for the documented reasons.

---

## Phase 2 — Implement the heuristic regex tightening (green for §1.1–§1.3)

Edit `pipelex/cogt/templating/template_preprocessor.py`.

- [x] Replace the three regex strings in `preprocess_template` with the new ones from the "Target code" section above. The replacement-function calls (`replace_optional_at_variable`, `replace_at_variable`, `replace_dollar_variable`) and their bodies stay unchanged.
- [x] Re-run the test module. Expected state:
  - §1.1 CSS tests pass (except `test_css_font_face_pass_through`, which asserts the documented residual hyphen limitation, also passes — see its expected output above).
  - §1.2 email tests pass.
  - §1.3 regression guards pass.
  - §1.4 escape tests still fail (escapes not implemented yet).
  - §1.5 legacy tests still pass.

---

## Phase 3 — Implement the `@@` / `$$` escapes (green for §1.4)

Still in `pipelex/cogt/templating/template_preprocessor.py`.

- [x] Add the two sentinel module-level constants from the "Target code" section (`_AT_ESCAPE_SENTINEL`, `_DOLLAR_ESCAPE_SENTINEL`).
- [x] In `preprocess_template`, before the existing regex substitutions, prepend:
  ```python
  processed_template = template.replace("@@", _AT_ESCAPE_SENTINEL).replace("$$", _DOLLAR_ESCAPE_SENTINEL)
  ```
  (Replaces the current `processed_template = template` line.)
- [x] After the three regex substitutions, before the `return`, append:
  ```python
  processed_template = processed_template.replace(_AT_ESCAPE_SENTINEL, "@").replace(_DOLLAR_ESCAPE_SENTINEL, "$")
  ```
- [x] Remove the `# TODO: allow escape patterns` comment (line 73 in the current file).
- [x] Re-run the test module. Expected: all Phase 1 tests now pass; legacy tests still pass.

---

## Phase 4 — Workspace sanity check

Look for any existing `.mthds` file in the workspace that would behave differently under the new rules.

- [x] From the workspace root (`/Users/lchoquel/repos/Pipelex/`), run:
  ```bash
  grep -rn '@[a-zA-Z_][a-zA-Z_0-9.]*[[:space:]]*[({"'\'']' --include="*.mthds" . | head -50
  grep -rn '@@\|\$\$' --include="*.mthds" . | head -50
  ```
- [x] For any hit, decide: accept (intended behavior change, the new heuristic does what the user wants), document, or flag back to the human.

---

## Phase 5 — Lint and full tests

- [x] `make agent-check` — Pyright, Ruff, Mypy, plxt all clean.
- [x] Targeted test run for impacted areas:
  ```bash
  .venv/bin/pytest -n auto \
    -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
    -o log_level=WARNING --tb=short -q \
    tests/unit/pipelex/cogt/ tests/unit/pipelex/pipe_operators/
  ```
- [x] `make agent-test` — full suite green.

---

## Phase 6 — Docs & changelog

- [x] `CHANGELOG.md`: add an entry under `## [Unreleased]` — `### Fixed` for the CSS collision, `### Added` for the `@@` / `$$` escapes. Cross-link `wip/template-preprocessor-css-collision.md`.
- [x] Update MTHDS authoring guidance / agent prompts to mention `@@` and `$$`. Likely targets:
  - `pipelex/builder/` (in-repo authoring docs and any prompts that describe template syntax).
  - `mthds-plugins/` build/edit skill prompts (workspace neighbor — only update if the user explicitly asks to touch it; per `CLAUDE.md` plugin files belong to the published marketplace plugin).

**Checkpoint B**: Phase 6 complete = ready to ship via `/release`.

---

## Out of scope / explicit non-goals

- No reserved CSS keyword list. The heuristic covers the realistic surface; the escape covers the rest.
- No HTML/`<style>`-aware parsing of templates.
- No syntax migration (`@{var}` etc.) — purely additive change.
- No changes to the `replace_*` helper functions or to the surrounding `tag(...)` / `format()` filters.
- No changes to the call sites of `preprocess_template` listed in the design doc — they all benefit transparently.

---

## Phase 7 — `$` sigil footgun fixes (open, HIGH PRIORITY)

### Why this phase

A live audit of the inline `$` sigil surfaced four word-adjacent substitution bugs plus a consecutive-dots edge case. Root causes: the `$` regex is missing the `(?<!\w)` lookbehind that the `@` candidate pattern carries, and its identifier class (`[a-zA-Z0-9_.]+`) is too permissive (allows leading digit, consecutive dots, trailing dot inside the captured identifier).

Concrete bugs (verified live against the current `preprocess_template`):

| Input | Current output | Verdict |
|---|---|---|
| `micro$oft is a company` | `micro{{ oft\|format() }} is a company` | bug — mid-word substitution |
| `user$host.com` | `user{{ host.com\|format() }}` | bug — mid-word substitution |
| `P@ssw$rd123` | `P@ssw{{ rd123\|format() }}` | bug — mid-word substitution |
| `a$b$c` | `a{{ b\|format() }}{{ c\|format() }}` | bug — back-to-back mid-word |
| `$name..` | `{{ name.\|format() }}.` | bug — emits invalid Jinja |

Regression guards (already correct under the current regex — must stay correct under the new one):

- `see $name.` → `see {{ name|format() }}.` (sentence terminator)
- `$user.name.first.` → `{{ user.name.first|format() }}.` (dotted access + terminator)
- `run $(whatever) please` → unchanged (code-shape opener)
- `price $10 today` → unchanged (dollar amount)
- `$foo(bar)` / `$foo "bar"` → unchanged (code-shape lookahead)
- `$$literal` → `$literal` (escape)

Posture: **silent pass-through** for word-adjacent `$` (do not raise like `@` does). The `$` arm is best-effort inline by design — it already silently passes `$10`, `$(`, `${`, `$foo "..."`. Raising on `micro$oft` would be a noisier contract than warranted, and inconsistent with the existing `$` posture.

### Target code

In `pipelex/cogt/templating/template_preprocessor.py`:

```python
_DOLLAR_SIGIL_PATTERN = re.compile(
    r"(?<!\w)(\$)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)(?![a-zA-Z0-9_])(?!\s*[({\"'])",
)

def _replace_dollar_sigil(match: Match[str]) -> str:
    variable: str = match.group(2)
    return f"{{{{ {variable}|format() }}}}"
```

Notes:

- `(?<!\w)` mirrors the `@` candidate pattern's left guard. Fixes all four word-adjacent bugs.
- The strict segmented identifier `[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*` rules out consecutive dots automatically and makes the prior `(?![0-9])` arm redundant — drop it.
- The trailing-dot kludge in `_replace_dollar_sigil` (`if variable.endswith("."): variable = variable[:-1]; ...`) goes away. Under the strict shape a trailing `.` cannot end the captured identifier, so it naturally sits outside the match as literal punctuation. `$name.` still renders as `{{ name|format() }}.` because the `.` is simply not part of the match.

### Phase 7.1 — TDD red

All new tests go inside the existing `TestTemplatePreprocessor` class in `tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`.

- [x] `test_word_adjacent_dollar_pass_through` — parametrized over the four mid-word bug shapes (`micro$oft is a company`, `user$host.com`, `P@ssw$rd123`, `a$b$c`); each passes through unchanged.

- [x] `test_dollar_consecutive_dots_pass_through` — `$name..` renders as `{{ name|format() }}..`. Both dots stay outside the match as literal punctuation.

- [x] Re-ran the targeted module — new tests went red first (content mismatches), all existing `$`-related tests still passed.

### Phase 7.2 — Implementation (green)

- [x] In `pipelex/cogt/templating/template_preprocessor.py`:
  - [x] Replaced `_DOLLAR_SIGIL_PATTERN` with the strict segmented shape and added the `(?<!\w)` lookbehind.
  - [x] Dropped the `(?![0-9])` lookahead arm (redundant under the new identifier shape).
  - [x] Simplified `_replace_dollar_sigil` to the one-liner version. The `trailing_dot` branch is gone (unreachable under the new regex).
  - [x] Updated the `# Inline \`$\` sigil` comment to describe the new contract.
- [x] Targeted module green: 121 passed.

### Phase 7.3 — Workspace sanity check

- [x] Ran the grep against `/Users/lchoquel/repos/Pipelex/`. Two hits in `mthds-ui/data/pipelines/pipeline_25/bundle.mthds` (lines 100 and 107), both of the shape `"...\n\n$classified.content"`. These are grep false positives — the `n` matched by `[[:alnum:]_]` belongs to the TOML `\n` escape; after TOML decoding the `$` is preceded by a real newline, so the new regex still rewrites correctly. No action.

### Phase 7.4 — Lint, tests, docs

- [x] `make agent-check` clean (Pyright, Ruff, Mypy, plxt).
- [x] Targeted cogt test run: 584 passed in 9.06s.
- [x] `make agent-test` — full suite green (5148 passed, 2 skipped, 3 xfailed). One pre-existing test (`test_template_field_accesses_extra_context`) had its template changed from `Q$quarter` to `, quarter $quarter` to match the new contract — see the "Deviations from Phase 7 plan" section near the top.
- [x] `CHANGELOG.md` updated under `[Unreleased]` `### Fixed`.

**Checkpoint C**: Phase 7 complete when the four word-adjacent-`$` tests and the consecutive-dots test are green, all legacy tests are green, `make agent-check` is clean, and `make agent-test` is green.

### STOP HERE — checkpoint before Phase 8

**Coding must stop after Phase 7 is delivered.** Do **not** start Phase 8 in the same session. After Checkpoint C is reached:

1. Update the top "Status" block to record Phase 7 as landed (with the date), mirroring the style of the existing "strict line-bounded `@` rule landed" block.
2. Note any open questions, deviations from this plan, or follow-up items in a brief retrospective near the top of this file (same style as the existing "Deviations from the original plan" section).
3. Hand back to the human for review.

Phase 8 (declared-inputs gating, formerly Phase 7) opens a new area of concern — function split, signature change, and call-site threading across 9 files — and should be picked up in a fresh session with this `TODOS.md` as the entry point.

---

## Phase 8 — Declared-inputs gating for the `@`-sigil validator (open)

### Why this phase

The strict line-bounded `@` rule (Phases 1–6) turned every inline `@<ident>` into a load-time error to catch typos like `Extract from @invoice_text.` The same rule, however, makes inline `@media`, `@import`, `@keyframes`, `@font-face`, `@deprecated`, `@Override` — the CSS at-rules and code decorators that coding agents emit by default when writing HTML/CSS in PipeCompose templates — fail at load time too. Authors must escape every occurrence with `@@`, which is unfamiliar and surprising for both humans and agents. Phase 8 narrows the validator's "is this a real typo?" question by gating on the pipe's declared `inputs:`: an inline `@<ident>` raises only when `<ident>` (root segment for dotted paths) is one of the pipe's declared inputs. Everything else passes through silently, restoring CSS-friendliness without resurrecting the prior heuristic regex residuals (the rewriter stays strict line-bounded — alone-on-line `@var` still rewrites; nothing inline ever rewrites). LSP / `plxt check` still surface real typos at edit time because the inputs list is known at load time; no runtime threading required.

### Target behavior

```text
pipe with inputs: { invoice_text: Text }:
✗ Extract from @invoice_text. Done.            → RAISES (invoice_text is declared → real typo)
✓ Extract from $invoice_text. Done.            → rewrites $invoice_text inline
✓ @invoice_text                                 → rewrites alone-on-line (unchanged)

pipe with inputs: { invoice_text: Text } (no `media` input):
✓ <style>@media (max-width: 820px) { ... }</style>   → pass-through (media is NOT declared)
✓ @media (max-width: 820px) { ... }                  → pass-through
✓ @deprecated def foo():                             → pass-through
✓ @Override                                          → pass-through (alone-on-line, but no Override input)

pipe with inputs: { Override: Text } (unusual but possible):
✗ @Override                                          → RAISES at the alone-on-line shape too? NO —
   alone-on-line still rewrites, because that's the rewriter's strict success case.
   The gate only applies to the INLINE-candidate validator path.
```

### Target code

**Signature change (`pipelex/cogt/templating/template_preprocessor.py`):**

```python
def preprocess_template(template: str, *, declared_inputs: set[str] | None = None) -> str: ...
```

When `declared_inputs is None`, the validator skips the inline-candidate check entirely (lenient pass-through). When a set is provided, the validator raises only when the candidate identifier's root segment is in the set.

**Function split (for clean runtime path):**

```python
def validate_template_sigils(template: str, declared_inputs: set[str]) -> None:
    """Raise TemplateSigilSyntaxError when an inline @-candidate matches a declared input."""

def rewrite_template_sigils(template: str) -> str:
    """Pure rewrite — applies @-line-bounded and $-inline substitutions. Does not validate."""

def preprocess_template(template: str, *, declared_inputs: set[str] | None = None) -> str:
    """Convenience entry: normalize, escape sentinels, optionally validate, rewrite, restore."""
```

`render_template` (runtime, in `template_rendering.py:17`) calls `rewrite_template_sigils` directly — by the time we reach render, the template has already been validated at load time, so the runtime call only needs the rewrite step. This avoids threading `declared_inputs` through the rendering path.

**Validator gating logic (`_validate_at_sigil_alone_on_line`):**

```python
def _validate_at_sigil_alone_on_line(template: str, declared_inputs: set[str] | None) -> None:
    if declared_inputs is None:
        return  # lenient: no inputs context, nothing to gate against
    for line_index, line in enumerate(template.split("\n"), start=1):
        if "@" not in line:
            continue
        if _AT_SIGIL_PATTERN.fullmatch(line):
            continue
        candidate = _AT_CANDIDATE_PATTERN.search(line)
        if candidate is None:
            continue
        identifier = candidate.group(2)
        root = get_root_from_dotted_path(identifier)
        if root not in declared_inputs:
            continue  # not a declared input → not a typo candidate → pass through
        # ... build current error message and raise ...
```

### Call sites to update

| File | Line(s) | Inputs source | Pass |
|---|---|---|---|
| `pipe_llm_blueprint.py` | 41, 58 | `self.inputs: dict[str, str] \| None` | `set(self.inputs or {})` |
| `pipe_compose_blueprint.py` | 106 | same | same |
| `pipe_search_blueprint.py` | 44 | same | same |
| `pipe_img_gen_blueprint.py` | 39 | same | same |
| `pipe_compose_factory.py` | 67 | `inputs: InputStuffSpecs` | `set(inputs.variables)` |
| `template_document_analyzer.py` | 48 | `input_specs: dict[str, str]` | `set(input_specs.keys())` |
| `template_image_analyzer.py` | 64, 163 | same | same |
| `construct_blueprint.py` | 249 | none (discovery function, not primary validation) | `None` |
| `template_blueprint.py` | 25, 37 | none (base blueprint, no inputs context) | `None` |
| `template_rendering.py` | 17 | runtime (already validated at load) | switch to `rewrite_template_sigils` |

### Phase 8.1 — TDD red: tests for the new behavior

All new tests go inside the existing `TestTemplatePreprocessor` class in `tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`.

- [ ] **Parametrized success (lenient when no matching input):** inline `@media (...)`, `@import "..."`, `@keyframes`, `@font-face`, `@deprecated def foo():`, `@Override` — each with `declared_inputs=set()` or `declared_inputs={"other_var"}` — pass through unchanged, no raise.
- [ ] **Parametrized success (lenient when `declared_inputs=None`):** same set of inputs as above, called with no kwarg — pass through unchanged.
- [ ] **Parametrized error (strict when match):** inline `@invoice_text.` with `declared_inputs={"invoice_text"}` raises with the existing migration hint shape (line N, sigil+identifier, `$var` hint, `@@` escape hint).
- [ ] **Dotted-access gating:** inline `@user.profile.bio` with `declared_inputs={"user"}` raises; same template with `declared_inputs={"profile"}` passes through (gate is on root segment).
- [ ] **Alone-on-line rewrites regardless of inputs:** `@invoice_text` alone on its line still rewrites whether or not `invoice_text` is in `declared_inputs` — the rewriter is strict and inputs-agnostic.
- [ ] **Update CSS at-rule tests:** the existing `test_css_at_rule_raises_under_strict_rule` (parametrized) splits into two cases: `declared_inputs=set()` → pass-through, `declared_inputs={<at-rule keyword>}` → still raises. Keep the `@@`-escape companion tests as documented opt-outs (escape still works under any gating regime).

Blueprint integration tests (`tests/unit/pipelex/pipe_operators/pipe_llm/test_pipe_llm_blueprint.py`):

- [ ] PipeLLM with `inputs: {"invoice_text": "Text"}` and `prompt = "Extract from @invoice_text."` — pydantic raises `ValidationError` wrapping `TemplateSigilSyntaxError`.
- [ ] Same prompt with no `inputs` declared — loads cleanly (pass-through).
- [ ] PipeLLM with `inputs: {"page": "Page"}` and `prompt = "<style>@media (max-width: 820px) { ... }</style>\n@page"` — loads cleanly (no `media` input → CSS passes through; `@page` alone on line → rewrites).
- [ ] Same prompt with `inputs: {"page": "Page", "media": "Text"}` — raises on `@media` (declared input now matches).

Run target:

```bash
.venv/bin/pytest -q tests/unit/pipelex/cogt/templating/test_template_preprocessor.py
.venv/bin/pytest -q tests/unit/pipelex/pipe_operators/pipe_llm/test_pipe_llm_blueprint.py
```

Expected state after Phase 8.1: new tests fail (red), all existing tests still pass (the lenient-when-`None` default keeps current call sites' behavior intact for legacy tests that don't pass inputs).

### Phase 8.2 — Implementation (green)

- [ ] In `pipelex/cogt/templating/template_preprocessor.py`:
  - [ ] Add `get_root_from_dotted_path` import (or inline equivalent).
  - [ ] Change `_validate_at_sigil_alone_on_line` signature to accept `declared_inputs: set[str] | None`; gate per the logic in §Target code.
  - [ ] Split `preprocess_template` into `validate_template_sigils` (just the validator wrapper) and `rewrite_template_sigils` (escape → normalize → substitute → restore, no validation). Keep `preprocess_template` as the convenience entry that runs both.
  - [ ] Update the module docstring to describe the gating behavior.
- [ ] Thread `declared_inputs` through the 7 call sites that have inputs context (see table). Pass `None` from the 2 call sites that don't.
- [ ] In `pipelex/cogt/templating/template_rendering.py:17`: switch from `preprocess_template(template)` to `rewrite_template_sigils(template)` — no need to re-validate at render time.

Run target same as Phase 8.1. Expected: all Phase 8.1 tests green, all legacy tests still green.

### Phase 8.3 — Workspace sanity check

- [ ] Re-run the workspace `.mthds` grep from Phase 4 of the line-bounded plan (`wip/template-preprocessor-line-bounded-at.md`):

  ```bash
  # Inline @-sigil candidates — anything @var that's not on its own line:
  grep -rEn '(^|[^[:alnum:]_])@\??[a-zA-Z_][a-zA-Z0-9_.]*' --include="*.mthds" . | \
    grep -vE '^[^:]+:[0-9]+:[[:space:]]*@\??[a-zA-Z_][a-zA-Z0-9_.]*[[:space:]]*$' | \
    head -50
  ```

- [ ] For each hit: confirm it now loads cleanly under the new gating (the identifier should NOT be a declared input — that's the whole point). If any hit IS a declared input, it's a genuine typo that should keep raising — verify the error fires.
- [ ] Confirm any `@@`-escape workarounds added in Phase 4 are still functionally correct (they should be; `@@` still works) but are no longer strictly necessary for the CSS cases. Note them in a "follow-up cleanup" list — don't strip them in this PR.

### Phase 8.4 — Lint, tests, docs

- [ ] `make agent-check` clean (Pyright, Ruff, Mypy, plxt).
- [ ] Targeted test run (per `tests/CLAUDE.md` mapping for `pipelex/cogt/` + `pipelex/pipe_operators/`):

  ```bash
  .venv/bin/pytest -n auto \
    -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
    -o log_level=WARNING --tb=short -q \
    tests/unit/pipelex/cogt/ tests/unit/pipelex/pipe_operators/ tests/integration/pipelex/pipes/
  ```

- [ ] `make agent-test` — full suite green.
- [ ] `CHANGELOG.md` under `[Unreleased]` `### Changed`: "Template preprocessor: relaxed the strict `@`-line rule. Inline `@<ident>` now raises only when `<ident>` is a declared input of the surrounding pipe; other inline `@` candidates (CSS at-rules, code decorators) pass through silently. The line-bounded rewriter is unchanged."
- [ ] MTHDS authoring guidance (`pipelex/builder/` prompts and any in-repo docs that currently steer authors toward `@@`-escapes for CSS): drop the CSS-escape advice, keep the `@@`/`$$` mention as the literal-character opt-out.

**Checkpoint D**: Phase 8 complete when CSS at-rules in PipeCompose HTML templates load without `@@` escapes (where they don't collide with declared inputs), AND typo-shape inline `@<declared>` still raises with the migration hint at load time.

### Open decisions for Phase 8

These are small enough to default and proceed; flag objections before locking in.

1. **`declared_inputs=None` default = lenient (no raise).** Reasoning: callers without inputs context (the base `TemplateBlueprint`, the `ConstructBlueprint` discovery function) can't make the gate decision; the strict behavior is hostile in those contexts. Alternative: default-strict — every call site that doesn't pass inputs gets the current Phase 1–6 behavior. Less friendly to the discovery / runtime paths.
2. **Gate on root segment of dotted identifier.** `@user.profile.bio` is gated on `user`. Matches how Pipelex's input resolution and `detect_jinja2_required_variables` treat dotted paths.
3. **Validator does NOT consult Jinja2-detected variables.** It only consults `declared_inputs`. Reasoning: by the time we validate, we haven't rewritten yet, so Jinja2 can't see `@var` as a variable; conversely, if the author wrote `{{ media }}` directly in Jinja, that's a separate concern. Keep the gate narrow and explicit.
4. **Reserved-name handling unchanged.** Internal vars (`preliminary_text`, `place_holder`, `_-prefixed`) are still filtered downstream in `pipe_llm_blueprint.py:78`. The validator doesn't need to know about them — they're not realistic typo candidates inline.

### Out of scope for Phase 8

- **Auto-cleanup of existing `@@`-escapes in workspace `.mthds` files.** Phase 4 of the line-bounded plan added some; they keep working under the new gating. A follow-up PR can strip the ones that are no longer needed.
- **Runtime gating on actual working-memory contents.** The proposal we considered first (check the candidate against the runtime context) would catch typos that aren't declared as inputs. Rejected because it moves validation from load time to render time and breaks LSP / `plxt check` integration. The declared-inputs gate is the load-time approximation.
- **Heuristic shape detection inside the validator.** No `(?!\s*[({"'])` lookahead — the declared-inputs gate fully replaces shape-based heuristics for the `@` arm.
- **Changes to the `$` sigil contract.** `$` is unchanged.
