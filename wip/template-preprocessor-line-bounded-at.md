# Template preprocessor — strict line-bounded `@` sigil (TDD plan)

## Status: Open. Supersedes `wip/template-preprocessor-residual-edge-cases.md`. Adapts from the current state of `fix/Template-preprocessor-footguns` (the CSS / email / escape work shipped on this branch — that work stays; this plan strips the now-unnecessary heuristics on `@` and replaces them with a strict line-bounded rule + a load-time validator).

## Why this design (one paragraph)

`@var` produces `<var>...</var>` (a block-shaped envelope via the `tag()` filter). `$var` produces inline `format()` output. The existing collisions (`@media`, `@import`, `@font-face`, `user@example.com`, `@status. Amount (USD).`, `@var {{ jinja }}`, …) are all symptoms of letting `@` do inline duty when its rendered shape is fundamentally block-level. Restricting `@` to "alone on its own line" aligns syntax with semantics, makes the regex trivial, and turns silent pass-through (the current footgun) into a loud, actionable error.

## Quick start (cold session)

Working directory: `/Users/lchoquel/repos/Pipelex/pipelex` (the `pipelex/` runtime repo inside the multi-repo workspace at `/Users/lchoquel/repos/Pipelex/`).

Read in this order:

1. This file.
2. `pipelex/cogt/templating/template_preprocessor.py` — current implementation (~100 lines, post-CSS-collision fix).
3. `pipelex/cogt/templating/template_blueprint.py` — where `TemplateBlueprint` runs its pydantic `validate_template` hook; the new sigil validator hooks in alongside the existing Jinja2 syntax check.
4. `pipelex/pipe_operators/llm/pipe_llm_blueprint.py:33-62` — example of the existing `preprocess_template + detect_jinja2_required_variables` pattern in a blueprint's `validate_inputs`; the new exception flows through this surface.
5. `tests/unit/pipelex/cogt/templating/test_template_preprocessor.py` — single `TestTemplatePreprocessor` class with ~80 tests; many existing tests use inline `@var` and will be rewritten or repurposed.
6. `wip/template-preprocessor-residual-edge-cases.md` — obsolete under the new rule for the `@` cases; the `$` residuals listed there are explicit non-goals here (see §Out of scope).

Project conventions (from `pipelex/CLAUDE.md`):

- One `TestClass` per test module. Keep everything inside `TestTemplatePreprocessor`.
- pytest-mock, never `unittest.mock`.
- `make agent-check` after code changes (Ruff + pyright + mypy + plxt).
- Targeted test: `.venv/bin/pytest -q tests/unit/pipelex/cogt/templating/test_template_preprocessor.py`.
- Full impacted run: see the source-to-test mapping in `pipelex/tests/CLAUDE.md` — `pipelex/cogt/` touches `tests/unit/pipelex/cogt/ tests/integration/pipelex/cogt/`, and the `pipe_operators` blueprints touch `tests/unit/pipelex/pipe_operators/ tests/integration/pipelex/pipes/`.

## Target behavior

### `@` and `@?` — line-bounded only

An `@var` or `@?var` sigil is recognized **only** when it is the entire content of a line (leading/trailing whitespace allowed). Anything else containing a candidate sigil shape is an error at load time.

```text
✓ @invoice_text            → {{ invoice_text|tag("invoice_text") }}
✓     @?notes              → {% if notes %}{{ notes|tag("notes") }}{% endif %}
✓ @user.profile.bio        → {{ user.profile.bio|tag("user.profile.bio") }}

✗ Extract from @invoice_text.    → ERROR: inline @invoice_text (line 1). Use $invoice_text for inline, or move @invoice_text onto its own line.
✗ Hello @name!                   → ERROR: inline @name (line 1). …
✗ @var $other_var                → ERROR: @var is not alone on its line (line 1). …
✗ The value (@value) is …        → ERROR: inline @value (line 1). …
```

Identifier shape (unchanged in spirit, tightened slightly): `[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*`. First char must be a letter or underscore (not a digit); dotted access supported; no trailing dot in the capture.

### `$` — unchanged

`$var` keeps its current inline behavior, lookaheads, and `(?![0-9])` digit guard. Known `$` residuals (`$name {{ jinja }}` not rewriting, `$user. info()` not rewriting) are explicit non-goals here — see §Out of scope.

### `@@` and `$$` escapes — unchanged

`@@` → literal `@`, `$$` → literal `$`. The sentinel substitution runs before validation and before the regex pass, so escaped occurrences never reach the validator and never trip the strict rule. Authors with literal CSS at-rules (`@@media`, `@@font-face`) or literal dollar amounts (`$$10`) escape with the doubled sigil.

### Candidate sigil definition (the validator's scope)

The validator does **not** flag every `@` in the template. It flags only "candidate sigils" — shapes that look like a malformed `@`/`@?` interpolation:

- `@` (or `@?`) **not** preceded by a word character (post-`@@`-escape).
- Followed immediately (no whitespace) by an identifier-shape capture.
- On a line that is not solely that sigil + optional whitespace.

This means:

- `someone@example.com` — `@` preceded by `e` (word char) → not a candidate → silently passes through. (Matches the current lookbehind protection.)
- `@Override`, `@deprecated` in a code block at line start — IS a candidate (line-start `@` + identifier) → error if not alone. Authors escape with `@@Override` if they want literal.
- `@media (max-width: 820px) {` — IS a candidate → error if not alone. Authors escape with `@@media`.
- `@ media` (space after `@`) — not a candidate (no identifier immediately after `@`) → silently passes through.

The validator's error message must include:

- The line number (1-based).
- The offending span (the `@` and the identifier).
- A concrete migration hint: "Did you mean `$var` (inline) or move `@var` onto its own line? Escape with `@@` for a literal `@`."

## Target code

### Preprocessor (`pipelex/cogt/templating/template_preprocessor.py`)

Replace `_SIGIL_PATTERN` (the unified alternation) with two patterns:

```python
# Line-bounded @ / @? sigil — must be alone on its own line.
_AT_SIGIL_PATTERN = re.compile(
    r"^[ \t]*(@\??)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)[ \t]*$",
    re.MULTILINE,
)

# Inline $ sigil — current heuristics, unchanged in scope (digit guard + identifier-class boundary
# + code/CSS-shape lookahead). The `@` arm is gone from this pattern entirely.
_DOLLAR_SIGIL_PATTERN = re.compile(
    r"(\$)(?![0-9])([a-zA-Z0-9_.]+)(?![a-zA-Z0-9_.])(?!\s*[({\"'])",
)

# Candidate-sigil detector for the validator: any unescaped @ at non-word boundary, followed by
# an identifier shape. Used only to surface errors; never substitutes.
_AT_CANDIDATE_PATTERN = re.compile(
    r"(?<!\w)(@\??)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)",
)
```

`_replace_sigil` collapses to two arms (no more `_Sigil.AT` vs `_Sigil.AT_OPTIONAL` ambiguity in shared code) but the `_Sigil` enum stays — used by both `@` and `$` callbacks.

Trailing-dot handling stays in the `$` callback (where it still matters for prose like `$amount.`). It can be dropped from the `@` callback because the line-bounded regex cannot capture a trailing dot — the identifier class no longer includes `.` at segment boundaries.

`preprocess_template` flow:

```python
def preprocess_template(template: str) -> str:
    # 1. Escape sentinels first — @@ and $$ disappear before validation and substitution.
    processed = template.replace("@@", _AT_ESCAPE_SENTINEL).replace("$$", _DOLLAR_ESCAPE_SENTINEL)

    # 2. Validate: any candidate @-sigil that is not alone on its line is an error.
    _validate_at_sigil_alone_on_line(processed)

    # 3. Substitute: @ line-bounded first, then $ inline. (Two passes are safe — @ output occupies
    #    whole lines, so the $ pattern's lookahead never sees @-introduced braces.)
    processed = _AT_SIGIL_PATTERN.sub(_replace_at_sigil, processed)
    processed = _DOLLAR_SIGIL_PATTERN.sub(_replace_dollar_sigil, processed)

    # 4. Restore sentinels.
    return processed.replace(_AT_ESCAPE_SENTINEL, "@").replace(_DOLLAR_ESCAPE_SENTINEL, "$")
```

### New exception (`pipelex/cogt/templating/template_errors.py`, new module)

```python
from pipelex.system.exceptions import ToolError


class TemplateSigilSyntaxError(ToolError):
    """Raised when a template contains a sigil shape that violates the strict @-line rule.

    The error message includes the line number, the offending span, and a migration hint.
    """
```

Placed alongside the other templating utilities, not under `tools/jinja2/`, because this is about Pipelex sigils, not about Jinja2 itself. Mirrors the `Jinja2TemplateSyntaxError` pattern in shape and ergonomics.

### Validator (`pipelex/cogt/templating/template_preprocessor.py`)

```python
def _validate_at_sigil_alone_on_line(template: str) -> None:
    """Scan for candidate `@` / `@?` sigils that are not alone on their own line and raise.

    Inputs are post-`@@`-escape (so `@@` cases are already replaced by sentinels and don't trip
    the check). Word-adjacent `@` (emails, prose hashtags) is excluded by the `(?<!\w)`
    lookbehind on the candidate pattern.
    """
    for line_index, line in enumerate(template.split("\n"), start=1):
        if "@" not in line:
            continue
        if _AT_SIGIL_PATTERN.fullmatch(line):
            continue
        candidate = _AT_CANDIDATE_PATTERN.search(line)
        if candidate is None:
            continue
        sigil = candidate.group(1)
        identifier = candidate.group(2)
        msg = (
            f"Inline `{sigil}{identifier}` is not allowed on line {line_index}: "
            f"the `{sigil}` sigil produces tag-wrapped block content and must appear alone on "
            f"its own line. "
            f"Did you mean `${identifier}` (inline value), or move `{sigil}{identifier}` onto "
            f"its own line? "
            f"Escape with `@@` if you intend a literal `@`."
        )
        raise TemplateSigilSyntaxError(msg)
```

Loop semantics: report the first offending line, not all of them. Authors fix one, re-run, fix the next — cheaper to read than a bulk dump. (Worth confirming with the user before locking — see §Open decisions.)

### Blueprint integration

The existing `validate_inputs` methods in each pipe blueprint already call `preprocess_template(self.prompt)`. They need to catch `TemplateSigilSyntaxError` and re-raise with pipe-specific context, mirroring how they handle `Jinja2DetectVariablesError`:

```python
try:
    preprocessed_template = preprocess_template(self.prompt)
except TemplateSigilSyntaxError as exc:
    msg = f"Template sigil error in PipeLLM prompt: {exc}"
    raise ValueError(msg) from exc
```

Same surface in `pipe_compose_blueprint.py`, `pipe_compose_factory.py`, `pipe_img_gen_blueprint.py`, `pipe_search_blueprint.py`, `pipe_compose/construct_blueprint.py`. And `TemplateBlueprint.validate_template` gets the same treatment.

The `ValueError` wrapping is what pydantic surfaces in its validation error report — same path as the existing template-parsing errors. LSP / `plxt check` already render these cleanly.

## Test migration framing

Many tests in `test_template_preprocessor.py` exercise inline `@var` shapes that were valid under the heuristic and are invalid under the strict rule. They split into three buckets:

1. **Generic-variable tests that just happen to use `@`.** Example: `test_variable_followed_by_comma` (`"Values: @first, @second, and @third"`). The point is "a sigil followed by punctuation works"; switching to `$first, $second` keeps the intent and matches the actual semantic (inline value). Rewrite the input to use `$`.

2. **Tests that specifically validated the old `@`-can-be-inline contract.** Example: `test_at_variable_with_trailing_dot`, `test_back_to_back_at_variables`, `test_variable_in_parentheses`. Convert to `pytest.raises(TemplateSigilSyntaxError)` (or via a parametrized error-shape test) — these are the new contract tests.

3. **Tests of `$` behavior, escape behavior, or `@` alone on a line.** Untouched. Example: `test_dollar_amounts_not_processed`, `test_double_at_escapes_to_literal_at`, `test_at_variable_pattern` (already uses `@expense\n@invoices`), `test_optional_at_variable_pattern` (uses `@?optional_field` on its own line), `test_variable_alone_on_line`, all CSS pass-through tests.

The residual-rewrite tests (`test_css_namespace_residual_rewritten`, `test_css_font_face_residual_rewritten`, `test_css_dash_residual_rewritten`) get deleted — the residuals don't exist under the new rule. The companion escape tests (`test_css_namespace_escaped_pass_through`, `test_css_font_face_escaped_pass_through`, `test_css_dash_residual_escape_workaround`) stay — `@@` still works.

CSS pass-through tests (`test_css_media_query_pass_through`, `test_css_supports_pass_through`, etc.) need a behavior change: today they assert the input passes through unchanged. Under the new rule, they assert the input **raises** `TemplateSigilSyntaxError`. The intent ("CSS at-rules are not sigils") is the same; the enforcement is now strict, not heuristic.

Email pass-through tests (`test_email_address_pass_through`, `test_email_in_sentence_pass_through`, `test_word_adjacent_at_pass_through`) stay as pass-through — emails have a word char before `@`, so they're not candidate sigils and don't trip the validator.

## Phases

### Phase 1 — Replace the residuals doc and lock the plan

- [x] Write this plan doc (`wip/template-preprocessor-line-bounded-at.md`).
- [ ] Update `TODOS.md` so the next person opening the repo sees a single pointer to this file. The "Status: Complete" header from the prior CSS-collision work stays as history; a new "Next phase" section at the top points here.
- [ ] Mark `wip/template-preprocessor-residual-edge-cases.md` as superseded (one-line note at the top pointing to this file). Don't delete it yet — it's still useful as history for the `$` residuals, which remain open.

### Phase 2 — TDD red: new tests for the strict contract

All new tests inside `TestTemplatePreprocessor`. Don't open a second class.

- [x] **Strict-line success cases** (parametrized, all alone-on-line forms): `@var`, `@?var`, `@user.profile.bio`, `@_private_var`, `    @indented_var`, `@var\t` (trailing tab). Each rewrites correctly.
- [x] **Strict-line error cases** (parametrized, all raising `TemplateSigilSyntaxError` with the expected message components — line number, offending span, migration hint):
  - Inline mid-sentence: `Extract from @invoice_text. Done.`
  - Inline trailing punctuation: `@var.`, `@var,`, `@var!`, `@var?`, `@var;`, `@var:`
  - Inline parenthetical: `(@var)`, `[@var]`
  - Multiple sigils per line: `@a @b`, `@a $b`, `$b @a`
  - Word-adjacent (but not email — preceded by space): `Word @var`, `@var Word`
  - CSS at-rules: `@media (max-width: 820px) {`, `@font-face { font-family: "X"; }`, `@import url("reset.css");`, `@keyframes spin { from {…} }`
  - Code constructs: `@Override`, `@deprecated def foo():`
- [x] **Word-adjacent silent pass-through** (parametrized): `someone@example.com`, `hello@pipelex.com`, `Send to noreply@anthropic.com immediately.`, `prefix@suffix`. Each passes through unchanged with no error.
- [x] **Escape cases unchanged**: existing `test_double_at_*`, `test_quadruple_at_is_two_escapes`, `test_escape_does_not_consume_legit_variable`, `test_escape_inside_style_block`. All still green. (Note: `test_triple_at_is_escape_plus_variable` survives Phase 2 untouched but is destined for Phase 3 conversion to `pytest.raises` — `@@@var` post-sentinel resolves to `<sentinel>@var`, which is no longer alone-on-line under the strict rule.)
- [x] **Full style block now raises**: rewrote `test_full_style_block_pass_through` → `test_full_style_block_raises_under_strict_rule` (expects `TemplateSigilSyntaxError`) and added companion `test_full_style_block_escaped_pass_through` using `@@media` / `@@supports`.
- [x] **Blueprint integration tests**: added three tests in `tests/unit/pipelex/pipe_operators/pipe_llm/test_pipe_llm_blueprint.py` (note: actual dir is `pipe_llm/`, not `llm/`) — prompt-field, system_prompt-field, and multi-line line-number variants — each asserting pydantic surfaces `@var`, `$var` (migration), `@@` (escape), and `line N`.
- [x] Run the suite. Confirmed: 23 red in preprocessor + 3 red in blueprint = 26 expected failures; 93 + 11 = 104 untouched tests still green.

**Checkpoint A — DONE.** Phase 2 left the repo in a clean red state. Notes for whoever picks up Phase 3+:

1. **Whitespace preservation deviation from §Target code.** The Phase 2 success-case tests assert that leading and trailing whitespace on indented alone-on-line forms is **preserved** (`    @indented_var` → `    {{ indented_var|tag("indented_var") }}`, `@var\t` → `{{ var|tag("var") }}\t`). The plan's literal regex `r"^[ \t]*(@\??)(ident)[ \t]*$"` would consume the whitespace into the match and the `re.sub` callback would drop it. Phase 4 must use capture groups for leading/trailing whitespace and re-emit them in `_replace_at_sigil`, e.g.:

    ```python
    _AT_SIGIL_PATTERN = re.compile(
        r"^([ \t]*)(@\??)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)([ \t]*)$",
        re.MULTILINE,
    )
    # callback: f"{leading}{rendered}{trailing}"
    ```

    This decision keeps templates embedded in indented YAML/TOML blocks rendering in the same column as the surrounding text. If you'd rather have whitespace eaten, flip the tests in `test_strict_line_at_sigil_success` (cases `indented_at_var`, `trailing_tab_at_var`, `tab_indented_optional_at_var`, `indented_at_var_in_block`) and drop the capture groups.

2. **Skeleton-only `template_errors.py`.** `TemplateSigilSyntaxError(ToolError)` exists with no behavior. Phase 4 adds `_validate_at_sigil_alone_on_line` in `template_preprocessor.py` and the validator is what makes the red tests go green.

3. **Phase 1 housekeeping still open.** Phase 1's checklist had two unticked items (TODOS.md pointer; superseded note on `wip/template-preprocessor-residual-edge-cases.md`). Those are still open. Pick them up before Phase 3 or fold them into Phase 6's docs work.

4. **Targeted test commands for resuming work.**

    ```bash
    .venv/bin/pytest -q tests/unit/pipelex/cogt/templating/test_template_preprocessor.py
    .venv/bin/pytest -q tests/unit/pipelex/pipe_operators/pipe_llm/test_pipe_llm_blueprint.py
    ```

    Expected at start of Phase 3: 23 red + 3 red. After Phase 3 rewrite: many more red (legacy inline-`@` tests converted to `pytest.raises`). After Phase 4 implementation: all green.

### Phase 3 — TDD red: rewrite the inline-`@` tests

This is the meaty migration. Each test gets sorted into one of the three buckets in §Test migration framing.

- [ ] Walk every test in `test_template_preprocessor.py` (and `test_template_pipeline.py`). For each that uses inline `@var`:
  - Bucket 1 (generic, switch to `$`): rewrite input from `@var` to `$var`, rewrite expected from `{{ var|tag(...) }}` to `{{ var|format() }}`.
  - Bucket 2 (specifically asserts `@` inline): convert to `pytest.raises(TemplateSigilSyntaxError)` (or fold into the parametrized error-cases test added in Phase 2 and delete the standalone test).
  - Bucket 3 (already alone-on-line, or about `$`/escapes): no change.
- [ ] Delete `test_css_*_residual_rewritten` and `test_css_dash_residual_rewritten` — residuals don't exist under the new rule.
- [ ] Rewrite the CSS pass-through tests (`test_css_media_query_pass_through` etc.) to expect `TemplateSigilSyntaxError`. Keep the escape companions as pass-through assertions.
- [ ] Run the suite. State: even more red.

### Phase 4 — Implementation (green)

- [ ] Add `pipelex/cogt/templating/template_errors.py` with `TemplateSigilSyntaxError(ToolError)`.
- [ ] In `template_preprocessor.py`:
  - [ ] Replace `_SIGIL_PATTERN` with `_AT_SIGIL_PATTERN`, `_DOLLAR_SIGIL_PATTERN`, `_AT_CANDIDATE_PATTERN` (see §Target code).
  - [ ] Split `_replace_sigil` into `_replace_at_sigil` and `_replace_dollar_sigil`. Drop trailing-dot handling from the `@` callback; keep it in the `$` callback.
  - [ ] Add `_validate_at_sigil_alone_on_line` (see §Target code).
  - [ ] Rewrite `preprocess_template` to: escape → validate → AT pass → DOLLAR pass → restore.
- [ ] Update the docstring at the top of `template_preprocessor.py` to describe the strict rule and the candidate-sigil validator. Strip the long comment block describing the heuristic alternatives — it's no longer applicable.
- [ ] In each pipe blueprint that calls `preprocess_template` (`pipe_llm_blueprint.py`, `pipe_compose_blueprint.py`, `pipe_compose_factory.py`, `pipe_img_gen_blueprint.py`, `pipe_search_blueprint.py`, `compose/construct_blueprint.py`, `shared/template_image_analyzer.py`, `template_document_analyzer.py`): wrap the `preprocess_template` call in `try/except TemplateSigilSyntaxError` and re-raise as `ValueError` with pipe-specific context. Mirror the existing `Jinja2DetectVariablesError` pattern.
- [ ] Update `TemplateBlueprint.validate_template` to call `preprocess_template` and catch the new exception.
- [ ] Run the suite. Expected: all Phase 2 + Phase 3 tests now green; legacy tests still green.

**Checkpoint B**: Phase 4 done when `make agent-check` is clean and the targeted test run (`tests/unit/pipelex/cogt/ tests/unit/pipelex/pipe_operators/`) is green.

### Phase 5 — Workspace sanity check

Look for any `.mthds` file in the workspace that would now fail validation.

- [ ] From the workspace root (`/Users/lchoquel/repos/Pipelex/`), run:

  ```bash
  # Inline @-sigil candidates — anything @var that's not on its own line:
  grep -rEn '(^|[^[:alnum:]_])@\??[a-zA-Z_][a-zA-Z0-9_.]*' --include="*.mthds" . | \
    grep -vE '^[^:]+:[0-9]+:[[:space:]]*@\??[a-zA-Z_][a-zA-Z0-9_.]*[[:space:]]*$' | \
    head -50

  # Existing @@ / $$ usages (already correct):
  grep -rEn '@@|\$\$' --include="*.mthds" . | head -50
  ```
- [ ] For each hit, decide: migrate to `$var` (inline), reshape onto its own line, or escape with `@@` (literal `@`). Document the migration list in this file under a new "Workspace migration" section.
- [ ] If hits exist in `methods/`, `pipelex-cookbook/`, `test-bed/`, or fixture-shipped `.mthds`, write the migrations as part of this branch. If hits exist in `mthds-plugins/` (the marketplace plugin), STOP and flag to the user — that repo isn't ours to touch from here.

### Phase 6 — Authoring docs + CHANGELOG

- [ ] Update `CHANGELOG.md` under `[Unreleased]`:
  - Replace the prior `### Fixed` entry for CSS collision with a `### Changed` (breaking) entry describing the new strict rule.
  - Keep the `### Added` entry for `@@` / `$$` escapes — still accurate.
  - Add a short migration note: "Inline `@var` is now a load-time error. Use `$var` for inline values, keep `@var` alone on its own line, or escape with `@@` for a literal `@`."
- [ ] Update MTHDS authoring guidance to reflect the strict rule. Likely targets:
  - `pipelex/builder/` prompts and any in-repo authoring docs.
  - The MTHDS spec / `mthds-language-tutorial.md` (in the `mthds/` workspace repo) — **only if** the user explicitly opts in to a cross-repo doc change. Per the workspace rule, default is to leave the spec doc edits to a separate PR.
- [ ] Update any IDE-side documentation (vscode-pipelex sees this via plxt — if plxt's diagnostics output changes, note it).

### Phase 7 — Lint + full tests

- [ ] `make agent-check` — Pyright, Ruff, Mypy, plxt all clean.
- [ ] Targeted: `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/cogt/ tests/unit/pipelex/pipe_operators/ tests/integration/pipelex/pipes/`
- [ ] `make agent-test` — full suite green.

**Checkpoint C**: Ready to ship via `/release`.

## Open decisions to confirm before Phase 4

These are small enough that I'll make a default call and proceed; flag any objections before locking in.

1. **Validator reports first error, not all errors.** Default: yes (cheaper to read; matches Jinja2 syntax error behavior). Alternative: accumulate all sigil errors per template and raise once with a list — only worth it if templates regularly have many errors at once, which is unlikely.
2. **Indented `@var` allowed.** Default: yes — `^[ \t]*@var[ \t]*$` permits leading indentation. Useful for templates embedded in YAML strings or indented blocks. Trailing whitespace too (forgiving on author trailing spaces). Alternative: zero indentation only — stricter but probably too aggressive for indented YAML / TOML embeddings.
3. **Trailing-dot handling stays on `$`.** Default: yes — `$amount.` → `{{ amount|format() }}.` still works (existing behavior). The `@` callback drops the trailing-dot logic because the line-bounded regex can't capture one.
4. **No accumulation across blueprints.** Default: each blueprint's `validate_inputs` raises the first sigil error it hits, even if the same .mthds file has more in other prompts (system_prompt, sub-templates). Pydantic's accumulation handles cross-field collection at the model level — the per-call raise is fine.

## Out of scope / explicit non-goals

- **`$` residuals from `wip/template-preprocessor-residual-edge-cases.md`.** `$name {{ jinja }}` not rewriting and `$user. info()` not rewriting are real but separate. They affect `$`, which keeps its inline contract. If we tackle them, it's a follow-up PR.
- **Reserved-keyword list for CSS at-rules.** Not needed — the strict rule means CSS pass-through is by accident-free design (CSS at-rules always have content after them, so they're always inline candidates, so they always raise unless escaped).
- **Auto-rewriting `@var` to `$var` in a migration tool.** If the workspace sanity check turns up enough hits that manual migration is painful, we could write a one-shot `plxt fix-sigils` command. Not in scope for this branch.
- **HTML/`<style>`-aware parsing of templates.** Templates remain plain strings to the preprocessor.
- **Changing the `tag()` / `format()` filter shapes.** Out of scope; this work is purely about which sigil sources rewrite into which Jinja form.
- **Spec doc updates in the cross-repo `mthds/` repo.** Per the workspace plugin rule, default is to leave spec edits for a separate PR initiated from that repo.
