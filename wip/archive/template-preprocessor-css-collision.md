# Template preprocessor — sigil collision with CSS, emails, and code

## Context

The template preprocessor at `pipelex/cogt/templating/template_preprocessor.py` rewrites three sigils into Jinja2 before rendering:

- `@var` → `{{ var|tag("var") }}` (regex `r"@(?![0-9])([a-zA-Z0-9_.]+)"`)
- `@?var` → optional insertion (`{% if var %}…{% endif %}`)
- `$var` → `{{ var|format() }}`

There is no escape mechanism today — only a `# TODO: allow escape patterns` comment. This produces silent breakage in any template whose source text legitimately contains an `@` or `$` followed by a word.

## Observed failure

PipeCompose templates that embed HTML/CSS in a `<style>` block break on CSS at-rules. Example from the wild:

```html
<style>
  /* … */
  @media (max-width: 820px) {
    .fashion-project-page { padding: 24px; }
    /* … */
  }
</style>
```

The preprocessor rewrites `@media` as a template variable. The downstream Jinja2 render then fails or produces garbage. Authoring agents currently work around this by deleting responsive blocks — losing functionality the template was meant to express.

## The problem is wider than CSS

The exact same regex misfires on:

- **CSS at-rules**: `@media`, `@import`, `@keyframes`, `@font-face`, `@supports`, `@charset`, `@namespace`, `@page`, `@property`, `@layer`, `@container`, `@scope`, … plus everything CSS adds in the future.
- **Email addresses** in body text: `someone@example.com` → captures `example.com` as a variable (already documented in `test_email_address_partially_processed`).
- **Code-block content in LLM prompts**: Python decorators (`@property`, `@staticmethod`, `@classmethod`), cron specs (`@daily`), social handles (`@username`).
- **`$` has the symmetric problem**: bash vars in code blocks (`$PATH`), jQuery (`$(...)`), LaTeX math (`$…$`).

Any solution scoped narrowly to CSS will be reopened the first time an agent generates an HTML template with an email address or a Python snippet.

## Strategies considered

### 1. Reserved CSS keyword list

Maintain a static set of CSS at-rule names that the preprocessor leaves alone.

- **Pros**: zero LLM cognitive overhead for the common case.
- **Cons**: CSS-specific hack baked into a domain-agnostic templating layer; the list rots as CSS evolves; doesn't help emails / decorators / cron / handles; quietly reserves common words like `media`, `import`, `page`, `layer`, `property` as unusable variable names via `@var` syntax.

### 2. Explicit escape (`@@` → literal `@`, `$$` → literal `$`)

Add a Razor-style escape so authors can opt out of preprocessing on any `@` or `$`.

- **Pros**: principled, generic, predictable; covers every present and future collision (CSS, emails, handles, decorators).
- **Cons**: paste-existing-CSS-as-is doesn't "just work" — every at-rule needs `@@`. LLMs generating templates need to know the rule (prompt/doc burden).

### 3. Smarter regex heuristics

Refine the regex so it doesn't match the problematic shapes in the first place:

- **`(?<!\w)` lookbehind before each sigil** — skips when the `@` or `$` is preceded by a word character. Kills emails: in `user@example.com`, the `@` is preceded by `r`, so it's skipped.
- **`(?!\s*[({"'])` lookahead after the captured identifier** — skips when the identifier is followed by `(`, `"`, `'`, or `{` (with optional whitespace). Kills CSS at-rules: `@media (…)`, `@supports (…)`, `@import "…"`, `@charset "…"`, `@keyframes name {…}`, `@font-face {…}`, `@page {…}`, `@layer name {…}`, etc.

Template variables in Pipelex are essentially never followed by `(` / `"` / `'` / `{`. The user confirmed that the only conceivable counter-example `@var (note)` does not occur in practice: `@var` is used for tagged block insertion, so wrapping the inserted block in a parenthetical immediately after would not make semantic sense.

- **Pros**: zero burden on authors, no reserved names, no list to maintain, fixes CSS *and* emails in one stroke.
- **Cons**: heuristic — there may be residual edge cases we haven't anticipated, which is why we want an escape too.

### 4. Context-aware skipping (don't preprocess inside `<style>` / fenced code blocks)

Parse the template enough to identify "code-like" regions and skip preprocessing inside them.

- **Pros**: bulletproof inside the protected context.
- **Cons**: real parsing complexity; doesn't help emails in body text; easy to get wrong (nested blocks, malformed HTML). Overkill.

### 5. Stricter syntax (`@{var}`)

Require a delimiter around the variable name.

- **Pros**: cleanest theoretically.
- **Cons**: breaking change across the entire MTHDS surface, churns every existing `.mthds` file, gives up the ergonomic appeal of bare `@var`. Not justified by the problem.

## Decision

Adopt **Strategy 3 (heuristic regex tightening) + Strategy 2 (explicit escape)**. Skip the rest.

### Heuristic regex tightening (primary fix)

Apply to all three sigils (`@`, `@?`, `$`):

1. Add a `(?<!\w)` lookbehind in front of the sigil.
2. Add a `(?!\s*[({"'])` lookahead immediately after the captured identifier.

This silently fixes CSS at-rules, email addresses, and most code-block cases — with no author intervention, no reserved names, and no maintenance burden.

### Explicit escape (safety net)

1. Treat `@@` as a literal `@` (consumed during preprocessing).
2. Treat `$$` as a literal `$` (consumed during preprocessing).
3. The escape must be applied **after** sigil substitution so that `@@var` produces a literal `@var` and not a Jinja2 expression, but **before** Jinja2 receives the template.

Heuristics fail silently; the escape gives authors a clean, explicit opt-out for any residual case the heuristic can't predict.

### What we explicitly do not do

- No reserved CSS keyword list.
- No context-aware HTML parsing.
- No breaking syntax migration.

## Rationale for combining both layers

- The heuristic alone makes the common case work for authors and LLMs without anyone having to know about escaping.
- The escape alone forces every author and every prompt to learn the rule, and breaks paste-existing-CSS workflows.
- Together, they cover the realistic surface: the heuristic handles the cases we can predict; the escape handles the cases we can't.

## Scope of the change

The preprocessor is shared across LLM prompts, PipeCompose templates, ImgGen prompts, and template document analyzers — all the call sites in:

- `pipelex/pipe_operators/llm/pipe_llm_blueprint.py`
- `pipelex/pipe_operators/llm/template_document_analyzer.py`
- `pipelex/pipe_operators/compose/construct_blueprint.py`
- `pipelex/pipe_operators/compose/pipe_compose_blueprint.py`
- `pipelex/pipe_operators/compose/pipe_compose_factory.py`
- `pipelex/pipe_operators/shared/template_image_analyzer.py`
- `pipelex/pipe_operators/search/pipe_search_blueprint.py`
- `pipelex/pipe_operators/img_gen/pipe_img_gen_blueprint.py`
- `pipelex/cogt/templating/template_blueprint.py`

A single change to `preprocess_template` covers all of them.

## Backward compatibility

- The `(?!\s*[({"'])` lookahead changes the meaning of templates that currently match `@var (...)` or `$var "...`". The user confirmed `@var (…)` is not a real pattern (tagged blocks make a trailing parenthetical nonsensical). For `$` the same reasoning applies — `$var` is value formatting; a trailing parenthesized phrase is also unidiomatic.
- The `(?<!\w)` lookbehind changes templates where `@var` immediately follows a word character. Today such templates already produce surprising results (see the email test); tightening here is a behavior fix, not a regression.
- `@@` and `$$` are not currently meaningful in templates, so consuming them as escapes is a pure addition.

A workspace-wide grep over existing `.mthds` files should confirm zero collisions before merge.

## Documentation follow-ups (out of scope of this change, tracked separately)

- Update agent-facing MTHDS authoring guidance to mention `@@` and `$$` escapes.
- Add a short "writing templates with code/HTML inside" section to the docs.
- Update the existing `test_email_address_partially_processed` semantics: emails should now pass through cleanly.

## Open questions

None blocking. The user confirmed the `@var (…)` edge case is not real, which removes the only material concern with the heuristic.
