"""AST core for the log-call guard.

Pipelex's log-call conventions, written for contributors in ``docs/tools/logging.md`` ("Log-call conventions"), say
that a line's message is a fixed sentence and that its values ride in ``fields``. This module checks the ones that
can be read off the source, on every call of the ``log`` facade in ``pipelex/`` outside ``pipelex/tools/log/``
and in the ``api/`` member's ``api/pipelex_api/``:

1. **The interpolation rule, at INFO and above** (``info``, ``warning``, ``error``, ``critical``). The message is a
   literal written at the call: a string constant, an f-string without a placeholder, a ``+`` of literals, a
   conditional between literals, or a name whose bindings that can reach the call are all literals, a ``+=`` of a
   literal included. A message built by an f-string, by ``%``, by ``+`` or by ``.format()`` is refused under that
   form's name, and so is a name bound to one of those, the binding's line given. Any other expression, a parameter,
   an attribute, a call's result, a mapping, a name captured from an enclosing function, is refused as
   ``non-literal``: the guard cannot tell that it is fixed, and every such message the first census found was built
   from values.
2. **The markup rule, at every level.** No literal text of a message, its title or its inline title holds a Rich
   markup tag: a closing tag (``[/red]``, ``[/]``), an ``@`` handler, or a tag whose text Rich reads as a style
   (``[red]``, ``[bold green]``, ``[link=https://…]``) or as one of its theme's style names. The text is read the way
   it reaches the console: a ``+`` of literals, named ones included, is folded into one text before it is scanned. A
   bracketed word that is no style, ``list[int]``, is text and passes. A tag escaped with a backslash passes.
3. **The wording rules.** At every level, a message starts with no lowercase letter (``lowercase-start``), ends with
   no period and no ellipsis (``trailing-period``) and holds no backtick (``backtick``); at INFO and above it also
   names no identifier, a word holding an underscore or a call written ``name()`` (``identifier``), and holds at most
   ``MAX_MESSAGE_LENGTH`` characters (``length``). They read the texts the markup rule reads, each text a message can
   reach the console as, and one text that breaks a rule is enough: a conditional between a good and a bad literal
   breaks it. A text that starts or ends with a value the guard cannot read passes the rule about that end, and the
   length counts a text's literal parts alone, the least it can hold once its values are spliced in.
4. **The exception rule, at every level** (``spliced-exception``). No value a message splices into its text reaches
   a handled exception: an f-string's placeholder, a value a ``%`` or a ``.format()`` formats, or any part of the
   message that is no literal text, the message itself included. A value reaches one when it calls a
   ``.exception()`` method, or reads a name bound by ``except ... as``, directly or through the bindings of the names
   it reads (``detail = str(exc)``), a captured name included.

The title and the inline title join the message (the dispatch renders them into it), so every rule reads them too,
each as a text of its own, and a title or an inline title that is statically ``None`` is no text at all. A ``**``
expansion of a dict literal with string keys passes its entries as keywords; any other ``**`` expansion could carry
the message, so it is refused as ``non-literal`` at every level. DEBUG and VERBOSE may keep an f-string, a long
message and an identifier; every other rule holds there as everywhere.

**Names** are read by Python's own scoping: the scope the call is made in (a comprehension reading as part of the
scope it is written in), then the enclosing functions, class bodies never among them, then the module. Of a name's
bindings there, only those that can reach the read count, by the scope's control flow: the nearest along
straight-line code, the nearest on each path through an ``if``, a ``try`` or a ``match``, those a loop's later passes
carry back, and none past a ``return``, a ``raise``, a ``break`` or a ``continue``. A name bound in an enclosing
function is not followed, save by the exception rule, which reads it through every binding that function makes. The
facade itself is found the same way: a call's receiver is the facade where an import of the facade reaches it, a
captured receiver read through every binding of its function too. One index of every scope's bindings and flow is
built per module, in one walk.

**The baseline.** The calls that broke the rules when the guard arrived are listed in the committed
``log_call_baseline.toml`` at the repo root, under the key ``<relative_path>::<qualified_name>`` of the function that
makes them, ``<module>`` for a module-level call, each by its signature: the method, the message's source text, the
rules the call breaks and every binding that reaches the names the guard read to judge it, the bindings a spliced
exception is reached through included (``warning: msg [f-string] where msg = f"Loaded {alias}"``), rendered the same
on every supported Python. Line
numbers never enter it. The comparison with the tree is exact both ways: a call the baseline does not list fails,
and so does a listed signature no call matches any more, whether the call now complies, moved to another function,
or had its message, a binding of it or the rules it breaks change, until its entry is removed. Changing a listed
call's message is therefore converting it. ``prune_baseline`` removes stale signatures and never adds one; nothing
here adds one.

**The baseline only shrinks.** ``compare_with_trusted_baseline`` holds the working baseline to the one committed at
a trusted revision, the base a change merges into, read through git: a signature it does not list, or lists fewer
times, is growth, and fails.

There is no escape hatch: a message that must vary is a fixed message with fields.

The presentation layer wired into the ``pipelex-dev`` Typer app lives in ``check_log_calls_cmd.py``.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import tomllib
from collections import Counter
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias, cast

import tomlkit
from rich.default_styles import DEFAULT_STYLES
from rich.errors import StyleSyntaxError
from rich.markup import RE_TAGS
from rich.style import Style
from typing_extensions import override

from pipelex.tools.misc.toml_utils import save_toml_to_path

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence

#: The trees the guard scans, relative to the repo root: the runtime and the API server, which logs through the same facade.
SCAN_ROOTS: tuple[Path, ...] = (Path("pipelex"), Path("api") / "pipelex_api")

#: The directory a scan root's packages are imported from, when it is not the repo root itself.
IMPORT_ROOTS: tuple[Path, ...] = (Path("api"),)

#: The facade's own package, whose internals build messages for the sinks and are not call sites.
EXCLUDED_ROOTS: tuple[Path, ...] = (Path("pipelex") / "tools" / "log",)

#: The committed baseline of the calls that broke the rules when the guard arrived, relative to the repo root.
BASELINE_FILE = Path("log_call_baseline.toml")

#: This module, relative to the repo root: a revision that holds it runs the guard, so a baseline missing there is empty.
GUARD_MODULE_FILE = Path("pipelex") / "cli" / "dev_cli" / "commands" / "log_call_guard.py"

#: The only version of the baseline's shape.
BASELINE_VERSION = 1

#: The dotted paths the ``log`` facade is reachable at: the package's re-export and the object in its own module.
FACADE_PATHS = frozenset({"pipelex.log", "pipelex.tools.log.log.log"})

#: The modules whose ``import *`` binds the facade under its own name.
FACADE_STAR_MODULES = frozenset({"pipelex", "pipelex.tools.log.log"})
FACADE_NAME = "log"

#: The facade's methods at INFO and above, where a message is a literal, names no identifier and is short.
INFO_AND_ABOVE_METHODS = frozenset({"info", "warning", "error", "critical"})

#: Every method of the facade that emits a line, where a message holds no markup, keeps the wording rules that hold at
#: every level and splices no exception.
EMITTING_METHODS = frozenset({"verbose", "debug", *INFO_AND_ABOVE_METHODS})

#: The longest a message may be at INFO and above, in characters.
MAX_MESSAGE_LENGTH = 80

#: The keyword a call may pass its message under instead of positionally.
CONTENT_KEYWORD = "content"

#: The keywords whose text the dispatch renders into the message.
TITLE_KEYWORDS = ("title", "inline")

#: The qualified name of a call made outside any function or class.
MODULE_SCOPE_NAME = "<module>"

#: How long a git command reading the trusted baseline may take.
GIT_TIMEOUT_SECONDS = 30


class LogCallGuardError(Exception):
    """The guard cannot run as configured: a missing scan root, a malformed baseline or an unreadable revision, never a violation.

    Kept local to this module rather than derived from ``PipelexError``, for the reason ``hub_layering_guard``
    gives for its own.
    """


class LogCallRule(StrEnum):
    """A rule a log call breaks, each naming its remedy."""

    F_STRING = "f-string"
    PERCENT_FORMAT = "percent-format"
    CONCATENATION = "concatenation"
    FORMAT_CALL = "format-call"
    NON_LITERAL = "non-literal"
    MARKUP = "markup"
    LOWERCASE_START = "lowercase-start"
    TRAILING_PERIOD = "trailing-period"
    BACKTICK = "backtick"
    IDENTIFIER = "identifier"
    LENGTH = "length"
    SPLICED_EXCEPTION = "spliced-exception"

    @property
    def remedy(self) -> str:
        match self:
            case LogCallRule.F_STRING | LogCallRule.PERCENT_FORMAT | LogCallRule.CONCATENATION | LogCallRule.FORMAT_CALL:
                return "write a fixed message and pass its values in `fields=` (DEBUG and VERBOSE may keep an f-string)"
            case LogCallRule.NON_LITERAL:
                return "write the message as a literal at the call and pass what varies in `fields=`"
            case LogCallRule.MARKUP:
                return "drop the tag: the console colours a value by its field's name, or draws a named layout"
            case LogCallRule.LOWERCASE_START:
                return "start the message with a capital letter, its subject first"
            case LogCallRule.TRAILING_PERIOD:
                return "end the message with no period and no ellipsis"
            case LogCallRule.BACKTICK:
                return "write the message as plain prose: what a backtick would quote rides in a field"
            case LogCallRule.IDENTIFIER:
                return "say it in words and carry the identifier as a field's value, an environment variable's name in `env_var` for instance"
            case LogCallRule.LENGTH:
                return (
                    f"say what happened in one sentence of at most {MAX_MESSAGE_LENGTH} characters, "
                    "the values in `fields=` and the advice in `user_action`"
                )
            case LogCallRule.SPLICED_EXCEPTION:
                return (
                    "write a fixed message and pass the exception in `fields=` as `**error_fields(exc=...)`, "
                    "or with `include_exception=True` at ERROR and above"
                )


class RuleBreach(NamedTuple):
    """One rule a call breaks, with what the reader needs to find it."""

    rule: LogCallRule
    detail: str


class OffendingCall(NamedTuple):
    """One facade call that breaks at least one rule.

    Attributes:
        relative_path: The source file, posix, relative to the repo root.
        qualified_name: The enclosing classes and functions joined by dots, or ``<module>``.
        lineno: The call's line, for the report only: it never enters the baseline.
        signature: The call's identity in the baseline: its method, its message's source text, the rules it breaks
            and the bindings the guard read to judge it.
        breaches: Every rule the call breaks.
    """

    relative_path: str
    qualified_name: str
    lineno: int
    signature: str
    breaches: tuple[RuleBreach, ...]

    @property
    def key(self) -> str:
        """The baseline key: ``<relative_path>::<qualified_name>``."""
        return f"{self.relative_path}::{self.qualified_name}"


class StaleEntry(NamedTuple):
    """A baseline signature that no call matches any more."""

    key: str
    signature: str


class BaselineComparison(NamedTuple):
    """What the tree and the baseline disagree on; both lists empty is a pass."""

    unlisted: list[OffendingCall]
    stale: list[StaleEntry]

    @property
    def is_clean(self) -> bool:
        return not self.unlisted and not self.stale


class BaselineGrowth(NamedTuple):
    """A signature the working baseline lists more times than the trusted one does: an entry added since."""

    key: str
    signature: str
    trusted_count: int
    working_count: int


# --------------------------------------------------------------------------------------
# Markup: what Rich would read as console markup in a piece of text
#
# The one reading of a markup tag in the repo's checks: the guard applies it to a call's literal text, and the
# live-run tests to the messages a run logs. A tag-shaped span is not markup by its shape alone. Rich's tag pattern
# also matches the `[int]` of `list[int]`, a `[cycle]` marker and a backend's table, `[openai]`, yet none of them
# names a style, and a message holding one prints as written. So a tag counts as markup only when Rich would style
# with it: a closing tag, `[/]` or `[/red]`; an `@` handler, `[@click=app.bell]`; or an opening tag whose text Rich
# parses as a style, `[bold]`, `[on blue]`, `[link=https://pipelex.com]`, or that names a style of Rich's default
# theme, `[repr.number]`. A tag escaped with a backslash is text, since Rich prints it as written.
# --------------------------------------------------------------------------------------


def _reads_as_style(*, tag_text: str) -> bool:
    """Whether Rich renders a tag's text as markup rather than leaving the reader a bracketed word.

    A closing tag and an ``@`` handler are markup whatever they name. An opening tag is markup when Rich parses its
    text as a style, ``name=parameters`` read the way Rich's own ``Tag`` reads it, or when it names a style of Rich's
    default theme.
    """
    if tag_text.startswith(("/", "@")):
        return True
    if tag_text in DEFAULT_STYLES:
        return True
    name, separator, parameters = tag_text.partition("=")
    style_text = f"{name} {parameters}" if separator else name
    try:
        Style.parse(style_text)
    except StyleSyntaxError:
        return False
    return True


def find_markup_tags(*, text: str) -> list[str]:
    """The unescaped tags in the text that Rich would apply as markup, in order, each as written.

    Tags are found by Rich's own pattern, ``rich.markup.RE_TAGS``: a run of backslashes, then a bracketed tag whose
    text opens with a lowercase letter, ``#``, ``/`` or ``@``.
    """
    if "[" not in text:
        return []
    tags: list[str] = []
    for match in RE_TAGS.finditer(text):
        full_text, escapes, tag_text = match.groups()
        # An odd run of backslashes escapes the tag, which then prints as written.
        if len(escapes) % 2 == 1:
            continue
        if _reads_as_style(tag_text=tag_text):
            tags.append(full_text[len(escapes) :])
    return tags


# --------------------------------------------------------------------------------------
# Source text, the same on every supported Python
# --------------------------------------------------------------------------------------


def _escape_literal_part(*, text: str) -> str:
    """A literal part of an f-string as the signature writes it: JSON's escapes, braces doubled."""
    return json.dumps(text, ensure_ascii=False)[1:-1].replace("{", "{{").replace("}", "}}")


def _render_joined_parts(*, values: list[ast.expr]) -> str:
    rendered: list[str] = []
    for value in values:
        match value:
            case ast.Constant(value=str() as text):
                rendered.append(_escape_literal_part(text=text))
            case ast.FormattedValue(value=inner, conversion=conversion, format_spec=format_spec):
                conversion_text = "" if conversion == -1 else f"!{chr(conversion)}"
                spec_text = ""
                if isinstance(format_spec, ast.JoinedStr):
                    spec_text = ":" + _render_joined_parts(values=format_spec.values)
                rendered.append("{" + render_source(expr=inner) + conversion_text + spec_text + "}")
            case _:
                rendered.append("{" + render_source(expr=value) + "}")
    return "".join(rendered)


class _JoinedStrFlattener(ast.NodeTransformer):
    """Replaces each f-string by a name whose text is the f-string's canonical rendering.

    An f-string is the one node whose ``ast.unparse`` rendering follows the parser's quoting rules, which PEP 701
    changed in Python 3.12, so the guard renders f-strings itself and a signature never depends on the interpreter
    the check runs on. Every other node ``ast.unparse`` renders through ``repr`` and fixed punctuation.
    """

    @override
    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:  # pylint: disable=invalid-name  # ast.NodeTransformer dispatch name
        return ast.Name(id='f"' + _render_joined_parts(values=node.values) + '"', ctx=ast.Load())


def render_source(*, expr: ast.expr) -> str:
    """An expression's source text, rendered the same on every supported Python."""
    if isinstance(expr, ast.JoinedStr):
        return 'f"' + _render_joined_parts(values=expr.values) + '"'
    flattened = _JoinedStrFlattener().visit(copy.deepcopy(expr))
    return ast.unparse(cast("ast.AST", flattened))


_OPERATOR_SYMBOLS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.MatMult: "@",
    ast.Div: "/",
    ast.Mod: "%",
    ast.Pow: "**",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.BitAnd: "&",
    ast.FloorDiv: "//",
}


def _operator_symbol(*, operator: ast.operator) -> str:
    return _OPERATOR_SYMBOLS.get(type(operator), type(operator).__name__)


# --------------------------------------------------------------------------------------
# Scopes, bindings and the flow between them, indexed once per module
# --------------------------------------------------------------------------------------


class _ScopeKind(StrEnum):
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"
    COMPREHENSION = "comprehension"

    @property
    def is_module(self) -> bool:
        match self:
            case _ScopeKind.MODULE:
                return True
            case _ScopeKind.FUNCTION | _ScopeKind.CLASS | _ScopeKind.COMPREHENSION:
                return False

    @property
    def is_class(self) -> bool:
        match self:
            case _ScopeKind.CLASS:
                return True
            case _ScopeKind.MODULE | _ScopeKind.FUNCTION | _ScopeKind.COMPREHENSION:
                return False

    @property
    def is_comprehension(self) -> bool:
        match self:
            case _ScopeKind.COMPREHENSION:
                return True
            case _ScopeKind.MODULE | _ScopeKind.FUNCTION | _ScopeKind.CLASS:
                return False

    @property
    def runs_when_called(self) -> bool:
        """Whether the scope's code runs whenever it is called, rather than once, where it is written."""
        match self:
            case _ScopeKind.FUNCTION:
                return True
            case _ScopeKind.MODULE | _ScopeKind.CLASS | _ScopeKind.COMPREHENSION:
                return False


class _OpaqueBinding(StrEnum):
    """What binds a name to a value the guard does not read, each written in a signature as ``<kind>``."""

    PARAMETER = "parameter"
    FOR_TARGET = "for target"
    WITH_TARGET = "with target"
    EXCEPT_TARGET = "except target"
    COMPREHENSION_TARGET = "comprehension target"
    MATCH_CAPTURE = "match capture"
    UNPACKING = "unpacking"
    IMPORT = "import"
    DEFINITION = "definition"
    ASSIGNMENT_TARGET = "assignment target"

    @property
    def placeholder(self) -> str:
        return f"<{self}>"


#: What a name the guard does not follow is written as in a signature: one captured from an enclosing function,
#: and one bound nowhere it is read from.
_CAPTURED_PLACEHOLDER = "<enclosing function>"
_UNBOUND_PLACEHOLDER = "<unbound>"


class _Binding:
    """One binding of a name: the value bound, the scope that value is read in, and how it binds.

    Compared by identity: two bindings of the same text on two lines are two bindings.

    Attributes:
        serial: The binding's rank in the walk, which orders the bindings of one line.
        value: The bound expression, ``None`` for an opaque binding.
        scope: The scope the value is evaluated in, which is where the names it reads resolve: the function a
            ``global`` assignment is written in, or the comprehension holding a ``:=``, rather than the scope the
            name lands in.
        lineno: The line, for the report only.
        operator: The operator of an augmented assignment, ``None`` for a plain one.
        prior: The target of an augmented assignment, the read of the value it updates.
        opaque: What binds the name when the guard does not read the value: a parameter, a loop target, an import.
        import_path: The dotted path an import binds the name to, which tells the facade apart.
    """

    def __init__(
        self,
        *,
        serial: int,
        value: ast.expr | None,
        scope: _Scope,
        lineno: int,
        operator: ast.operator | None = None,
        prior: ast.Name | None = None,
        opaque: _OpaqueBinding | None = None,
        import_path: str | None = None,
    ) -> None:
        self.serial = serial
        self.value = value
        self.scope = scope
        self.lineno = lineno
        self.operator = operator
        self.prior = prior
        self.opaque = opaque
        self.import_path = import_path

    def render(self, *, name: str) -> str:
        """The binding as a signature writes it: its source text, never its line."""
        if self.opaque is not None or self.value is None:
            return f"{name} = {(self.opaque or _OpaqueBinding.ASSIGNMENT_TARGET).placeholder}"
        if self.operator is not None:
            return f"{name} {_operator_symbol(operator=self.operator)}= {render_source(expr=self.value)}"
        return f"{name} = {render_source(expr=self.value)}"


class _EntryPoint:
    """Where a scope written in the module starts to run in the module's flow, and the module bindings it can see.

    A class body runs once, where its statement stands, and sees ``at_entry``. A function may be called at any time
    once it is defined, and also sees ``after``: every module binding made from then on, in any order.
    """

    def __init__(self) -> None:
        self.at_entry: dict[str, set[_Binding]] = {}
        self.after: dict[str, set[_Binding]] = {}


class _Scope:
    """One scope of a module: the names it binds, by Python's rules, and the flow of its statements."""

    def __init__(self, *, kind: _ScopeKind, parent: _Scope | None) -> None:
        self.kind = kind
        self.parent = parent
        self.bindings: dict[str, list[_Binding]] = {}
        # Every name a binding operation targets here, `del` and a bare annotation included: those make a name
        # local without giving it a value.
        self.bound_names: set[str] = set()
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()
        # The bindings another scope makes here through `global` or `nonlocal`, which run whenever it is called.
        self.moved_bindings: dict[str, list[_Binding]] = {}
        # The flow of a scope that is not a comprehension: the events of its statements, and the stack of event lists
        # the walk is filling. A comprehension's flow is part of the scope it is written in.
        self.events: list[_Event] = []
        self.sinks: list[list[_Event]] = [self.events]
        # Where the scope starts to run in the module's flow, and whether it runs there or whenever it is called.
        self.entry: _EntryPoint | None = None
        self.runs_later = False

    def bind(self, *, name: str, binding: _Binding) -> None:
        self.bindings.setdefault(name, []).append(binding)
        self.bound_names.add(name)

    def owns(self, *, name: str) -> bool:
        """Whether the name is local to this scope: bound here and declared neither ``global`` nor ``nonlocal``."""
        return name in self.bound_names and name not in self.global_names and name not in self.nonlocal_names

    @property
    def statement_scope(self) -> _Scope:
        """The nearest scope that is not a comprehension: where a ``:=`` in a comprehension binds its name."""
        scope = self
        while scope.kind.is_comprehension and scope.parent is not None:
            scope = scope.parent
        return scope


#: Where a name read in a scope resolves: the scope whose bindings it reads, or the placeholder of a name not followed.
_Location: TypeAlias = _Scope | str

#: What a name read resolves to: the placeholder of a name not followed, or the bindings that can reach the read, in
#: source order, none when no binding does.
_Reach: TypeAlias = str | list[_Binding]


# ---- the flow of a scope, as events ------------------------------------------------


class _JumpKind(StrEnum):
    RETURN = "return"
    RAISE = "raise"
    BREAK = "break"
    CONTINUE = "continue"


class _Read(NamedTuple):
    """A name read: the bindings that reach it are recorded against its node."""

    node: ast.Name
    name: str


class _Bind(NamedTuple):
    """A name bound, replacing whatever it held."""

    name: str
    binding: _Binding


class _Kill(NamedTuple):
    """A name deleted, or an except target cleared as its handler ends."""

    name: str


class _Enter(NamedTuple):
    """The point of the module's flow a scope written there starts to run from."""

    point: _EntryPoint


class _Branch(NamedTuple):
    """Paths of which exactly one runs; an empty path is the way around the others."""

    paths: tuple[list[_Event], ...]


class _Loop(NamedTuple):
    """A loop: its test runs before each pass and before it ends, its body any number of times, its ``else`` on a normal end."""

    test: list[_Event]
    body: list[_Event]
    orelse: list[_Event]


class _Try(NamedTuple):
    """A ``try``, or a ``with`` statement, whose context manager may swallow what its body raises."""

    body: list[_Event]
    handlers: tuple[list[_Event], ...]
    orelse: list[_Event]
    final: list[_Event]


class _Match(NamedTuple):
    """A ``match``: each case's pattern and guard, then its body, and whether its last case always matches."""

    cases: tuple[tuple[list[_Event], list[_Event]], ...]
    is_exhaustive: bool


class _Jump(NamedTuple):
    """A ``return``, ``raise``, ``break`` or ``continue``: nothing after it in its block runs."""

    kind: _JumpKind


_Event: TypeAlias = _Read | _Bind | _Kill | _Enter | _Branch | _Loop | _Try | _Match | _Jump

#: The bindings that can reach a point for one name, ``None`` standing for a path on which the name holds nothing.
_Reaching: TypeAlias = frozenset[_Binding | None]

_NOTHING: _Reaching = frozenset({None})


def _union(*, sets: Iterable[_Reaching]) -> _Reaching:
    merged: set[_Binding | None] = set()
    for reaching in sets:
        merged.update(reaching)
    return frozenset(merged)


class _FlowState:
    """What reaches one point of a scope's flow: each name's bindings, and the entry points already passed."""

    def __init__(self, *, names: dict[str, _Reaching], active: frozenset[_EntryPoint]) -> None:
        self.names = names
        self.active = active

    def reaching(self, *, name: str) -> _Reaching:
        return self.names.get(name, _NOTHING)

    def copy(self) -> _FlowState:
        return _FlowState(names=dict(self.names), active=self.active)

    def is_same_as(self, *, other: _FlowState) -> bool:
        return self.names == other.names and self.active == other.active


def _joined(*, states: Iterable[_FlowState | None]) -> _FlowState | None:
    """The state where paths meet: each name holding what it holds on any of them; ``None`` when no path gets there."""
    live = [state for state in states if state is not None]
    if not live:
        return None
    if len(live) == 1:
        return live[0].copy()
    every_name: set[str] = set()
    for state in live:
        every_name.update(state.names)
    names = {name: _union(sets=(state.reaching(name=name) for state in live)) for name in every_name}
    active: set[_EntryPoint] = set()
    for state in live:
        active.update(state.active)
    return _FlowState(names=names, active=frozenset(active))


class _LoopFrame:
    """A loop being run: the states its ``break`` and ``continue`` statements leave with."""

    def __init__(self) -> None:
        self.jumps: dict[_JumpKind, list[_FlowState]] = {}


class _RaiseFrame:
    """A region whose exceptions a handler or a ``finally`` takes over: every state reached in it, joined.

    A ``finally`` region also keeps the jumps that leave through it, which resume once the ``finally`` has run.
    """

    def __init__(self, *, state: _FlowState, has_finally: bool) -> None:
        self.state = state.copy()
        self.has_finally = has_finally
        self.jumps: dict[_JumpKind, list[_FlowState]] = {}

    def note(self, *, name: str, reaching: _Reaching) -> None:
        self.state.names[name] = self.state.reaching(name=name) | reaching


class _FlowRunner:
    """Runs one scope's flow, recording at each name read every binding that can reach it.

    A loop runs until the state at its head stops growing, so a binding later in its body reaches a read earlier in it.
    """

    def __init__(self, *, recorded: dict[ast.Name, set[_Binding | None]]) -> None:
        self._recorded = recorded
        self._frames: list[_LoopFrame | _RaiseFrame] = []

    def run(self, *, events: Sequence[_Event], state: _FlowState | None) -> _FlowState | None:
        """The state after the events, ``None`` when no path gets through them. The state given is consumed."""
        for event in events:
            if state is None:
                return None
            state = self._step(event=event, state=state)
        return state

    def _step(self, *, event: _Event, state: _FlowState) -> _FlowState | None:
        match event:
            case _Read(node=node, name=name):
                self._recorded.setdefault(node, set()).update(state.reaching(name=name))
                return state
            case _Bind(name=name, binding=binding):
                state.names[name] = frozenset({binding})
                for point in state.active:
                    point.after.setdefault(name, set()).add(binding)
                self._note(name=name, reaching=frozenset({binding}))
                return state
            case _Kill(name=name):
                state.names.pop(name, None)
                self._note(name=name, reaching=_NOTHING)
                return state
            case _Enter(point=point):
                for name, reaching in state.names.items():
                    point.at_entry.setdefault(name, set()).update(binding for binding in reaching if binding is not None)
                state.active |= {point}
                for frame in self._raise_frames():
                    frame.state.active |= {point}
                return state
            case _Branch(paths=paths):
                return _joined(states=[self.run(events=path, state=state.copy()) for path in paths])
            case _Loop():
                return self._run_loop(loop=event, state=state)
            case _Try():
                return self._run_try(statement=event, state=state)
            case _Match():
                return self._run_match(statement=event, state=state)
            case _Jump(kind=kind):
                self._jump(kind=kind, state=state)
                return None

    def _raise_frames(self) -> list[_RaiseFrame]:
        return [frame for frame in self._frames if isinstance(frame, _RaiseFrame)]

    def _note(self, *, name: str, reaching: _Reaching) -> None:
        """An exception may be raised once a name changes: every enclosing handler and ``finally`` may see it."""
        for frame in self._raise_frames():
            frame.note(name=name, reaching=reaching)

    def _jump(self, *, kind: _JumpKind, state: _FlowState) -> None:
        """Hand a jump's state to what it resumes at: the innermost ``finally`` it leaves through, else its loop."""
        match kind:
            case _JumpKind.RAISE:
                # Every state a region reaches is already noted in the frames that take its exceptions over.
                return
            case _JumpKind.RETURN:
                frames = [frame for frame in self._raise_frames() if frame.has_finally]
                if frames:
                    frames[-1].jumps.setdefault(kind, []).append(state.copy())
            case _JumpKind.BREAK | _JumpKind.CONTINUE:
                for frame in reversed(self._frames):
                    if isinstance(frame, _LoopFrame) or frame.has_finally:
                        frame.jumps.setdefault(kind, []).append(state.copy())
                        return

    def _run_loop(self, *, loop: _Loop, state: _FlowState) -> _FlowState | None:
        head = state.copy()
        while True:
            frame = _LoopFrame()
            self._frames.append(frame)
            tested = self.run(events=loop.test, state=head.copy())
            body_end = self.run(events=loop.body, state=tested.copy() if tested is not None else None)
            self._frames.pop()
            next_head = _joined(states=[state, body_end, *frame.jumps.get(_JumpKind.CONTINUE, [])])
            if next_head is None or next_head.is_same_as(other=head):
                break
            head = next_head
        finished = self.run(events=loop.orelse, state=tested)
        return _joined(states=[finished, *frame.jumps.get(_JumpKind.BREAK, [])])

    def _run_try(self, *, statement: _Try, state: _FlowState) -> _FlowState | None:
        """The handlers start from any state the body reached, and a ``finally`` runs on every way out."""
        finally_frame = _RaiseFrame(state=state, has_finally=True) if statement.final else None
        if finally_frame is not None:
            self._frames.append(finally_frame)
        body_frame = _RaiseFrame(state=state, has_finally=False)
        self._frames.append(body_frame)
        body_end = self.run(events=statement.body, state=state)
        self._frames.pop()
        handler_ends = [self.run(events=handler, state=body_frame.state.copy()) for handler in statement.handlers]
        finished = _joined(states=[self.run(events=statement.orelse, state=body_end), *handler_ends])
        if finally_frame is None:
            return finished
        self._frames.pop()
        # After an exception the `finally` runs and the exception goes on; after a jump it runs and the jump resumes.
        self.run(events=statement.final, state=finally_frame.state.copy())
        for kind, jump_states in finally_frame.jumps.items():
            resumed = self.run(events=statement.final, state=_joined(states=jump_states))
            if resumed is not None:
                self._jump(kind=kind, state=resumed)
        return self.run(events=statement.final, state=finished)

    def _run_match(self, *, statement: _Match, state: _FlowState) -> _FlowState | None:
        """Each case is tried from what the failed ones left: a pattern may bind its captures and still fail."""
        trying = state
        ends: list[_FlowState | None] = []
        for pattern, body in statement.cases:
            matched = self.run(events=pattern, state=trying.copy())
            if matched is None:
                continue
            ends.append(self.run(events=body, state=matched.copy()))
            trying = _joined(states=[trying, matched]) or trying
        if not statement.is_exhaustive:
            ends.append(trying)
        return _joined(states=ends)


def _is_irrefutable(*, case: ast.match_case) -> bool:
    """Whether a case always matches: a bare capture or ``_``, with no guard."""
    return case.guard is None and isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None


# ---- the index -------------------------------------------------------------------------


class _ScopeIndex:
    """Every scope of one module with the names it binds and the flow of its statements, built in one walk, then
    each flow run once, which records the bindings that can reach each name read.

    The flow follows Python's control flow: a binding reaches a read along straight-line code until another
    replaces it, the branches of an ``if``, a ``try`` or a ``match`` each bring theirs, a loop brings the bindings
    of its later passes, and code after a ``return``, a ``raise``, a ``break`` or a ``continue`` is reached by
    nothing.
    """

    def __init__(self, *, module: ast.Module, package: str) -> None:
        self.module_scope = _Scope(kind=_ScopeKind.MODULE, parent=None)
        self.call_scopes: dict[ast.Call, _Scope] = {}
        # The scope each name is read in, so a name met anywhere in an expression, a lambda's body included, resolves.
        self.read_scopes: dict[ast.Name, _Scope] = {}
        self._package = package
        self._scopes: list[_Scope] = [self.module_scope]
        self._serials = itertools.count()
        self._recorded: dict[ast.Name, set[_Binding | None]] = {}
        for statement in module.body:
            self._visit(node=statement, scope=self.module_scope)
        self._apply_declarations()
        for scope in self._scopes:
            if not scope.kind.is_comprehension:
                _FlowRunner(recorded=self._recorded).run(events=scope.events, state=_FlowState(names={}, active=frozenset()))

    # ---- the walk ---------------------------------------------------------------------

    def _new_binding(
        self,
        *,
        value: ast.expr | None,
        scope: _Scope,
        lineno: int,
        operator: ast.operator | None = None,
        prior: ast.Name | None = None,
        opaque: _OpaqueBinding | None = None,
        import_path: str | None = None,
    ) -> _Binding:
        return _Binding(
            serial=next(self._serials),
            value=value,
            scope=scope,
            lineno=lineno,
            operator=operator,
            prior=prior,
            opaque=opaque,
            import_path=import_path,
        )

    def _nested_scope(self, *, kind: _ScopeKind, parent: _Scope) -> _Scope:
        """A scope written in ``parent``, with the point of the module's flow it starts to run from."""
        scope = _Scope(kind=kind, parent=parent)
        self._scopes.append(scope)
        flow = parent.statement_scope
        if flow.kind.is_module and not kind.is_comprehension:
            point = _EntryPoint()
            self._emit(scope=flow, event=_Enter(point=point))
            scope.entry = point
        else:
            scope.entry = flow.entry
        scope.runs_later = flow.runs_later or kind.runs_when_called
        return scope

    @staticmethod
    def _emit(*, scope: _Scope, event: _Event) -> None:
        scope.statement_scope.sinks[-1].append(event)

    @contextmanager
    def _sink(self, *, scope: _Scope) -> Generator[list[_Event]]:
        """Collect the events the walk emits in a scope's flow, for one block of a compound statement."""
        events: list[_Event] = []
        flow = scope.statement_scope
        flow.sinks.append(events)
        try:
            yield events
        finally:
            flow.sinks.pop()

    def _collected(self, *, nodes: Iterable[ast.AST | None], scope: _Scope) -> list[_Event]:
        with self._sink(scope=scope) as events:
            self._visit_all(nodes=nodes, scope=scope)
        return events

    def _bind(self, *, name: str, owner: _Scope, binding: _Binding) -> None:
        """Bind a name in the scope that owns it and, unless that is a comprehension, in that scope's flow."""
        owner.bind(name=name, binding=binding)
        if not owner.kind.is_comprehension:
            self._emit(scope=owner, event=_Bind(name=name, binding=binding))

    def _visit_all(self, *, nodes: Iterable[ast.AST | None], scope: _Scope) -> None:
        for node in nodes:
            if node is not None:
                self._visit(node=node, scope=scope)

    def _visit(self, *, node: ast.AST, scope: _Scope) -> None:
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef():
                self._visit_all(nodes=node.decorator_list, scope=scope)
                self._visit_signature_outside(arguments=node.args, scope=scope)
                self._visit_all(nodes=[node.returns, *getattr(node, "type_params", [])], scope=scope)
                function_scope = self._nested_scope(kind=_ScopeKind.FUNCTION, parent=scope)
                self._bind_parameters(arguments=node.args, scope=function_scope)
                self._visit_all(nodes=node.body, scope=function_scope)
                self._bind_opaque(name=node.name, kind=_OpaqueBinding.DEFINITION, scope=scope, lineno=node.lineno)
            case ast.Lambda():
                self._visit_signature_outside(arguments=node.args, scope=scope)
                lambda_scope = self._nested_scope(kind=_ScopeKind.FUNCTION, parent=scope)
                self._bind_parameters(arguments=node.args, scope=lambda_scope)
                self._visit(node=node.body, scope=lambda_scope)
            case ast.ClassDef():
                self._visit_all(nodes=[*node.decorator_list, *node.bases, *node.keywords, *getattr(node, "type_params", [])], scope=scope)
                class_scope = self._nested_scope(kind=_ScopeKind.CLASS, parent=scope)
                self._visit_all(nodes=node.body, scope=class_scope)
                self._bind_opaque(name=node.name, kind=_OpaqueBinding.DEFINITION, scope=scope, lineno=node.lineno)
            case ast.ListComp(elt=elt, generators=generators) | ast.SetComp(elt=elt, generators=generators):
                self._visit_comprehension(generators=generators, results=[elt], scope=scope)
            case ast.GeneratorExp(elt=elt, generators=generators):
                self._visit_comprehension(generators=generators, results=[elt], scope=scope)
            case ast.DictComp(key=key, value=value, generators=generators):
                self._visit_comprehension(generators=generators, results=[key, value], scope=scope)
            case ast.Assign(targets=targets, value=value):
                self._visit(node=value, scope=scope)
                for target in targets:
                    if isinstance(target, ast.Name):
                        self._bind(name=target.id, owner=scope, binding=self._new_binding(value=value, scope=scope, lineno=node.lineno))
                    else:
                        self._bind_target(target=target, kind=_OpaqueBinding.UNPACKING, scope=scope)
            case ast.AnnAssign(target=target, annotation=annotation, value=value):
                self._visit_all(nodes=[annotation, value], scope=scope)
                if isinstance(target, ast.Name):
                    if value is None:
                        # A bare annotation binds no value but makes the name local, by Python's rules.
                        scope.bound_names.add(target.id)
                    else:
                        self._bind(name=target.id, owner=scope, binding=self._new_binding(value=value, scope=scope, lineno=node.lineno))
                else:
                    self._visit(node=target, scope=scope)
            case ast.AugAssign(target=ast.Name(id=name) as target, op=operator, value=value):
                # The value updated is read where the update stands.
                self._emit(scope=scope, event=_Read(node=target, name=name))
                self._visit(node=value, scope=scope)
                binding = self._new_binding(value=value, scope=scope, lineno=node.lineno, operator=operator, prior=target)
                self._bind(name=name, owner=scope, binding=binding)
            case ast.NamedExpr(target=ast.Name(id=name), value=value):
                self._visit(node=value, scope=scope)
                # A `:=` in a comprehension binds in the scope the comprehension is written in, its value read where it stands.
                self._bind(name=name, owner=scope.statement_scope, binding=self._new_binding(value=value, scope=scope, lineno=node.lineno))
            case ast.If(test=test, body=body, orelse=orelse):
                self._visit(node=test, scope=scope)
                self._emit(scope=scope, event=_Branch(paths=(self._collected(nodes=body, scope=scope), self._collected(nodes=orelse, scope=scope))))
            case ast.While(test=test, body=body, orelse=orelse):
                loop = _Loop(
                    test=self._collected(nodes=[test], scope=scope),
                    body=self._collected(nodes=body, scope=scope),
                    orelse=self._collected(nodes=orelse, scope=scope),
                )
                self._emit(scope=scope, event=loop)
            case (
                ast.For(target=target, iter=iterable, body=body, orelse=orelse) | ast.AsyncFor(target=target, iter=iterable, body=body, orelse=orelse)
            ):
                self._visit(node=iterable, scope=scope)
                with self._sink(scope=scope) as loop_body:
                    self._bind_target(target=target, kind=_OpaqueBinding.FOR_TARGET, scope=scope)
                    self._visit_all(nodes=body, scope=scope)
                self._emit(scope=scope, event=_Loop(test=[], body=loop_body, orelse=self._collected(nodes=orelse, scope=scope)))
            case ast.With(items=items, body=body) | ast.AsyncWith(items=items, body=body):
                for item in items:
                    self._visit(node=item.context_expr, scope=scope)
                    if item.optional_vars is not None:
                        self._bind_target(target=item.optional_vars, kind=_OpaqueBinding.WITH_TARGET, scope=scope)
                # A context manager may swallow what its body raises, so what follows may see any state the body reached.
                self._emit(scope=scope, event=_Try(body=self._collected(nodes=body, scope=scope), handlers=([],), orelse=[], final=[]))
            case (
                ast.Try(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)
                | ast.TryStar(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)
            ):
                statement = _Try(
                    body=self._collected(nodes=body, scope=scope),
                    handlers=tuple(self._handler_events(handler=handler, scope=scope) for handler in handlers),
                    orelse=self._collected(nodes=orelse, scope=scope),
                    final=self._collected(nodes=finalbody, scope=scope),
                )
                self._emit(scope=scope, event=statement)
            case ast.Match(subject=subject, cases=cases):
                self._visit(node=subject, scope=scope)
                match_cases = tuple(
                    (self._collected(nodes=[case.pattern, case.guard], scope=scope), self._collected(nodes=case.body, scope=scope)) for case in cases
                )
                self._emit(scope=scope, event=_Match(cases=match_cases, is_exhaustive=bool(cases) and _is_irrefutable(case=cases[-1])))
            case ast.Return(value=value):
                self._visit_all(nodes=[value], scope=scope)
                self._emit(scope=scope, event=_Jump(kind=_JumpKind.RETURN))
            case ast.Raise(exc=exception, cause=cause):
                self._visit_all(nodes=[exception, cause], scope=scope)
                self._emit(scope=scope, event=_Jump(kind=_JumpKind.RAISE))
            case ast.Break():
                self._emit(scope=scope, event=_Jump(kind=_JumpKind.BREAK))
            case ast.Continue():
                self._emit(scope=scope, event=_Jump(kind=_JumpKind.CONTINUE))
            case ast.Import() | ast.ImportFrom():
                self._bind_imports(statement=node, scope=scope)
            case ast.Global(names=names):
                # A module-level `global` changes nothing.
                if not scope.kind.is_module:
                    scope.global_names.update(names)
            case ast.Nonlocal(names=names):
                scope.nonlocal_names.update(names)
            case ast.MatchAs(pattern=pattern, name=capture_name):
                if pattern is not None:
                    self._visit(node=pattern, scope=scope)
                if capture_name is not None:
                    self._bind_opaque(name=capture_name, kind=_OpaqueBinding.MATCH_CAPTURE, scope=scope, lineno=node.lineno)
            case ast.MatchStar(name=capture_name):
                if capture_name is not None:
                    self._bind_opaque(name=capture_name, kind=_OpaqueBinding.MATCH_CAPTURE, scope=scope, lineno=node.lineno)
            case ast.MatchMapping(keys=keys, patterns=patterns, rest=rest):
                self._visit_all(nodes=[*keys, *patterns], scope=scope)
                if rest is not None:
                    self._bind_opaque(name=rest, kind=_OpaqueBinding.MATCH_CAPTURE, scope=scope, lineno=node.lineno)
            case ast.BoolOp(values=values):
                # Each operand after the first runs only when the ones before it did not decide.
                self._visit(node=values[0], scope=scope)
                self._visit_short_circuit(values=values[1:], scope=scope)
            case ast.IfExp(test=test, body=body, orelse=orelse):
                self._visit(node=test, scope=scope)
                self._emit(
                    scope=scope, event=_Branch(paths=(self._collected(nodes=[body], scope=scope), self._collected(nodes=[orelse], scope=scope)))
                )
            case ast.Name(id=name, ctx=ast.Load()):
                self.read_scopes[node] = scope
                self._emit(scope=scope, event=_Read(node=node, name=name))
            case ast.Name(id=name, ctx=ast.Store()):
                self._bind_opaque(name=name, kind=_OpaqueBinding.ASSIGNMENT_TARGET, scope=scope, lineno=node.lineno)
            case ast.Name(id=name, ctx=ast.Del()):
                # `del` makes a name local without giving it a value, by Python's rules, and empties it.
                scope.bound_names.add(name)
                self._emit(scope=scope, event=_Kill(name=name))
            case ast.Call():
                self.call_scopes[node] = scope
                self._visit_all(nodes=ast.iter_child_nodes(node), scope=scope)
            case _:
                self._visit_all(nodes=ast.iter_child_nodes(node), scope=scope)

    def _visit_short_circuit(self, *, values: list[ast.expr], scope: _Scope) -> None:
        if not values:
            return
        with self._sink(scope=scope) as evaluated:
            self._visit(node=values[0], scope=scope)
            self._visit_short_circuit(values=values[1:], scope=scope)
        self._emit(scope=scope, event=_Branch(paths=(evaluated, [])))

    def _handler_events(self, *, handler: ast.ExceptHandler, scope: _Scope) -> list[_Event]:
        with self._sink(scope=scope) as events:
            self._visit_all(nodes=[handler.type], scope=scope)
            if handler.name is not None:
                self._bind_opaque(name=handler.name, kind=_OpaqueBinding.EXCEPT_TARGET, scope=scope, lineno=handler.lineno)
            self._visit_all(nodes=handler.body, scope=scope)
            if handler.name is not None:
                # Python deletes an except target as its handler ends.
                self._emit(scope=scope, event=_Kill(name=handler.name))
        return events

    def _visit_signature_outside(self, *, arguments: ast.arguments, scope: _Scope) -> None:
        """A signature's defaults and annotations, which are evaluated in the scope the definition is written in."""
        every_argument = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg]
        annotations = [argument.annotation for argument in every_argument if argument is not None]
        self._visit_all(nodes=[*arguments.defaults, *arguments.kw_defaults, *annotations], scope=scope)

    def _bind_parameters(self, *, arguments: ast.arguments, scope: _Scope) -> None:
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg):
            if argument is not None:
                self._bind_opaque(name=argument.arg, kind=_OpaqueBinding.PARAMETER, scope=scope, lineno=argument.lineno)

    def _visit_comprehension(self, *, generators: list[ast.comprehension], results: list[ast.expr], scope: _Scope) -> None:
        """A comprehension: its first iterable is read in the enclosing scope, everything else in a scope of its own.

        Its body runs any number of times, as a loop of the flow it is written in, where its `:=` bind.
        """
        self._visit(node=generators[0].iter, scope=scope)
        comprehension_scope = self._nested_scope(kind=_ScopeKind.COMPREHENSION, parent=scope)
        with self._sink(scope=scope) as body:
            for index_generator, generator in enumerate(generators):
                if index_generator > 0:
                    self._visit(node=generator.iter, scope=comprehension_scope)
                self._bind_target(target=generator.target, kind=_OpaqueBinding.COMPREHENSION_TARGET, scope=comprehension_scope)
                self._visit_all(nodes=generator.ifs, scope=comprehension_scope)
            self._visit_all(nodes=results, scope=comprehension_scope)
        self._emit(scope=scope, event=_Loop(test=[], body=body, orelse=[]))

    def _bind_target(self, *, target: ast.expr, kind: _OpaqueBinding, scope: _Scope) -> None:
        """The names an assignment target binds: a name, reached through tuples, lists and starred parts.

        An attribute or a subscript rebinds no name, ``cache[msg] = 1`` leaving ``msg`` as it was: its parts are read.
        """
        match target:
            case ast.Name(id=name):
                self._bind_opaque(name=name, kind=kind, scope=scope, lineno=target.lineno)
            case ast.Tuple(elts=elements) | ast.List(elts=elements):
                for element in elements:
                    self._bind_target(target=element, kind=kind, scope=scope)
            case ast.Starred(value=value):
                self._bind_target(target=value, kind=kind, scope=scope)
            case _:
                self._visit(node=target, scope=scope)

    def _bind_opaque(self, *, name: str, kind: _OpaqueBinding, scope: _Scope, lineno: int, import_path: str | None = None) -> None:
        self._bind(name=name, owner=scope, binding=self._new_binding(value=None, scope=scope, lineno=lineno, opaque=kind, import_path=import_path))

    def _bind_imports(self, *, statement: ast.Import | ast.ImportFrom, scope: _Scope) -> None:
        """The names an import binds, each with the dotted path it binds them to.

        ``import a.b`` binds ``a`` to ``a``, ``import a.b as x`` binds ``x`` to ``a.b``, ``from a import b as c`` binds
        ``c`` to ``a.b``, a relative import resolves against the module's package, and a star import from a module that
        exports the facade binds its name.
        """
        match statement:
            case ast.Import(names=aliases):
                for alias in aliases:
                    bound_name = alias.asname or alias.name.partition(".")[0]
                    module_path = alias.name if alias.asname else bound_name
                    self._bind_opaque(name=bound_name, kind=_OpaqueBinding.IMPORT, scope=scope, lineno=statement.lineno, import_path=module_path)
            case ast.ImportFrom(module=module, level=level, names=aliases):
                base = _absolute_module(module=module, level=level, package=self._package)
                for alias in aliases:
                    if alias.name == "*":
                        if base in FACADE_STAR_MODULES:
                            star_path = f"{base}.{FACADE_NAME}"
                            self._bind_opaque(
                                name=FACADE_NAME, kind=_OpaqueBinding.IMPORT, scope=scope, lineno=statement.lineno, import_path=star_path
                            )
                        continue
                    imported_path = f"{base}.{alias.name}" if base else None
                    self._bind_opaque(
                        name=alias.asname or alias.name, kind=_OpaqueBinding.IMPORT, scope=scope, lineno=statement.lineno, import_path=imported_path
                    )

    def _apply_declarations(self) -> None:
        """Move the bindings of a ``global`` or ``nonlocal`` name to the scope that owns it."""
        for scope in self._scopes:
            for name in sorted(scope.global_names):
                for binding in scope.bindings.pop(name, []):
                    self.module_scope.bind(name=name, binding=binding)
                    self.module_scope.moved_bindings.setdefault(name, []).append(binding)
            for name in sorted(scope.nonlocal_names):
                owner = self._nonlocal_owner(scope=scope, name=name)
                moved = scope.bindings.pop(name, [])
                if owner is not None:
                    for binding in moved:
                        owner.bind(name=name, binding=binding)
                        owner.moved_bindings.setdefault(name, []).append(binding)

    @staticmethod
    def _nonlocal_owner(*, scope: _Scope, name: str) -> _Scope | None:
        enclosing = scope.parent
        while enclosing is not None and not enclosing.kind.is_module:
            if not enclosing.kind.is_class and enclosing.owns(name=name):
                return enclosing
            enclosing = enclosing.parent
        return None

    # ---- name resolution --------------------------------------------------------------

    def locate(self, *, scope: _Scope, name: str) -> _Location:
        """Where a name read in a scope resolves, by Python's rules.

        Its own scope, a comprehension reading as part of the scope it is written in; then the enclosing functions,
        class bodies never among them, a name one of them binds being captured and not followed; then the module.
        """
        current = scope
        has_crossed_comprehension = False
        while current.kind.is_comprehension and not current.owns(name=name) and current.parent is not None:
            current = current.parent
            has_crossed_comprehension = True
        if name in current.global_names:
            return self._module_location(name=name)
        # A comprehension written in a class body does not see the class's names, as no nested scope does.
        if current.owns(name=name) and not (has_crossed_comprehension and current.kind.is_class):
            return current
        if name in current.nonlocal_names:
            return _CAPTURED_PLACEHOLDER
        enclosing = current.parent
        while enclosing is not None and not enclosing.kind.is_module:
            if not enclosing.kind.is_class:
                if name in enclosing.global_names:
                    return self._module_location(name=name)
                if enclosing.owns(name=name):
                    return _CAPTURED_PLACEHOLDER
            enclosing = enclosing.parent
        return self._module_location(name=name)

    def _module_location(self, *, name: str) -> _Location:
        return self.module_scope if self.module_scope.owns(name=name) else _UNBOUND_PLACEHOLDER

    def reaching(self, *, node: ast.Name, scope: _Scope) -> _Reach:
        """The bindings that can reach a name read in a scope, or the placeholder of a name the guard does not follow.

        A read of its own flow's name gets what the flow's run recorded there. A read of a module name from a scope
        written in the module gets what the module held where that scope starts to run, and, from a function, every
        module binding made once it is defined. A comprehension's target is any of its bindings. A binding another
        scope makes through ``global`` or ``nonlocal`` runs whenever that scope is called, so it reaches every read.
        """
        name = node.id
        location = self.locate(scope=scope, name=name)
        if isinstance(location, str):
            return location
        flow = scope.statement_scope
        found: set[_Binding] = set()
        if location.kind.is_comprehension:
            found.update(location.bindings.get(name, []))
        else:
            # A function that declares a module name `global` tracks its own bindings of it, in its flow.
            is_read_in_own_flow = location is flow or name in flow.global_names
            recorded: set[_Binding | None] = self._recorded.get(node, set()) if is_read_in_own_flow else {None}
            found.update(binding for binding in recorded if binding is not None)
            if None in recorded and location is not flow and flow.entry is not None:
                found.update(flow.entry.at_entry.get(name, set()))
                if flow.runs_later:
                    found.update(flow.entry.after.get(name, set()))
        found.update(binding for binding in location.moved_bindings.get(name, []) if binding.scope.statement_scope is not flow)
        return sorted(found, key=lambda binding: (binding.lineno, binding.serial))

    def possible_bindings(self, *, node: ast.Name, scope: _Scope) -> list[_Binding]:
        """The bindings a name may hold where it is read, a captured name's every binding included.

        How a call's receiver is read, and a name the exception rule follows: a name captured from an enclosing
        function may hold whatever that function binds it to.
        """
        reach = self.reaching(node=node, scope=scope)
        if not isinstance(reach, str):
            return reach
        if reach != _CAPTURED_PLACEHOLDER:
            return []
        enclosing = scope.statement_scope.parent
        while enclosing is not None and not enclosing.kind.is_module:
            if not enclosing.kind.is_class and enclosing.owns(name=node.id):
                return list(enclosing.bindings.get(node.id, []))
            enclosing = enclosing.parent
        return []


# --------------------------------------------------------------------------------------
# Reading a message
# --------------------------------------------------------------------------------------

#: The form a message expression takes: ``None`` when it is fixed, otherwise the rule it breaks and what it is,
#: as a noun phrase the report completes ("the message is an f-string").
_Form: TypeAlias = RuleBreach | None

#: The text a message can reach the console as, as runs of literal text: between two consecutive runs sits a value
#: the guard cannot read, so a markup tag is looked for within a run and never across one.
_Shape: TypeAlias = tuple[str, ...]

#: The shape of a value the guard cannot read.
_UNKNOWN_SHAPE: _Shape = ("", "")

#: The most shapes a `+` folds its operands into; past it, the operands are scanned apart, as they would be unread.
_MAX_FOLDED_SHAPES = 256

#: The bindings a reading is inside of, so a binding a loop feeds back into itself is read once.
_Seen: TypeAlias = frozenset[_Binding]


#: The bindings a name reaches a handled exception through, as a signature writes them, the last binding the exception's.
_Route: TypeAlias = tuple[str, ...]


class _Splice(NamedTuple):
    """A value a message splices into its text that reaches a handled exception.

    Attributes:
        source: The spliced value's source text, as the report names it.
        route: The bindings it reaches the exception through, which join the call's signature.
    """

    source: str
    route: _Route


def _folded(*, left: set[_Shape], right: set[_Shape]) -> set[_Shape]:
    """The shapes of a concatenation: each left text's last run joined to each right text's first run.

    Past the bound, the sides are kept apart as if a value the guard cannot read stood between them: each left text
    keeps its start and each right text its end, and no run joins across.
    """
    if len(left) * len(right) > _MAX_FOLDED_SHAPES:
        return {(*left_shape, "") for left_shape in left} | {("", *right_shape) for right_shape in right}
    return {(*left_shape[:-1], left_shape[-1] + right_shape[0], *right_shape[1:]) for left_shape, right_shape in itertools.product(left, right)}


def _short_source(*, expr: ast.expr, limit: int = 60) -> str:
    text = render_source(expr=expr)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_none(*, expr: ast.expr) -> bool:
    return isinstance(expr, ast.Constant) and expr.value is None


class _MessageReader:
    """Reads a message expression in the scope it is written in, through the bindings that reach the names it holds.

    Every binding it reads is recorded in ``trace``, as a signature writes it, so the identity of a call that breaks
    a rule changes whenever what it logs does.
    """

    def __init__(self, *, index: _ScopeIndex, trace: set[str]) -> None:
        self._index = index
        self.trace = trace

    def _reach(self, *, node: ast.Name, scope: _Scope) -> _Reach:
        """The bindings that reach a name, the placeholder of one not followed recorded in the trace."""
        reach = self._index.reaching(node=node, scope=scope)
        if isinstance(reach, str):
            self.trace.add(f"{node.id} = {reach}")
        elif not reach:
            self.trace.add(f"{node.id} = {_UNBOUND_PLACEHOLDER}")
        else:
            self.trace.update(binding.render(name=node.id) for binding in reach)
        return reach

    # ---- the form, for the interpolation rule -----------------------------------------

    def form(self, *, expr: ast.expr, scope: _Scope, seen: _Seen, allows_none: bool) -> _Form:
        """Whether a message expression is fixed, and if not, the rule it breaks.

        The outermost form names the rule: ``f"{x}" + "!"`` is a concatenation. A title may be statically ``None``.
        """
        match expr:
            case ast.Constant(value=str()):
                return None
            case ast.Constant(value=None) if allows_none:
                return None
            case ast.JoinedStr(values=values):
                if any(isinstance(value, ast.FormattedValue) for value in values):
                    return RuleBreach(rule=LogCallRule.F_STRING, detail="an f-string")
                return None
            case ast.BinOp(op=ast.Add(), left=left, right=right):
                left_form = self.form(expr=left, scope=scope, seen=seen, allows_none=False)
                right_form = self.form(expr=right, scope=scope, seen=seen, allows_none=False)
                if left_form is None and right_form is None:
                    return None
                return RuleBreach(rule=LogCallRule.CONCATENATION, detail="a `+` concatenation")
            case ast.BinOp(op=ast.Mod()):
                return RuleBreach(rule=LogCallRule.PERCENT_FORMAT, detail="a `%` format")
            case ast.Call(func=ast.Attribute(attr="format")):
                return RuleBreach(rule=LogCallRule.FORMAT_CALL, detail="a `.format()` call")
            case ast.IfExp(body=body, orelse=orelse):
                # Both branches are read, so the trace holds what either binds.
                body_form = self.form(expr=body, scope=scope, seen=seen, allows_none=allows_none)
                orelse_form = self.form(expr=orelse, scope=scope, seen=seen, allows_none=allows_none)
                return body_form or orelse_form
            case ast.Name():
                return self._name_form(node=expr, scope=scope, seen=seen, allows_none=allows_none)
            case _:
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{_short_source(expr=expr)}`, not a literal")

    def _name_form(self, *, node: ast.Name, scope: _Scope, seen: _Seen, allows_none: bool) -> _Form:
        name = node.id
        reach = self._reach(node=node, scope=scope)
        if isinstance(reach, str):
            if reach == _CAPTURED_PLACEHOLDER:
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, captured from an enclosing function")
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound to no literal in its scope or at module level")
        if not reach:
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound to no literal in its scope or at module level")
        first_form: _Form = None
        for binding in reach:
            if binding in seen:
                # A binding a loop feeds back into itself, `msg = msg + "!"`: the bindings it started from decide.
                continue
            binding_form = self._binding_form(name=name, binding=binding, seen=seen | {binding}, allows_none=allows_none)
            first_form = first_form or binding_form
        return first_form

    def _binding_form(self, *, name: str, binding: _Binding, seen: _Seen, allows_none: bool) -> _Form:
        if binding.opaque is not None or binding.value is None:
            kind = binding.opaque or _OpaqueBinding.ASSIGNMENT_TARGET
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound at line {binding.lineno} as a {kind}, not to a literal")
        match binding.operator:
            case None:
                value_form = self.form(expr=binding.value, scope=binding.scope, seen=seen, allows_none=allows_none)
                if value_form is None:
                    return None
                return RuleBreach(rule=value_form.rule, detail=f"`{name}`, bound at line {binding.lineno} to {value_form.detail}")
            case ast.Add():
                # `msg += "!"` keeps a literal literal: the value it extends decides, then what extends it.
                prior_form = None if binding.prior is None else self._name_form(node=binding.prior, scope=binding.scope, seen=seen, allows_none=False)
                if prior_form is not None:
                    return prior_form
                if self.form(expr=binding.value, scope=binding.scope, seen=seen, allows_none=False) is None:
                    return None
                return RuleBreach(rule=LogCallRule.CONCATENATION, detail=f"`{name}`, extended with `+=` at line {binding.lineno}")
            case ast.Mod():
                return RuleBreach(rule=LogCallRule.PERCENT_FORMAT, detail=f"`{name}`, formatted with `%=` at line {binding.lineno}")
            case _:
                symbol = _operator_symbol(operator=binding.operator)
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, updated with `{symbol}=` at line {binding.lineno}")

    # ---- the shapes, for the markup rule ----------------------------------------------

    def shapes(self, *, expr: ast.expr, scope: _Scope, seen: _Seen) -> set[_Shape]:
        """The texts a message expression can reach the console as, its statically known concatenations folded."""
        match expr:
            case ast.Constant(value=str() as text):
                return {(text,)}
            case ast.Constant(value=None):
                return {("",)}
            case ast.JoinedStr(values=values):
                runs = [""]
                for value in values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        runs[-1] += value.value
                    else:
                        runs.append("")
                return {tuple(runs)}
            case ast.BinOp(op=ast.Add(), left=left, right=right):
                return _folded(left=self.shapes(expr=left, scope=scope, seen=seen), right=self.shapes(expr=right, scope=scope, seen=seen))
            case ast.BinOp(op=ast.Mod(), left=left):
                return self.shapes(expr=left, scope=scope, seen=seen)
            case ast.Call(func=ast.Attribute(attr="format", value=receiver)):
                return self.shapes(expr=receiver, scope=scope, seen=seen)
            case ast.IfExp(body=body, orelse=orelse):
                return self.shapes(expr=body, scope=scope, seen=seen) | self.shapes(expr=orelse, scope=scope, seen=seen)
            case ast.Name():
                return self._name_shapes(node=expr, scope=scope, seen=seen)
            case _:
                return {_UNKNOWN_SHAPE}

    def _name_shapes(self, *, node: ast.Name, scope: _Scope, seen: _Seen) -> set[_Shape]:
        """The texts a name can hold where it is read: those of each binding that can reach it."""
        reach = self._reach(node=node, scope=scope)
        if isinstance(reach, str) or not reach:
            return {_UNKNOWN_SHAPE}
        result: set[_Shape] = set()
        for binding in reach:
            if binding in seen:
                result.add(_UNKNOWN_SHAPE)
                continue
            result |= self._binding_shapes(binding=binding, seen=seen | {binding})
        return result

    def _binding_shapes(self, *, binding: _Binding, seen: _Seen) -> set[_Shape]:
        """The texts a binding gives its name: an augmented one updates the text that reaches it."""
        if binding.opaque is not None or binding.value is None:
            return {_UNKNOWN_SHAPE}
        match binding.operator:
            case None:
                return self.shapes(expr=binding.value, scope=binding.scope, seen=seen)
            case ast.Add():
                return _folded(
                    left=self._prior_shapes(binding=binding, seen=seen), right=self.shapes(expr=binding.value, scope=binding.scope, seen=seen)
                )
            case ast.Mod():
                return self._prior_shapes(binding=binding, seen=seen)
            case _:
                return {_UNKNOWN_SHAPE}

    def _prior_shapes(self, *, binding: _Binding, seen: _Seen) -> set[_Shape]:
        """The texts an augmented assignment updates: those reaching its target where it stands."""
        if binding.prior is None:
            return {_UNKNOWN_SHAPE}
        return self._name_shapes(node=binding.prior, scope=binding.scope, seen=seen)

    # ---- the spliced exceptions, for the exception rule -------------------------------

    def spliced_exceptions(self, *, expr: ast.expr, scope: _Scope, seen: _Seen) -> list[_Splice]:
        """The values a message expression splices into its text that reach a handled exception, in source order.

        The message is read the way ``shapes`` reads it, down to the values it splices: an f-string's placeholders,
        the values a ``%`` formats, the arguments of a ``.format()`` call, and any expression that is no literal
        text, the message itself included. A name is read through its bindings, a captured name through every binding
        of the function it is captured from, and a name bound by ``except ... as`` is the exception itself.
        """
        match expr:
            case ast.Constant():
                return []
            case ast.JoinedStr(values=values):
                placeholders = [value.value for value in values if isinstance(value, ast.FormattedValue)]
                return [splice for placeholder in placeholders for splice in self._splice(value=placeholder, seen=seen)]
            case ast.BinOp(op=ast.Add(), left=left, right=right):
                return [*self.spliced_exceptions(expr=left, scope=scope, seen=seen), *self.spliced_exceptions(expr=right, scope=scope, seen=seen)]
            case ast.BinOp(op=ast.Mod(), left=left, right=right):
                return [*self.spliced_exceptions(expr=left, scope=scope, seen=seen), *self._splice(value=right, seen=seen)]
            case ast.Call(func=ast.Attribute(attr="format", value=receiver), args=args, keywords=keywords):
                arguments = [*args, *(keyword.value for keyword in keywords)]
                spliced = [splice for argument in arguments for splice in self._splice(value=argument, seen=seen)]
                return [*self.spliced_exceptions(expr=receiver, scope=scope, seen=seen), *spliced]
            case ast.IfExp(body=body, orelse=orelse):
                return [*self.spliced_exceptions(expr=body, scope=scope, seen=seen), *self.spliced_exceptions(expr=orelse, scope=scope, seen=seen)]
            case ast.Name():
                return self._name_spliced_exceptions(node=expr, scope=scope, seen=seen)
            case _:
                return self._splice(value=expr, seen=seen)

    def _name_spliced_exceptions(self, *, node: ast.Name, scope: _Scope, seen: _Seen) -> list[_Splice]:
        """What a name splices through each binding it may hold, the binding leading every route it is on."""
        splices: list[_Splice] = []
        for binding in self._index.possible_bindings(node=node, scope=scope):
            if binding in seen:
                continue
            rendered = binding.render(name=node.id)
            if binding.opaque == _OpaqueBinding.EXCEPT_TARGET:
                splices.append(_Splice(source=node.id, route=(rendered,)))
                continue
            if binding.opaque is not None or binding.value is None:
                continue
            inner_seen = seen | {binding}
            found: list[_Splice] = []
            if binding.prior is not None:
                found.extend(self._name_spliced_exceptions(node=binding.prior, scope=binding.scope, seen=inner_seen))
            if binding.operator is None or isinstance(binding.operator, ast.Add):
                found.extend(self.spliced_exceptions(expr=binding.value, scope=binding.scope, seen=inner_seen))
            else:
                found.extend(self._splice(value=binding.value, seen=inner_seen))
            splices.extend(_Splice(source=splice.source, route=(rendered, *splice.route)) for splice in found)
        return splices

    def _splice(self, *, value: ast.expr, seen: _Seen) -> list[_Splice]:
        """A value spliced into a message, when it reaches a handled exception."""
        route = self._exception_route(expr=value, visited=set(seen))
        if route is None:
            return []
        return [_Splice(source=_short_source(expr=value), route=route)]

    def _exception_route(self, *, expr: ast.expr, visited: set[_Binding]) -> _Route | None:
        """The bindings through which an expression reaches a handled exception, or ``None`` when it reaches none.

        It reaches one when it calls a ``.exception()`` method, a finished task's or a retry outcome's, or reads a
        name one of whose bindings is an ``except ... as`` target or binds a value that reaches one in turn. Whether
        a binding reaches one does not depend on the way to it, so each binding is followed once.
        """
        for node in ast.walk(expr):
            match node:
                case ast.Call(func=ast.Attribute(attr="exception")):
                    return ()
                case ast.Name(ctx=ast.Load()):
                    scope = self._index.read_scopes.get(node)
                    route = None if scope is None else self._name_exception_route(node=node, scope=scope, visited=visited)
                    if route is not None:
                        return route
                case _:
                    pass
        return None

    def _name_exception_route(self, *, node: ast.Name, scope: _Scope, visited: set[_Binding]) -> _Route | None:
        for binding in self._index.possible_bindings(node=node, scope=scope):
            if binding in visited:
                continue
            visited.add(binding)
            rendered = binding.render(name=node.id)
            if binding.opaque == _OpaqueBinding.EXCEPT_TARGET:
                return (rendered,)
            if binding.opaque is not None or binding.value is None:
                continue
            route = self._exception_route(expr=binding.value, visited=visited)
            if route is None and binding.prior is not None:
                route = self._name_exception_route(node=binding.prior, scope=binding.scope, visited=visited)
            if route is not None:
                return (rendered, *route)
        return None


def markup_tags_of(*, shapes: Iterable[_Shape]) -> list[str]:
    """The distinct markup tags the runs of these shapes hold, in a stable order."""
    tags: list[str] = []
    for shape in sorted(shapes):
        for run in shape:
            for tag in find_markup_tags(text=run):
                if tag not in tags:
                    tags.append(tag)
    return tags


# --------------------------------------------------------------------------------------
# Wording: what the text of a message says, read off its shapes
#
# A rule about how a text starts or ends reads the first or the last run of each shape, so a text that starts or ends
# with a value the guard cannot read passes it. A rule about what a text holds reads every run, never across a value.
# The length counts a shape's runs alone, the least its text can be once its values are spliced in.
# --------------------------------------------------------------------------------------

#: The periods that end a text, an ellipsis written as three periods or as one character included.
_TRAILING_PERIOD_PATTERN = re.compile(r"[.…]+$")

#: A call written with empty parentheses, ``load()`` or ``Loader.load()``, else a word.
_IDENTIFIER_CANDIDATE_PATTERN = re.compile(r"(?:\w+\.)*\w+\(\)|\w+")


def _lowercase_start_of(*, text: str) -> str | None:
    """The first word of a text that starts with a lowercase letter, or ``None``; leading whitespace is skipped."""
    stripped = text.lstrip()
    if not stripped or not stripped[0].islower():
        return None
    return stripped.split(maxsplit=1)[0]


def _trailing_period_of(*, text: str) -> str | None:
    """The periods, or the ellipsis, a text ends with, or ``None``; trailing whitespace is skipped."""
    match = _TRAILING_PERIOD_PATTERN.search(text.rstrip())
    return match.group() if match else None


def _identifiers_in(*, text: str) -> list[str]:
    """The identifiers a text holds, in order: each call written ``name()``, and each word holding an underscore."""
    identifiers: list[str] = []
    for match in _IDENTIFIER_CANDIDATE_PATTERN.finditer(text):
        token = match.group()
        if token.endswith("()") or ("_" in token and token.strip("_")):
            identifiers.append(token)
    return identifiers


def _shape_length(*, shape: _Shape) -> int:
    return sum(len(run) for run in shape)


def wording_breaches(*, shapes: Iterable[_Shape], part_name: str, is_info_and_above: bool) -> list[RuleBreach]:
    """The wording rules a part of a message breaks, read off every text it can reach the console as.

    At every level a text starts with no lowercase letter, ends with no period and no ellipsis, and holds no backtick;
    at INFO and above it also holds no identifier and is at most ``MAX_MESSAGE_LENGTH`` characters long. A shape
    that breaks a rule is enough: a conditional between a good and a bad literal breaks it.
    """
    ordered_shapes = sorted(shapes)
    breaches: list[RuleBreach] = []
    first_words = dict.fromkeys(word for shape in ordered_shapes if (word := _lowercase_start_of(text=shape[0])) is not None)
    breaches.extend(RuleBreach(rule=LogCallRule.LOWERCASE_START, detail=f"{part_name} starts with the lowercase `{word}`") for word in first_words)
    endings = dict.fromkeys(ending for shape in ordered_shapes if (ending := _trailing_period_of(text=shape[-1])) is not None)
    breaches.extend(RuleBreach(rule=LogCallRule.TRAILING_PERIOD, detail=f"{part_name} ends with `{ending}`") for ending in endings)
    if any("`" in run for shape in ordered_shapes for run in shape):
        breaches.append(RuleBreach(rule=LogCallRule.BACKTICK, detail=f"{part_name} holds a backtick"))
    if not is_info_and_above:
        return breaches
    identifiers = dict.fromkeys(identifier for shape in ordered_shapes for run in shape for identifier in _identifiers_in(text=run))
    for identifier in identifiers:
        kind = "call" if identifier.endswith("()") else "identifier"
        breaches.append(RuleBreach(rule=LogCallRule.IDENTIFIER, detail=f"{part_name} holds the {kind} `{identifier}`"))
    longest = max(ordered_shapes, key=lambda shape: _shape_length(shape=shape), default=None)
    if longest is not None and _shape_length(shape=longest) > MAX_MESSAGE_LENGTH:
        # A shape of several runs splices values the guard cannot read, so its literal runs are the least it holds.
        bound = "" if len(longest) == 1 else "at least "
        detail = f"{part_name} is {bound}{_shape_length(shape=longest)} characters long, more than {MAX_MESSAGE_LENGTH}"
        breaches.append(RuleBreach(rule=LogCallRule.LENGTH, detail=detail))
    return breaches


# --------------------------------------------------------------------------------------
# The facade
# --------------------------------------------------------------------------------------


def module_package_of(*, relative_path: str) -> str:
    """The package a module's relative imports resolve against, read off its path: ``pipelex.core`` for ``pipelex/core/x.py``."""
    path = Path(relative_path)
    for import_root in IMPORT_ROOTS:
        if path.is_relative_to(import_root):
            path = path.relative_to(import_root)
    return ".".join(path.parent.parts)


def _absolute_module(*, module: str | None, level: int, package: str) -> str | None:
    if level == 0:
        return module
    package_parts = package.split(".") if package else []
    if level - 1 > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - (level - 1)]
    if module:
        base_parts.append(module)
    return ".".join(base_parts) or None


def _receiver_root(*, expr: ast.expr) -> tuple[ast.Name, list[str]] | None:
    """``a.b.c`` as the name ``a`` and the attributes ``["b", "c"]``, or ``None`` when the expression is not a dotted name."""
    attributes: list[str] = []
    while isinstance(expr, ast.Attribute):
        attributes.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    return expr, list(reversed(attributes))


def _expanded_entries(*, expr: ast.expr) -> list[tuple[str, ast.expr]] | None:
    """The keywords a ``**`` expansion passes, when it expands a dict literal whose keys are all strings, else ``None``."""
    if not isinstance(expr, ast.Dict):
        return None
    entries: list[tuple[str, ast.expr]] = []
    for key, value in zip(expr.keys, expr.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return None
        entries.append((key.value, value))
    return entries


def message_parts_of(*, call: ast.Call) -> tuple[list[tuple[str | None, ast.expr]], list[ast.expr]]:
    """The parts of a call's message, the message labelled ``None`` and a title by its keyword, and the ``**``
    expansions whose keywords cannot be read.

    A ``**`` of a dict literal with string keys passes its ``content``, ``title`` and ``inline`` entries as keywords;
    any other expansion may carry any of them, so the message cannot be read through it.
    """
    keywords: list[tuple[str, ast.expr]] = []
    unread: list[ast.expr] = []
    for keyword in call.keywords:
        if keyword.arg is not None:
            keywords.append((keyword.arg, keyword.value))
            continue
        entries = _expanded_entries(expr=keyword.value)
        if entries is None:
            unread.append(keyword.value)
        else:
            keywords.extend(entries)
    parts: list[tuple[str | None, ast.expr]] = []
    content = call.args[0] if call.args else next((value for name, value in keywords if name == CONTENT_KEYWORD), None)
    if content is not None:
        parts.append((None, content))
    # A title or inline title that is statically `None` is no text at all.
    parts.extend((name, value) for name, value in keywords if name in TITLE_KEYWORDS and not _is_none(expr=value))
    return parts, unread


# --------------------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------------------


class _LogCallCollector(ast.NodeVisitor):
    """Walks one module, tracking the qualified name it is in, and records every facade call that breaks a rule."""

    def __init__(self, *, relative_path: str, module: ast.Module) -> None:
        self.relative_path = relative_path
        self.offending_calls: list[OffendingCall] = []
        self._index = _ScopeIndex(module=module, package=module_package_of(relative_path=relative_path))
        self._qualified_parts: list[str] = []

    # ---- qualified names --------------------------------------------------------------

    def _visit_named_scope(self, *, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        # Decorators, defaults and bases run in the enclosing scope, under its name.
        for decorator in node.decorator_list:
            self.visit(decorator)
        if isinstance(node, ast.ClassDef):
            for base in (*node.bases, *node.keywords):
                self.visit(base)
        else:
            for default in (*node.args.defaults, *(default for default in node.args.kw_defaults if default is not None)):
                self.visit(default)
        self._qualified_parts.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self._qualified_parts.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        self._visit_named_scope(node=node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        self._visit_named_scope(node=node)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        self._visit_named_scope(node=node)

    @property
    def _qualified_name(self) -> str:
        return ".".join(self._qualified_parts) or MODULE_SCOPE_NAME

    # ---- the calls --------------------------------------------------------------------

    @override
    def visit_Call(self, node: ast.Call) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        method = self._facade_method(node=node)
        if method is not None:
            self._check_call(node=node, method=method)
        self.generic_visit(node)

    def _facade_method(self, *, node: ast.Call) -> str | None:
        """The facade method a call invokes, its receiver read where the call is made.

        The receiver's name is the facade when a binding that can reach the call imports the facade, under whatever
        name or module path: a parameter or a local of that name, or an import made in another function, is not.
        """
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in EMITTING_METHODS:
            return None
        receiver = _receiver_root(expr=node.func.value)
        if receiver is None:
            return None
        root, attributes = receiver
        for binding in self._index.possible_bindings(node=root, scope=self._index.call_scopes[node]):
            if binding.import_path is not None and ".".join([binding.import_path, *attributes]) in FACADE_PATHS:
                return node.func.attr
        return None

    def _check_call(self, *, node: ast.Call, method: str) -> None:
        scope = self._index.call_scopes[node]
        parts, unread_expansions = message_parts_of(call=node)
        is_info_and_above = method in INFO_AND_ABOVE_METHODS

        trace: set[str] = set()
        reader = _MessageReader(index=self._index, trace=trace)
        # A `**` expansion the guard cannot read may carry the message or a title, so no rule can be checked through it.
        breaches = [
            RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`**{_short_source(expr=expansion)}` is an expansion whose keywords cannot be read")
            for expansion in unread_expansions
        ]
        if is_info_and_above:
            for label, expr in parts:
                form = reader.form(expr=expr, scope=scope, seen=frozenset(), allows_none=label is not None)
                if form is not None:
                    breaches.append(RuleBreach(rule=form.rule, detail=f"{_part_name(label=label)} is {form.detail}"))
        for label, expr in parts:
            part_name = _part_name(label=label)
            shapes = reader.shapes(expr=expr, scope=scope, seen=frozenset())
            for tag in markup_tags_of(shapes=shapes):
                breaches.append(RuleBreach(rule=LogCallRule.MARKUP, detail=f"{part_name} holds the markup tag `{tag}`"))
            breaches.extend(wording_breaches(shapes=shapes, part_name=part_name, is_info_and_above=is_info_and_above))
            # Only the bindings a spliced exception is reached through join the trace: they are what that rule read.
            spliced_sources: list[str] = []
            for splice in reader.spliced_exceptions(expr=expr, scope=scope, seen=frozenset()):
                trace.update(splice.route)
                if splice.source not in spliced_sources:
                    spliced_sources.append(splice.source)
            breaches.extend(
                RuleBreach(rule=LogCallRule.SPLICED_EXCEPTION, detail=f"{part_name} splices the exception `{source}`") for source in spliced_sources
            )

        if not breaches:
            return
        self.offending_calls.append(
            OffendingCall(
                relative_path=self.relative_path,
                qualified_name=self._qualified_name,
                lineno=node.lineno,
                signature=call_signature(
                    method=method,
                    parts=parts,
                    rules={breach.rule for breach in breaches},
                    bindings=trace,
                    expansions=unread_expansions,
                ),
                breaches=tuple(breaches),
            )
        )


def _part_name(*, label: str | None) -> str:
    """How the report names a part of a call's message: the message itself, or the keyword a title rides."""
    return "the message" if label is None else f"`{label}=`"


def call_signature(
    *,
    method: str,
    parts: Sequence[tuple[str | None, ast.expr]],
    rules: Iterable[LogCallRule],
    bindings: Iterable[str] = (),
    expansions: Sequence[ast.expr] = (),
) -> str:
    """A call's identity in the baseline, never a line.

    Its method, its message's source and any title's, the ``**`` expansions it cannot read, the rules it breaks in
    their declared order, and every binding the guard read to judge it, sorted:
    ``warning: msg [f-string] where msg = f"Loaded {alias}"``.
    """
    rendered = [render_source(expr=expr) if label is None else f"{label}={render_source(expr=expr)}" for label, expr in parts]
    rendered.extend(f"**{render_source(expr=expansion)}" for expansion in expansions)
    broken = set(rules)
    rule_names = [str(rule) for rule in LogCallRule if rule in broken]
    signature = f"{method}: {', '.join(rendered) or '<no message>'} [{', '.join(rule_names)}]"
    sorted_bindings = sorted(set(bindings))
    if sorted_bindings:
        signature += " where " + "; ".join(sorted_bindings)
    return signature


def find_offending_calls_in_source(*, source: str, relative_path: str) -> list[OffendingCall]:
    """The facade calls in one module's source that break a rule, in source order."""
    module = ast.parse(source)
    collector = _LogCallCollector(relative_path=relative_path, module=module)
    collector.visit(module)
    return sorted(collector.offending_calls, key=lambda call: (call.lineno, call.signature))


def _is_excluded(*, relative_path: Path) -> bool:
    return any(relative_path.is_relative_to(excluded) for excluded in EXCLUDED_ROOTS)


def iter_scanned_files(*, repo_root: Path) -> Iterator[Path]:
    """Every ``.py`` file the guard reads, as a path relative to the repo root, in a stable order.

    Raises:
        LogCallGuardError: If a scan root is missing or holds no module, which means the guard runs from somewhere
            other than the repo root and would otherwise pass having read nothing.
    """
    for scan_root in SCAN_ROOTS:
        absolute_root = repo_root / scan_root
        if not absolute_root.is_dir():
            msg = f"The log-call guard's scan root '{scan_root.as_posix()}/' does not exist under '{repo_root}'. Run it from the repo root."
            raise LogCallGuardError(msg)
        nb_files = 0
        for path in sorted(absolute_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative_path = path.relative_to(repo_root)
            if _is_excluded(relative_path=relative_path):
                continue
            nb_files += 1
            yield relative_path
        if nb_files == 0:
            msg = f"The log-call guard's scan root '{scan_root.as_posix()}/' holds no Python module under '{repo_root}'."
            raise LogCallGuardError(msg)


def collect_offending_calls(*, repo_root: Path) -> list[OffendingCall]:
    """Every facade call in the scanned trees that breaks a rule, sorted by file, then line."""
    offending: list[OffendingCall] = []
    for relative_path in iter_scanned_files(repo_root=repo_root):
        source = (repo_root / relative_path).read_text(encoding="utf-8")
        offending.extend(find_offending_calls_in_source(source=source, relative_path=relative_path.as_posix()))
    return sorted(offending, key=lambda call: (call.relative_path, call.lineno, call.signature))


# --------------------------------------------------------------------------------------
# The baseline
# --------------------------------------------------------------------------------------

#: The baseline's content: each key's signatures, a signature listed once per call that carries it.
Baseline: TypeAlias = dict[str, list[str]]

_BASELINE_ENTRY_KEYS = frozenset({"calls"})

_BASELINE_HEADER = (
    "The log calls that broke the log-call conventions when the guard arrived (pipelex-dev check-log-calls).",
    "Keyed by <relative_path>::<qualified_name>, each call listed by its method, its message's source,",
    "the rules it breaks and the bindings its message was read through.",
    "It only shrinks: convert a call, then remove its signature (pipelex-dev check-log-calls --prune).",
    "Never add an entry: the check refuses a baseline that lists more than its base. See docs/contribute/log-calls.md.",
)


def parse_baseline(*, text: str, origin: str) -> Baseline:
    """Parse and validate a baseline's text, ``origin`` naming where it was read for an error.

    Raises:
        LogCallGuardError: When the text is not a well-formed baseline at ``BASELINE_VERSION``.
    """
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"The log-call baseline {origin} is not valid TOML: {exc}"
        raise LogCallGuardError(msg) from exc
    version = raw.pop("version", None)
    if version != BASELINE_VERSION:
        msg = f"The log-call baseline {origin} must declare `version = {BASELINE_VERSION}` (found: {version!r})"
        raise LogCallGuardError(msg)
    baseline: Baseline = {}
    for key, raw_entry in raw.items():
        relative_path, separator, qualified_name = key.partition("::")
        if not separator or not qualified_name or not relative_path.endswith(".py"):
            msg = f"The log-call baseline key '{key}' is not of the form '<relative_path>::<qualified_name>'"
            raise LogCallGuardError(msg)
        if not isinstance(raw_entry, dict):
            msg = f"The log-call baseline entry '{key}' must be a table"
            raise LogCallGuardError(msg)
        entry = cast("dict[str, Any]", raw_entry)
        unknown_keys = set(entry) - _BASELINE_ENTRY_KEYS
        if unknown_keys:
            msg = f"The log-call baseline entry '{key}' has unknown key(s): {sorted(unknown_keys)}"
            raise LogCallGuardError(msg)
        calls = entry.get("calls")
        if not isinstance(calls, list) or not calls:
            msg = f"The log-call baseline entry '{key}' must list its calls as a non-empty `calls` array"
            raise LogCallGuardError(msg)
        signatures: list[str] = []
        for call in cast("list[Any]", calls):
            if not isinstance(call, str) or not call.strip():
                msg = f"The log-call baseline entry '{key}' lists a call that is not a non-empty string: {call!r}"
                raise LogCallGuardError(msg)
            signatures.append(call)
        baseline[key] = signatures
    return baseline


def load_baseline(*, repo_root: Path) -> Baseline:
    """Load and validate the committed baseline.

    Raises:
        LogCallGuardError: When the file is missing or malformed. A missing baseline is an error, never an empty
            one, which would report every listed call as new.
    """
    path = repo_root / BASELINE_FILE
    if not path.is_file():
        msg = f"The log-call baseline was not found at '{path}'. It is committed at the repo root; run the check from there."
        raise LogCallGuardError(msg)
    return parse_baseline(text=path.read_text(encoding="utf-8"), origin=f"'{path}'")


def _signatures_by_key(*, offending: Sequence[OffendingCall]) -> dict[str, list[OffendingCall]]:
    by_key: dict[str, list[OffendingCall]] = {}
    for call in offending:
        by_key.setdefault(call.key, []).append(call)
    return by_key


def compare_with_baseline(*, offending: Sequence[OffendingCall], baseline: Mapping[str, Sequence[str]]) -> BaselineComparison:
    """Match the offending calls against the baseline, exactly, both ways.

    A call is covered when its key lists its signature, once per call carrying it; a call beyond what is listed is
    unlisted, and a listed signature beyond the calls carrying it is stale.
    """
    unlisted: list[OffendingCall] = []
    stale: list[StaleEntry] = []
    by_key = _signatures_by_key(offending=offending)
    for key in sorted(set(by_key) | set(baseline)):
        listed = Counter(baseline.get(key, ()))
        calls_by_signature: dict[str, list[OffendingCall]] = {}
        for call in by_key.get(key, []):
            calls_by_signature.setdefault(call.signature, []).append(call)
        for signature, calls in calls_by_signature.items():
            unlisted.extend(calls[listed[signature] :])
        for signature, count in sorted(listed.items()):
            found = len(calls_by_signature.get(signature, []))
            # A signature listed more times than calls carry it is stale once per extra listing, the entry being immutable.
            stale.extend([StaleEntry(key=key, signature=signature)] * (count - found))
    return BaselineComparison(
        unlisted=sorted(unlisted, key=lambda call: (call.relative_path, call.lineno, call.signature)),
        stale=stale,
    )


def compare_with_trusted_baseline(*, baseline: Mapping[str, Sequence[str]], trusted: Mapping[str, Sequence[str]]) -> list[BaselineGrowth]:
    """Every signature the working baseline lists more times than the trusted one: the entries added since, sorted.

    The baseline only shrinks, so a pass is an empty list: every signature listed as often as at the trusted
    revision, or less.
    """
    growth: list[BaselineGrowth] = []
    for key in sorted(baseline):
        trusted_counts = Counter(trusted.get(key, ()))
        for signature, working_count in sorted(Counter(baseline[key]).items()):
            if working_count > trusted_counts[signature]:
                growth.append(BaselineGrowth(key=key, signature=signature, trusted_count=trusted_counts[signature], working_count=working_count))
    return growth


def build_baseline(*, offending: Sequence[OffendingCall]) -> Baseline:
    """The baseline that lists exactly the given calls, which is how the committed one was generated."""
    return {key: sorted(call.signature for call in calls) for key, calls in sorted(_signatures_by_key(offending=offending).items())}


def prune_baseline(*, baseline: Mapping[str, Sequence[str]], offending: Sequence[OffendingCall]) -> Baseline:
    """The baseline without its stale signatures. It never adds one: an unlisted call stays unlisted."""
    calls_by_key = _signatures_by_key(offending=offending)
    pruned: Baseline = {}
    for key in sorted(baseline):
        found = Counter(call.signature for call in calls_by_key.get(key, []))
        kept: list[str] = []
        for signature, count in sorted(Counter(baseline[key]).items()):
            kept.extend([signature] * min(count, found[signature]))
        if kept:
            pruned[key] = kept
    return pruned


def baseline_document(*, baseline: Mapping[str, Sequence[str]]) -> tomlkit.TOMLDocument:
    """The baseline as a TOML document: the header, the version, then every key in sorted order with its sorted calls.

    Each ``calls`` array is laid out one signature per line, indented the way ``plxt fmt`` indents an array, so a
    prune followed by ``make format`` moves nothing else.
    """
    document = tomlkit.document()
    for line in _BASELINE_HEADER:
        document.add(tomlkit.comment(line))
    document.add(tomlkit.nl())
    document.add("version", tomlkit.integer(BASELINE_VERSION))
    for key in sorted(baseline):
        calls = tomlkit.array()
        for signature in sorted(baseline[key]):
            calls.add_line(signature, indent="  ")
        calls.add_line(indent="")
        table = tomlkit.table()
        table.add("calls", calls)
        document.add(key, table)
    return document


def render_baseline(*, baseline: Mapping[str, Sequence[str]]) -> str:
    """The baseline file's text, as ``write_baseline`` writes it."""
    return baseline_document(baseline=baseline).as_string()


def write_baseline(*, baseline: Mapping[str, Sequence[str]], repo_root: Path) -> None:
    """Write the baseline file at the repo root, through the repo's TOML writer."""
    save_toml_to_path(baseline_document(baseline=baseline), path=repo_root / BASELINE_FILE)


def package_area_of(*, key: str) -> str:
    """The package area a baseline key belongs to, for the report: ``pipelex/<area>``, ``pipelex`` for a root module, or the API server."""
    parts = key.partition("::")[0].split("/")
    if parts[0] == "api":
        return "api/pipelex_api"
    if len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


# --------------------------------------------------------------------------------------
# The trusted baseline, read through git
# --------------------------------------------------------------------------------------


class _GitResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _run_git(*, args: list[str], repo_root: Path) -> _GitResult:
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["git", *args],  # ruff: ignore[start-process-with-partial-path]
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        msg = "git was not found on PATH: the comparison with a trusted baseline reads it through git"
        raise LogCallGuardError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS}s"
        raise LogCallGuardError(msg) from exc
    return _GitResult(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr.strip())


def resolve_merge_base(*, repo_root: Path, ref: str) -> str | None:
    """The merge base of ``HEAD`` and ``ref``, or ``None`` when it does not resolve: an unknown ref, or a shallow history."""
    result = _run_git(args=["merge-base", "HEAD", ref], repo_root=repo_root)
    merge_base = result.stdout.strip()
    if result.returncode != 0 or not merge_base:
        return None
    return merge_base


def _path_exists_at(*, repo_root: Path, commit: str, path: Path) -> bool:
    return _run_git(args=["cat-file", "-e", f"{commit}:{path.as_posix()}"], repo_root=repo_root).returncode == 0


def load_trusted_baseline(*, repo_root: Path, ref: str) -> Baseline | None:
    """The baseline committed at a trusted revision, read through ``git show``.

    A revision that runs the guard but holds no baseline file has an empty one. A revision the guard does not exist
    at yet holds nothing to compare with: ``None``, for the caller to say so.

    Raises:
        LogCallGuardError: When the revision does not resolve to a commit, or its baseline is malformed or of another
            version: the comparison cannot be made, and a gate that cannot compare fails.
    """
    resolved = _run_git(args=["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root=repo_root)
    commit = resolved.stdout.strip()
    if resolved.returncode != 0 or not commit:
        msg = f"The revision '{ref}' the log-call baseline is compared with does not resolve to a commit. Fetch it first."
        raise LogCallGuardError(msg)
    if not _path_exists_at(repo_root=repo_root, commit=commit, path=BASELINE_FILE):
        if _path_exists_at(repo_root=repo_root, commit=commit, path=GUARD_MODULE_FILE):
            return {}
        return None
    shown = _run_git(args=["show", f"{commit}:{BASELINE_FILE.as_posix()}"], repo_root=repo_root)
    if shown.returncode != 0:
        msg = f"git could not read {BASELINE_FILE.as_posix()} at '{ref}': {shown.stderr}"
        raise LogCallGuardError(msg)
    return parse_baseline(text=shown.stdout, origin=f"at '{ref}'")
