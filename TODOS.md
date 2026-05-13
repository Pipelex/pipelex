# Template preprocessor — sigil collision fix (TDD plan)

## Status: Complete (2026-05-13)

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
