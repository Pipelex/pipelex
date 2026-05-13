import re
from re import Match

from pipelex.cogt.templating.template_errors import TemplateSigilSyntaxError
from pipelex.types import StrEnum


class _Sigil(StrEnum):
    """Recognized sigil prefixes. Defined as a `StrEnum` so the `match`/`case` over sigils is
    exhaustiveness-checked by the linter — adding a new sigil to the regex without updating the
    dispatcher (or vice versa) fails CI rather than silently misrouting.
    """

    AT = "@"
    AT_OPTIONAL = "@?"


# Line-bounded `@` / `@?` sigil.
#
# The line-bounded form is the only valid shape for `@`/`@?` — the `tag()` rewriter wraps the
# value in a block-shaped envelope, so an inline shape would produce nonsensical output. Leading
# and trailing whitespace on the line is captured and preserved so templates embedded in indented
# YAML/TOML blocks render in the same column as the surrounding text. Input is normalized to
# `\n` line endings up-front (see `preprocess_template`), so this pattern only needs to handle
# `\n`-separated lines.
#
# Identifier shape: first char must be a letter or underscore (not a digit); dotted access
# supported; segments are non-empty and start with letter or underscore.
_AT_SIGIL_PATTERN = re.compile(
    r"^([ \t]*)(@\??)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)([ \t]*)$",
    re.MULTILINE,
)

# Inline `$` sigil — keeps its inline contract. The word-boundary lookbehind `(?<!\w)` mirrors
# the `@` candidate pattern's left guard: `$` adjacent to a word character on the left passes
# through silently (so prose like `micro$oft` or `user$host.com` does not produce mid-word
# substitution). The strict segmented identifier `[a-zA-Z_]...(?:\.[a-zA-Z_]...)*` rules out a
# leading digit (so `$10` is unaffected without a separate `(?![0-9])` arm) and consecutive dots
# (so `$name..` matches just `name`, leaving both trailing dots as literal punctuation outside
# the match — no invalid Jinja). The trailing lookaheads block word-character continuation and
# code-shape constructs (`$foo(`, `$foo "..."`, `${...}`).
_DOLLAR_SIGIL_PATTERN = re.compile(
    r"(?<!\w)(\$)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)(?![a-zA-Z0-9_])(?!\s*[({\"'])",
)

# Candidate-sigil detector for the validator: any unescaped `@`/`@?` at a non-word boundary
# followed immediately by an identifier shape. Used only to surface errors; never substitutes.
_AT_CANDIDATE_PATTERN = re.compile(
    r"(?<!\w)(@\??)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)",
)

# Sentinels for `@@` / `$$` escapes. Replaced before the validator and regex pass, and restored
# after, so escaped characters never reach the validator and never trip the strict rule. The NUL
# bytes make collision with realistic template content extremely unlikely.
_AT_ESCAPE_SENTINEL = "\x00PIPELEX_AT_ESCAPE\x00"
_DOLLAR_ESCAPE_SENTINEL = "\x00PIPELEX_DOLLAR_ESCAPE\x00"


def _replace_at_sigil(match: Match[str]) -> str:
    leading: str = match.group(1)
    sigil = _Sigil(match.group(2))
    variable: str = match.group(3)
    trailing: str = match.group(4)
    match sigil:
        case _Sigil.AT_OPTIONAL:
            rendered = f'{{% if {variable} %}}{{{{ {variable}|tag("{variable}") }}}}{{% endif %}}'
        case _Sigil.AT:
            rendered = f'{{{{ {variable}|tag("{variable}") }}}}'
    return f"{leading}{rendered}{trailing}"


def _replace_dollar_sigil(match: Match[str]) -> str:
    variable: str = match.group(2)
    return f"{{{{ {variable}|format() }}}}"


def _validate_at_sigil_alone_on_line(template: str) -> None:
    r"""Scan for `@`/`@?` sigil candidates that are not alone on their own line and raise.

    Inputs are post-`@@`-escape (so `@@` cases are already sentinel-replaced and don't trip the
    check). Word-adjacent `@` (emails, prose hashtags) is excluded by the `(?<!\w)` lookbehind
    on the candidate pattern.
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


def preprocess_template(template: str) -> str:
    r"""Preprocess a template string to convert our sigil syntax patterns into Jinja2 syntax.

    Recognized sigils:

    - ``@var`` (alone on its own line) → ``{{ var|tag("var") }}``
    - ``@?var`` (alone on its own line) → ``{% if var %}{{ var|tag("var") }}{% endif %}``
    - ``$var`` (inline) → ``{{ var|format() }}``

    Inline ``@var`` / ``@?var`` shapes are rejected at load time with `TemplateSigilSyntaxError`.

    Authors can opt out per occurrence with the explicit escapes ``@@`` (→ literal ``@``) and
    ``$$`` (→ literal ``$``).

    Line endings (``\r\n``, ``\r``) are normalized to ``\n`` up-front so the line-bounded ``@``
    rule works the same for Windows / classic-Mac authored templates as for Unix ones. The
    rendered output uses ``\n``-only line endings; downstream Jinja rendering is
    line-ending-insensitive.
    """
    # 1. Normalize line endings so the line-bounded rule is consistent across platforms.
    processed_template = template.replace("\r\n", "\n").replace("\r", "\n")
    # 2. Escape sentinels — @@ and $$ disappear before validation and substitution.
    processed_template = processed_template.replace("@@", _AT_ESCAPE_SENTINEL).replace("$$", _DOLLAR_ESCAPE_SENTINEL)
    # 3. Validate: any candidate @-sigil that is not alone on its line is an error.
    _validate_at_sigil_alone_on_line(processed_template)
    # 4. Substitute: $ inline first, then @ line-bounded. Running $ first keeps the $ pattern's
    #    code-shape lookahead from misfiring on `{{` braces introduced by the @ pass. The @
    #    pattern is line-bounded and indifferent to $-introduced braces.
    processed_template = _DOLLAR_SIGIL_PATTERN.sub(_replace_dollar_sigil, processed_template)
    processed_template = _AT_SIGIL_PATTERN.sub(_replace_at_sigil, processed_template)
    # 5. Restore sentinels.
    return processed_template.replace(_AT_ESCAPE_SENTINEL, "@").replace(_DOLLAR_ESCAPE_SENTINEL, "$")
