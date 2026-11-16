"""Render authored text as Python source: a string literal, or a class docstring.

Every place that writes generated Python source with authored text in it goes through here — the codegen
emitters and the structure generator, whose modules are executed — so that one escaping decides how text
sits in source, and it reads back exactly as authored. Text interpolated between quotes by hand is how a
description ending in a quote, a backslash or a triple quote comes out as a different module than intended.
"""

from inspect import cleandoc


def _double_quoted_inner(value: str) -> str:
    """The inside of a double-quoted literal of `value`: every `"` and every backslash escaped, a `'` left bare.

    This is the one escaper of this module. It is also what text needs to sit inside a `\"\"\"` delimiter it can
    never close, whatever quotes it holds. `repr` does the escaping of backslashes, newlines and control
    characters, and picks its own quote, so its choice is converted when it picked the single one.
    """
    escaped = repr(value)
    inner = escaped[1:-1]
    if escaped[0] == "'":
        # repr escaped every `'` and left every `"` bare: swap which of the two is escaped.
        inner = inner.replace("\\'", "'").replace('"', '\\"')
    return inner


def escape_py_string(value: str) -> str:
    """Escape a string as the Python literal `ruff format` would leave alone.

    Double quotes by default, and single quotes only where that **strictly reduces** the escape count —
    which is ruff's (and black's) own normalization rule, verified across the mixed and tied cases. Always
    double-quoting was the tempting simplification and it broke the stamp: a description or choice
    carrying a `"` came out double-quoted with both quotes escaped, which ruff rewrites to the
    escape-free `'say "hi"'` on a consumer's very first format run — at any line width, reporting an
    untouched artifact as hand-edited.

    The single-quoted case is `repr` itself: `repr` picks `'` for any value holding a `"`, which a value
    with more `"` than `'` does.
    """
    if value.count("'") < value.count('"'):
        return repr(value)
    return f'"{_double_quoted_inner(value)}"'


def normalized_docstring_text(text: str) -> str:
    """The authored text as it reads back out of `inspect.getdoc` once rendered as a docstring.

    Two normalizations, neither of them chosen. Each line loses its trailing spaces and tabs, because
    `ruff format` strips them inside a docstring as an auto-applied fix that would otherwise rewrite the
    stamped bytes. A line ends at a newline, a carriage return, or both together, and at nothing else. Then `cleandoc` —
    the very call `inspect.getdoc` makes — expands tabs, drops the indentation the lines after the first
    share, and trims blank edges. `class_docstring` renders this text so that `getdoc` reads it back
    unchanged, relative indentation included.

    This is the renderer's half of the fidelity contract, and the exact expression tests assert against:
    `inspect.getdoc(cls) == normalized_docstring_text(description)`.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return cleandoc("\n".join(line.rstrip(" \t") for line in lines))


def _docstring_delimiter(text: str) -> str | None:
    """The triple-quote delimiter `text` can sit inside verbatim, or `None` when it must be escaped.

    Falling back to `'''` for a description containing `\"\"\"` is what keeps the docstring **backslash-free**,
    and that is the whole point: any backslash trips ruff's `D301` ("use `r\"\"\"`"), and the `r` prefix it asks
    for would then render the escapes literally, corrupting the text.

    A delimiter is only chosen where `ruff format` leaves it alone. It rewrites `'''` to `\"\"\"` whenever the text
    holds no `\"\"\"`, and it pads with a space a text that opens with the delimiter's quote, or, on a single line,
    closes with it. The closing delimiter of a multi-line docstring sits on its own line, so only a single line
    is held to its last character.

    `None` means no verbatim rendering exists — the text carries both triple-quote styles, a control
    character, a backslash ending a line or beside a triple quote, or an edge quote no delimiter leaves unpadded.
    """
    if any(char not in {"\n", "\t"} and not char.isprintable() for char in text):
        return None
    # A backslash renders in a raw string, where ruff still reads one at a line's end as joining the next line, and
    # one before `"""` as leaving that delimiter usable.
    if "\\" in text and ('"""' in text or any(line.endswith("\\") for line in text.split("\n"))):
        return None
    single_line = "\n" not in text
    for delimiter in ('"""', "'''"):
        quote = delimiter[0]
        if delimiter == "'''" and '"""' not in text:
            return None
        if delimiter not in text and not text.startswith(quote) and not (single_line and text.endswith(quote)):
            return delimiter
    return None


def _summary_first_value(*, lines: list[str], indent: str, closing_indent: bool) -> str:
    """The value of a docstring of `lines` laid out summary-first: the summary beside the opening quotes, the rest indented.

    With `closing_indent`, the value ends on a line holding only `indent`, where the closing delimiter of a verbatim
    docstring sits on its own line.
    """
    continuation = "".join(f"\n{indent}{line}" if line else "\n" for line in lines[1:])
    closing = f"\n{indent}" if closing_indent and len(lines) > 1 else ""
    return f"{lines[0]}{continuation}{closing}"


def class_docstring(description: str, *, extra_line: str | None = None, indent: str = "    ") -> str:
    """Render a class docstring; append `extra_line` (e.g. an imprecision caveat) as a second paragraph.

    Verbatim when it can be, shaped the way a human writes one — summary on the first line, continuation
    lines indented to the class body, closing delimiter on its own line — because that is the only shape
    the pydocstyle rules and `ruff format` both leave untouched. Every rewrite they would otherwise apply
    (`D207` under-indented, `D209` closing quotes, `D210` edge whitespace, `D212` summary on the first line)
    is an auto-applied fix, and each one changes the body bytes the codegen stamp hashes, which is precisely
    the drift the codegen emitters exist to prevent.

    `inspect.getdoc` strips the indentation the lines after the first share, so the summary-first shape only
    reads back when those lines share none. When they do — a text that opens on a blank line and indents its
    whole body — or when no verbatim rendering exists, the docstring is escaped onto one physical line:
    summary-first when that reads back, and otherwise opening with an escaped newline, which leaves `getdoc`
    no first line to treat apart. The escaped form trips `D301`, but ruff classes that fix as *unsafe*, so a
    consumer's `ruff check --fix` leaves the bytes — and the stamp — alone; on one physical line, it trips no
    `D212`, whose fix is safe.

    So `__doc__` is deliberately *not* byte-identical to the authored description: it carries the
    indentation every hand-written docstring carries. The invariant that does hold is the one consumers
    read through — `inspect.getdoc(cls) == normalized_docstring_text(description)`. Exact bytes survive
    where they are consumed programmatically: `Field(description=...)`, and the crate itself.

    The text is never wrapped: a docstring becomes the model's JSON schema description, so a line break
    added here would become part of the text every consumer reads.
    """
    normalized_parts = (normalized_docstring_text(part) for part in (description or "", extra_line or ""))
    parts = [part for part in normalized_parts if part]
    if not parts:
        return f'{indent}""""""'

    body = "\n\n".join(parts)
    lines = body.split("\n")
    delimiter = _docstring_delimiter(body)
    if delimiter is not None:
        # Text holding no escape reads back as written, in a raw string as in a plain one: this is the docstring's value.
        verbatim = _summary_first_value(lines=lines, indent=indent, closing_indent=True)
        if cleandoc(verbatim) == body:
            prefix = "r" if "\\" in body else ""
            return f"{indent}{prefix}{delimiter}{verbatim}{delimiter}"

    # In the escaped form every `"` and every backslash is escaped, so no run of quotes can close the delimiter early,
    # and the value sits on one physical line. It is summary-first when that reads back; otherwise the value opens and
    # closes with a newline, which always reads back: `cleandoc` then has no first line to strip, and the indentation
    # the lines share, which is none, is all it removes from the others.
    summary_first = _summary_first_value(lines=lines, indent=indent, closing_indent=False)
    value = summary_first if cleandoc(summary_first) == body else f"\n{body}\n"
    return f'{indent}"""{_double_quoted_inner(value)}"""'
