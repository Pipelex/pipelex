import re
from re import Match

from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
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
#
# The `[ \t]` whitespace class is intentionally ASCII-only. Non-ASCII whitespace (NBSP,
# EM SPACE, etc. — usually from rich-text copy-paste) is not recognized as indentation;
# the validator (`_validate_at_sigil_alone_on_line`) surfaces a targeted error when this
# trips up a declared input rather than the generic "must appear alone on its own line".
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
# shell-style code constructs on the same line (`$foo "..."`, `$foo 'bar'`, `$foo {y}`,
# `$foo (parens)`). The horizontal-whitespace class `[ \t]+` (one-or-more, not zero-or-more)
# keeps the guard same-line *and* requires a space before the opener: zero-space adjacency
# to `'` / `"` / `{` / `(` reads as natural prose (possessives like `$user's data`, parenthetical
# `$user(note)`, adjacent quoting `$user"x"`) and interpolates. Zero-space `$` + opener with no
# identifier in between (`$(...)`, `${...}`, `$"..."`) is still blocked because the identifier
# capture in this same pattern fails — the lookahead only matters when an identifier did match.
# The `[ \t]+` class is also intentionally ASCII-only — non-ASCII whitespace (NBSP / EM SPACE)
# adjacent to an opener reads as opaque text, so `$foo<NBSP>"bar"` interpolates `$foo`.
_DOLLAR_SIGIL_PATTERN = re.compile(
    r"(?<!\w)(\$)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)(?![a-zA-Z0-9_])(?![ \t]+[({\"'])",
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


def _validate_at_sigil_alone_on_line(template: str, declared_inputs: set[str]) -> None:
    r"""Scan for `@`/`@?` sigil candidates that are not alone on their own line and raise
    when the candidate's root identifier is one of the surrounding pipe's declared inputs.

    Inputs are post-`@@`-escape (so `@@` cases are already sentinel-replaced and don't trip the
    check). Word-adjacent `@` (emails, prose hashtags) is excluded by the `(?<!\w)` lookbehind
    on the candidate pattern. Inline candidates whose root identifier is not in `declared_inputs`
    pass through silently — they're CSS at-rules, code decorators, or other false positives the
    validator can't distinguish from typos without the inputs context.
    """
    for line_index, line in enumerate(template.split("\n"), start=1):
        if "@" not in line:
            continue
        if _AT_SIGIL_PATTERN.fullmatch(line):
            continue
        stripped = line.strip()
        if _AT_SIGIL_PATTERN.fullmatch(stripped):
            padding_candidate = _AT_CANDIDATE_PATTERN.search(stripped)
            if padding_candidate is not None:
                padding_identifier = padding_candidate.group(2)
                if get_root_from_dotted_path(padding_identifier) in declared_inputs:
                    padding_sigil = padding_candidate.group(1)
                    msg = (
                        f"`{padding_sigil}{padding_identifier}` on line {line_index} is padded with "
                        f"non-ASCII whitespace (e.g. NBSP, EM SPACE — often from rich-text "
                        f"copy-paste). Only ASCII space/tab is recognized as line indentation. "
                        f"Replace non-ASCII whitespace with regular spaces, or escape with `@@` if "
                        f"you intend a literal `@`."
                    )
                    raise TemplateSigilSyntaxError(msg)
            continue
        for candidate in _AT_CANDIDATE_PATTERN.finditer(line):
            sigil = candidate.group(1)
            identifier = candidate.group(2)
            root_identifier = get_root_from_dotted_path(identifier)
            if root_identifier not in declared_inputs:
                continue
            msg = (
                f"Inline `{sigil}{identifier}` is not allowed on line {line_index}: "
                f"the `{sigil}` sigil produces tag-wrapped block content and must appear alone on "
                f"its own line. "
                f"Did you mean `${identifier}` (inline value), or move `{sigil}{identifier}` onto "
                f"its own line? "
                f"Escape with `@@` if you intend a literal `@`."
            )
            raise TemplateSigilSyntaxError(msg)


def _normalize_and_escape(template: str) -> str:
    """Normalize line endings and replace `@@`/`$$` escapes with sentinels."""
    normalized = template.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("@@", _AT_ESCAPE_SENTINEL).replace("$$", _DOLLAR_ESCAPE_SENTINEL)


def validate_template_sigils(template: str, declared_inputs: set[str]) -> None:
    r"""Raise `TemplateSigilSyntaxError` when an inline `@`/`@?` candidate's root identifier
    matches one of the pipe's declared inputs.

    The check is narrow on purpose: shapes like inline `@media` (CSS at-rules) or `@deprecated`
    (Python/Java decorators) are common in HTML/CSS templates, so raising on every inline `@`
    would be hostile. By gating on `declared_inputs`, the validator only fires on identifiers
    the author actually plans to use — i.e. the "real typo" cases.
    """
    prepared = _normalize_and_escape(template)
    _validate_at_sigil_alone_on_line(prepared, declared_inputs)


def rewrite_template_sigils(template: str) -> str:
    r"""Apply the sigil rewrites without validation.

    Substitutes `$` inline first, then `@`/`@?` line-bounded. Order is structurally safe
    in either direction: the `$` code-shape lookahead `(?![ \t]*[({"'])` is horizontal-only,
    so it cannot cross a `\n` to reach the `{` introduced by the `@` pass (which only
    substitutes alone-on-line, always preceded by a newline). `$`-first is chosen defensively
    — it remains correct if the `$` lookahead is ever loosened to `\s*`.

    Use this at render time, when the template has already been validated at load time —
    there's no point re-running the validator.
    """
    prepared = _normalize_and_escape(template)
    prepared = _DOLLAR_SIGIL_PATTERN.sub(_replace_dollar_sigil, prepared)
    prepared = _AT_SIGIL_PATTERN.sub(_replace_at_sigil, prepared)
    return prepared.replace(_AT_ESCAPE_SENTINEL, "@").replace(_DOLLAR_ESCAPE_SENTINEL, "$")


def preprocess_template(template: str, *, declared_inputs: set[str] | None = None) -> str:
    r"""Preprocess a template string to convert our sigil syntax patterns into Jinja2 syntax.

    Recognized sigils:

    - ``@var`` (alone on its own line) → ``{{ var|tag("var") }}``
    - ``@?var`` (alone on its own line) → ``{% if var %}{{ var|tag("var") }}{% endif %}``
    - ``$var`` (inline) → ``{{ var|format() }}``

    Inline ``@var`` / ``@?var`` shapes are rejected at load time with `TemplateSigilSyntaxError`
    **only when** the candidate identifier's root segment is in ``declared_inputs`` — that's the
    "real typo" gate. When ``declared_inputs`` is ``None`` (the default), the validator is
    skipped entirely, so callers without inputs context (the base ``TemplateBlueprint`` model
    validator, discovery passes in ``ConstructBlueprint``) don't raise on inline shapes.

    Authors can opt out per occurrence with the explicit escapes ``@@`` (→ literal ``@``) and
    ``$$`` (→ literal ``$``).

    Line endings (``\r\n``, ``\r``) are normalized to ``\n`` up-front so the line-bounded ``@``
    rule works the same for Windows / classic-Mac authored templates as for Unix ones. The
    rendered output uses ``\n``-only line endings; downstream Jinja rendering is
    line-ending-insensitive.
    """
    if declared_inputs is not None:
        validate_template_sigils(template, declared_inputs)
    return rewrite_template_sigils(template)
