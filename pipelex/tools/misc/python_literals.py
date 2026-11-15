"""Render authored text as Python source: a string literal, or a class docstring.

Every place that writes generated Python source with authored text in it goes through here — the codegen
emitters and the structure generator, whose modules are executed — so that one escaping decides how text
sits in source, and it reads back exactly as authored. Text interpolated between quotes by hand is how a
description ending in a quote, a backslash or a triple quote comes out as a different module than intended.
"""

from inspect import cleandoc


def escape_py_string(value: str) -> str:
    """Escape a string as the Python literal `ruff format` would leave alone.

    Double quotes by default, and single quotes only where that **strictly reduces** the escape count —
    which is ruff's (and black's) own normalization rule, verified across the mixed and tied cases. Always
    double-quoting was the tempting simplification and it broke the stamp: a description or choice
    carrying a `"` came out double-quoted with both quotes escaped, which ruff rewrites to the
    escape-free `'say "hi"'` on a consumer's very first format run — at any line width, reporting an
    untouched artifact as hand-edited.

    `repr` does the escaping of everything else — backslashes, newlines, control characters — and picks its
    own quote by a different rule, so its choice is converted when it disagrees.
    """
    quote = "'" if value.count("'") < value.count('"') else '"'
    escaped = repr(value)
    if escaped[0] == quote:
        return escaped
    # Only repr-single -> double is reachable: repr picks `"` solely for a value carrying `'` and no `"`,
    # which is exactly the shape this rule also wants double-quoted.
    other = escaped[0]
    inner = escaped[1:-1].replace(f"\\{other}", other).replace(quote, f"\\{quote}")
    return f"{quote}{inner}{quote}"


def _double_quoted_inner(value: str) -> str:
    """The inside of a double-quoted literal of `value`: every `"` and every backslash escaped, a `'` left bare.

    This is what text needs to sit inside a `\"\"\"` delimiter it can never close, whatever quotes it holds.
    `escape_py_string` is not that: it picks single quotes for a value with more `"` than `'`, which leaves
    every `"` bare.
    """
    escaped = repr(value)
    inner = escaped[1:-1]
    if escaped[0] == "'":
        # repr escaped every `'` and left every `"` bare: swap which of the two is escaped.
        inner = inner.replace("\\'", "'").replace('"', '\\"')
    return inner


def normalized_docstring_text(text: str) -> str:
    """The authored text as it reads back out of `inspect.getdoc` once rendered as a docstring.

    Two normalizations compose, neither of them chosen. Per-line trailing whitespace goes because
    `ruff format` strips it inside docstrings (and `D210` trims the edges), both as auto-applied fixes
    that would otherwise rewrite the stamped bytes. Then `cleandoc` — the same call `inspect.getdoc`
    makes — expands tabs, drops the common indentation, and trims blank edges. Composing them here is
    what makes the contract exact rather than approximate: the renderer indents continuation lines to the
    class body, and `cleandoc` takes that indentation straight back off.

    `cleandoc` runs twice because one pass is not where it settles: when the text opens with a blank line,
    the first pass drops it and promotes an indented line to first place, and the `inspect.getdoc` of the
    rendered docstring then strips that line's indentation again. The second pass is that strip, after
    which the text reads back unchanged.

    This is the renderer's half of the fidelity contract, and the exact expression tests assert against:
    `inspect.getdoc(cls) == normalized_docstring_text(description)`.
    """
    return cleandoc(cleandoc("\n".join(line.rstrip() for line in text.splitlines())))


def _docstring_delimiter(text: str) -> str | None:
    """The triple-quote delimiter `text` can sit inside verbatim, or `None` when it must be escaped.

    Falling back to `'''` for a description containing `\"\"\"` is what keeps the docstring **backslash-free**,
    and that is the whole point: any backslash trips ruff's `D301` ("use `r\"\"\"`"), and the `r` prefix it asks
    for would then render the escapes literally, corrupting the text. `ruff format` rewrites `'''` to `\"\"\"`
    only when that needs no escaping, so a `'''` chosen here is left alone.

    `None` means no verbatim rendering exists — the text carries both triple-quote styles, a control
    character, or a trailing backslash that would glue onto the closing delimiter.
    """
    if text.endswith("\\") or any(char not in {"\n", "\t"} and not char.isprintable() for char in text):
        return None
    return next((delimiter for delimiter in ('"""', "'''") if delimiter not in text and not text.endswith(delimiter[0])), None)


def class_docstring(description: str, *, extra_line: str | None = None, indent: str = "    ") -> str:
    """Render a class docstring; append `extra_line` (e.g. an imprecision caveat) as a second paragraph.

    Shaped the way a human writes one — summary on the first line, continuation lines indented to the class
    body, closing delimiter on its own line — because that is the only shape the pydocstyle rules and
    `ruff format` both leave untouched. Every rewrite they would otherwise apply (`D207` under-indented,
    `D209` closing quotes, `D210` edge whitespace) is an auto-applied fix, and each one changes the body
    bytes the codegen stamp hashes, which is precisely the drift the codegen emitters exist to prevent.

    So `__doc__` is deliberately *not* byte-identical to the authored description: it carries the
    indentation every hand-written docstring carries. The invariant that does hold is the one consumers
    read through — `inspect.getdoc(cls) == normalized_docstring_text(description)`. Exact bytes survive
    where they are consumed programmatically: `Field(description=...)`, and the crate itself.

    The text is never wrapped: a docstring becomes the model's JSON schema description, so a line break
    added here would become part of the text every consumer reads.
    """
    parts = [normalized_docstring_text(part) for part in (description or "", extra_line or "") if part.strip()]
    if not parts:
        return f'{indent}""""""'

    body = "\n\n".join(parts)
    delimiter = _docstring_delimiter(body)
    if delimiter is None:
        # No verbatim rendering exists, so escape. This trips `D301`, but ruff classes that fix as *unsafe*,
        # so a consumer's `ruff check --fix` still leaves the bytes — and the stamp — alone.
        # Every `"` is escaped, so no run of them can close the delimiter early.
        # Each rendered break carries the body indent, exactly as the verbatim branches do, so `cleandoc`
        # takes the same margin back off either way and the fidelity contract holds across both.
        escaped = f"\\n\\n{indent}".join(f"\\n{indent}".join(_double_quoted_inner(line) for line in part.split("\n")) for part in parts)
        return f'{indent}"""{escaped}"""'

    prefix = "r" if "\\" in body else ""
    lines = body.split("\n")
    if len(lines) == 1:
        return f"{indent}{prefix}{delimiter}{lines[0]}{delimiter}"
    continuation = "\n".join(f"{indent}{line}" if line else "" for line in lines[1:])
    return f"{indent}{prefix}{delimiter}{lines[0]}\n{continuation}\n{indent}{delimiter}"
