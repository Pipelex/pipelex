import re
from re import Match

# Single-pass pattern covering all three sigils:
#   - `@?` optional insertion
#   - `@` tagged insertion
#   - `$` formatted insertion
#
# Sigil prefix: `@`/`@?` need the `(?<!\w)` lookbehind so emails (`user@example.com`) and other
# word-adjacent `@` don't get rewritten. `$` does NOT use the lookbehind — prose like `Q$quarter`
# should interpolate, and dollar amounts (`$10`) are already blocked downstream by `(?![0-9])`.
#
# Identifier: `(?![a-zA-Z0-9_.])` immediately after the greedy `[a-zA-Z0-9_.]+` prevents the regex
# engine from backtracking inside the identifier when the CSS/code-shape lookahead fails — it
# forces the match to span the whole identifier so the final lookahead either passes or the whole
# match is rejected (no half-identifier matches).
#
# Trailing CSS/code-shape lookahead blocks two shapes:
#   - direct: `\s*[({"']` covers `@media (...)`, `@import "..."`, `$(...)`, `${...}`, etc.
#   - one-word-then-opener: `\s*[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))` covers `@keyframes spin {...}`,
#     `@layer reset {...}`, `@import url(...)`. The inner-word arm requires `(` or a *single* `{`
#     (NOT `{{`) — `@var with {{ ... }}` is a legit template with Jinja, and `@name said "..."`
#     is prose. `@namespace svg "..."` is the remaining residual case; escape with `@@`.
#
# A single pass is required so this last lookahead only sees characters from the original
# template — running sequential passes would let `{` braces introduced by an earlier substitution
# trigger the lookahead and truncate later matches.
_SIGIL_PATTERN = re.compile(
    r"(?:(?<!\w)(@\??)|(\$))(?![0-9])([a-zA-Z0-9_.]+)(?![a-zA-Z0-9_.])"
    r"(?!\s*(?:[({\"']|[a-zA-Z][\w-]*\s*(?:[(]|\{(?!\{))))"
)

# Sentinels for `@@` / `$$` escapes. Replaced before the regex pass and restored after, so the
# escaped characters can't be confused with sigils. The NUL bytes make the sentinel impossible to
# collide with user template content.
_AT_ESCAPE_SENTINEL = "\x00PIPELEX_AT_ESCAPE\x00"
_DOLLAR_ESCAPE_SENTINEL = "\x00PIPELEX_DOLLAR_ESCAPE\x00"


def _replace_sigil(match: Match[str]) -> str:
    # Exactly one of group(1) (the `@`/`@?` arm) or group(2) (the `$` arm) is populated.
    sigil: str = match.group(1) or match.group(2)
    variable: str = match.group(3)
    trailing_dot = variable.endswith(".")
    if trailing_dot:
        # Trailing dot can't be in a variable name so it must be punctuation in the surrounding
        # sentence — strip it from the variable and re-emit it after the rendered Jinja.
        variable = variable[:-1]
    if sigil == "@?":
        rendered = f'{{% if {variable} %}}{{{{ {variable}|tag("{variable}") }}}}{{% endif %}}'
    elif sigil == "@":
        rendered = f'{{{{ {variable}|tag("{variable}") }}}}'
    else:
        rendered = f"{{{{ {variable}|format() }}}}"
    return f"{rendered}." if trailing_dot else rendered


def preprocess_template(template: str) -> str:
    """Preprocess a template string to convert our sigil syntax patterns into Jinja2 syntax.

    Recognized sigils (each must be preceded by a non-word boundary and not be followed by a
    code/CSS-like opener):

    - ``@var`` → ``{{ var|tag("var") }}``
    - ``@?var`` → ``{% if var %}{{ var|tag("var") }}{% endif %}``
    - ``$var`` → ``{{ var|format() }}``

    Authors can opt out per occurrence with the explicit escapes ``@@`` (→ literal ``@``) and
    ``$$`` (→ literal ``$``).
    """
    processed_template = template.replace("@@", _AT_ESCAPE_SENTINEL).replace("$$", _DOLLAR_ESCAPE_SENTINEL)
    processed_template = _SIGIL_PATTERN.sub(_replace_sigil, processed_template)
    return processed_template.replace(_AT_ESCAPE_SENTINEL, "@").replace(_DOLLAR_ESCAPE_SENTINEL, "$")
