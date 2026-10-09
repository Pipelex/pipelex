"""AST core for the log-call guard.

Pipelex's log-call conventions, written for contributors in ``docs/tools/logging.md`` ("Log-call conventions"), say
that a line's message is a fixed sentence and that its values ride in ``fields``. This module checks the ones that
can be read off the source, on every call of the ``log`` facade in ``pipelex/`` outside ``pipelex/tools/log/``
and in the ``api/`` member's ``api/pipelex_api/``:

1. **The interpolation rule, at INFO and above** (``info``, ``warning``, ``error``, ``critical``). The message is a
   literal written at the call: a string constant, an f-string without a placeholder, a ``+`` of literals, a
   conditional between literals, or a name bound only to literals in its own scope or at module level, a ``+=`` of a
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

The title and the inline title join the message (the dispatch renders them into it), so both rules read them too,
and a title or an inline title that is statically ``None`` is no text at all. DEBUG and VERBOSE may keep an
f-string; the markup rule holds there as everywhere.

**Names** are read by Python's own scoping: the scope the call is made in (a comprehension reading as part of the
scope it is written in), then the enclosing functions, class bodies never among them, then the module. One index of
every scope's bindings is built per module, in one walk. A name bound in an enclosing function is not followed.

**The baseline.** The calls that broke the rules when the guard arrived are listed in the committed
``log_call_baseline.toml`` at the repo root, under the key ``<relative_path>::<qualified_name>`` of the function that
makes them, ``<module>`` for a module-level call, each by its signature: the method, the message's source text, the
rules the call breaks and every binding the guard read to judge it
(``warning: msg [f-string] where msg = f"Loaded {alias}"``), rendered the same on every supported Python. Line
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
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias, cast

import tomlkit
from rich.default_styles import DEFAULT_STYLES
from rich.errors import StyleSyntaxError
from rich.style import Style
from typing_extensions import override

from pipelex.tools.misc.toml_utils import save_toml_to_path

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

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

#: The facade's methods at INFO and above, where a message is a literal.
INTERPOLATION_BOUND_METHODS = frozenset({"info", "warning", "error", "critical"})

#: Every method of the facade that emits a line, where a literal message holds no markup.
MARKUP_BOUND_METHODS = frozenset({"verbose", "debug", *INTERPOLATION_BOUND_METHODS})

#: The keyword a call may pass its message under instead of positionally.
CONTENT_KEYWORD = "content"

#: The keywords whose text the dispatch renders into the message.
TITLE_KEYWORDS = ("title", "inline")

#: The qualified name of a call made outside any function or class.
MODULE_SCOPE_NAME = "<module>"

#: Rich's own console-markup tag pattern, ``rich.markup.RE_TAGS``: a run of backslashes, then a bracketed tag whose
#: text opens with a lowercase letter, ``#``, ``/`` or ``@``. An odd run of backslashes escapes the tag.
MARKUP_TAG_PATTERN = re.compile(r"((\\*)\[([a-z#/@][^[]*?)])")

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

    @property
    def remedy(self) -> str:
        match self:
            case LogCallRule.F_STRING | LogCallRule.PERCENT_FORMAT | LogCallRule.CONCATENATION | LogCallRule.FORMAT_CALL:
                return "write a fixed message and pass its values in `fields=` (DEBUG and VERBOSE may keep an f-string)"
            case LogCallRule.NON_LITERAL:
                return "write the message as a literal at the call and pass what varies in `fields=`"
            case LogCallRule.MARKUP:
                return "drop the tag: the console colours a value by its field's name, or draws a named layout"


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
# Markup
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
    """The unescaped Rich markup tags a piece of literal message text holds, in order."""
    if "[" not in text:
        return []
    tags: list[str] = []
    for match in MARKUP_TAG_PATTERN.finditer(text):
        full_text, escapes, tag_text = match.groups()
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
# Scopes and bindings, indexed once per module
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


class _Binding(NamedTuple):
    """One binding of a name: the value bound, the scope that value is read in, and how it binds.

    Attributes:
        value: The bound expression, ``None`` for an opaque binding.
        scope: The scope the value is evaluated in, which is where the names it reads resolve: the function a
            ``global`` assignment is written in, or the comprehension holding a ``:=``, rather than the scope the
            name lands in.
        lineno: The line, for the report only.
        operator: The operator of an augmented assignment, ``None`` for a plain one.
        opaque: What binds the name when the guard does not read the value: a parameter, a loop target, an import.
    """

    value: ast.expr | None
    scope: _Scope
    lineno: int
    operator: ast.operator | None
    opaque: _OpaqueBinding | None

    def render(self, *, name: str) -> str:
        """The binding as a signature writes it: its source text, never its line."""
        if self.opaque is not None or self.value is None:
            return f"{name} = {(self.opaque or _OpaqueBinding.ASSIGNMENT_TARGET).placeholder}"
        if self.operator is not None:
            return f"{name} {_operator_symbol(operator=self.operator)}= {render_source(expr=self.value)}"
        return f"{name} = {render_source(expr=self.value)}"


class _Scope:
    """One scope of a module and the index of the names it binds, by Python's rules."""

    def __init__(self, *, kind: _ScopeKind, parent: _Scope | None) -> None:
        self.kind = kind
        self.parent = parent
        self.bindings: dict[str, list[_Binding]] = {}
        # Every name a binding operation targets here, `del` and a bare annotation included: those make a name
        # local without giving it a value.
        self.bound_names: set[str] = set()
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()

    def bind(self, *, name: str, binding: _Binding) -> None:
        self.bindings.setdefault(name, []).append(binding)
        self.bound_names.add(name)

    def owns(self, *, name: str) -> bool:
        """Whether the name is local to this scope: bound here and declared neither ``global`` nor ``nonlocal``."""
        return name in self.bound_names and name not in self.global_names and name not in self.nonlocal_names

    def bindings_of(self, *, name: str) -> list[_Binding]:
        return sorted(self.bindings.get(name, []), key=lambda binding: binding.lineno)

    @property
    def statement_scope(self) -> _Scope:
        """The nearest scope that is not a comprehension: where a ``:=`` in a comprehension binds its name."""
        scope = self
        while scope.kind.is_comprehension and scope.parent is not None:
            scope = scope.parent
        return scope


#: Where a name read in a scope resolves: the scope whose bindings it reads, or the placeholder of a name not followed.
_Location: TypeAlias = _Scope | str


class _ScopeIndex:
    """Every scope of one module with the names each binds, and the scope each call is made in, built in one walk."""

    def __init__(self, *, module: ast.Module) -> None:
        self.module_scope = _Scope(kind=_ScopeKind.MODULE, parent=None)
        self.call_scopes: dict[ast.Call, _Scope] = {}
        self._scopes: list[_Scope] = [self.module_scope]
        for statement in module.body:
            self._visit(node=statement, scope=self.module_scope)
        self._apply_declarations()

    # ---- the walk ---------------------------------------------------------------------

    def _new_scope(self, *, kind: _ScopeKind, parent: _Scope) -> _Scope:
        scope = _Scope(kind=kind, parent=parent)
        self._scopes.append(scope)
        return scope

    def _visit_all(self, *, nodes: Iterable[ast.AST | None], scope: _Scope) -> None:
        for node in nodes:
            if node is not None:
                self._visit(node=node, scope=scope)

    def _visit(self, *, node: ast.AST, scope: _Scope) -> None:
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef():
                self._bind_opaque(name=node.name, kind=_OpaqueBinding.DEFINITION, scope=scope, lineno=node.lineno)
                self._visit_all(nodes=node.decorator_list, scope=scope)
                self._visit_signature_outside(arguments=node.args, scope=scope)
                self._visit_all(nodes=[node.returns, *getattr(node, "type_params", [])], scope=scope)
                function_scope = self._new_scope(kind=_ScopeKind.FUNCTION, parent=scope)
                self._bind_parameters(arguments=node.args, scope=function_scope)
                self._visit_all(nodes=node.body, scope=function_scope)
            case ast.Lambda():
                self._visit_signature_outside(arguments=node.args, scope=scope)
                lambda_scope = self._new_scope(kind=_ScopeKind.FUNCTION, parent=scope)
                self._bind_parameters(arguments=node.args, scope=lambda_scope)
                self._visit(node=node.body, scope=lambda_scope)
            case ast.ClassDef():
                self._bind_opaque(name=node.name, kind=_OpaqueBinding.DEFINITION, scope=scope, lineno=node.lineno)
                self._visit_all(nodes=[*node.decorator_list, *node.bases, *node.keywords, *getattr(node, "type_params", [])], scope=scope)
                class_scope = self._new_scope(kind=_ScopeKind.CLASS, parent=scope)
                self._visit_all(nodes=node.body, scope=class_scope)
            case ast.ListComp(elt=elt, generators=generators) | ast.SetComp(elt=elt, generators=generators):
                self._visit_comprehension(generators=generators, results=[elt], scope=scope)
            case ast.GeneratorExp(elt=elt, generators=generators):
                self._visit_comprehension(generators=generators, results=[elt], scope=scope)
            case ast.DictComp(key=key, value=value, generators=generators):
                self._visit_comprehension(generators=generators, results=[key, value], scope=scope)
            case ast.Assign(targets=targets, value=value):
                for target in targets:
                    if isinstance(target, ast.Name):
                        scope.bind(name=target.id, binding=_Binding(value=value, scope=scope, lineno=node.lineno, operator=None, opaque=None))
                    else:
                        self._bind_target(target=target, kind=_OpaqueBinding.UNPACKING, scope=scope)
                self._visit(node=value, scope=scope)
            case ast.AnnAssign(target=target, annotation=annotation, value=value):
                if isinstance(target, ast.Name):
                    if value is None:
                        # A bare annotation binds no value but makes the name local, by Python's rules.
                        scope.bound_names.add(target.id)
                    else:
                        scope.bind(name=target.id, binding=_Binding(value=value, scope=scope, lineno=node.lineno, operator=None, opaque=None))
                else:
                    self._visit(node=target, scope=scope)
                self._visit_all(nodes=[annotation, value], scope=scope)
            case ast.AugAssign(target=target, op=operator, value=value):
                if isinstance(target, ast.Name):
                    scope.bind(name=target.id, binding=_Binding(value=value, scope=scope, lineno=node.lineno, operator=operator, opaque=None))
                else:
                    self._visit(node=target, scope=scope)
                self._visit(node=value, scope=scope)
            case ast.NamedExpr(target=ast.Name(id=name), value=value):
                # A `:=` in a comprehension binds in the scope the comprehension is written in, its value read where it stands.
                scope.statement_scope.bind(name=name, binding=_Binding(value=value, scope=scope, lineno=node.lineno, operator=None, opaque=None))
                self._visit(node=value, scope=scope)
            case ast.For(target=target) | ast.AsyncFor(target=target):
                self._bind_target(target=target, kind=_OpaqueBinding.FOR_TARGET, scope=scope)
                self._visit_all(nodes=[node.iter, *node.body, *node.orelse], scope=scope)
            case ast.With(items=items, body=body) | ast.AsyncWith(items=items, body=body):
                for item in items:
                    self._visit(node=item.context_expr, scope=scope)
                    if item.optional_vars is not None:
                        self._bind_target(target=item.optional_vars, kind=_OpaqueBinding.WITH_TARGET, scope=scope)
                self._visit_all(nodes=body, scope=scope)
            case ast.ExceptHandler(type=exception_type, name=handler_name, body=body):
                if handler_name is not None:
                    self._bind_opaque(name=handler_name, kind=_OpaqueBinding.EXCEPT_TARGET, scope=scope, lineno=node.lineno)
                self._visit_all(nodes=[exception_type, *body], scope=scope)
            case ast.Import(names=aliases) | ast.ImportFrom(names=aliases):
                for alias in aliases:
                    if alias.name != "*":
                        bound_name = alias.asname or alias.name.partition(".")[0]
                        self._bind_opaque(name=bound_name, kind=_OpaqueBinding.IMPORT, scope=scope, lineno=node.lineno)
            case ast.Global(names=names):
                # A module-level `global` changes nothing.
                if not scope.kind.is_module:
                    scope.global_names.update(names)
            case ast.Nonlocal(names=names):
                scope.nonlocal_names.update(names)
            case ast.MatchAs(pattern=pattern, name=capture_name):
                if capture_name is not None:
                    self._bind_opaque(name=capture_name, kind=_OpaqueBinding.MATCH_CAPTURE, scope=scope, lineno=node.lineno)
                if pattern is not None:
                    self._visit(node=pattern, scope=scope)
            case ast.MatchStar(name=capture_name):
                if capture_name is not None:
                    self._bind_opaque(name=capture_name, kind=_OpaqueBinding.MATCH_CAPTURE, scope=scope, lineno=node.lineno)
            case ast.MatchMapping(keys=keys, patterns=patterns, rest=rest):
                if rest is not None:
                    self._bind_opaque(name=rest, kind=_OpaqueBinding.MATCH_CAPTURE, scope=scope, lineno=node.lineno)
                self._visit_all(nodes=[*keys, *patterns], scope=scope)
            case ast.Name(id=name, ctx=ast.Store()):
                self._bind_opaque(name=name, kind=_OpaqueBinding.ASSIGNMENT_TARGET, scope=scope, lineno=node.lineno)
            case ast.Name(id=name, ctx=ast.Del()):
                # `del` makes a name local without giving it a value, by Python's rules.
                scope.bound_names.add(name)
            case ast.Call():
                self.call_scopes[node] = scope
                self._visit_all(nodes=ast.iter_child_nodes(node), scope=scope)
            case _:
                self._visit_all(nodes=ast.iter_child_nodes(node), scope=scope)

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
        """A comprehension: its first iterable is read in the enclosing scope, everything else in a scope of its own."""
        self._visit(node=generators[0].iter, scope=scope)
        comprehension_scope = self._new_scope(kind=_ScopeKind.COMPREHENSION, parent=scope)
        for index_generator, generator in enumerate(generators):
            if index_generator > 0:
                self._visit(node=generator.iter, scope=comprehension_scope)
            self._bind_target(target=generator.target, kind=_OpaqueBinding.COMPREHENSION_TARGET, scope=comprehension_scope)
            self._visit_all(nodes=generator.ifs, scope=comprehension_scope)
        self._visit_all(nodes=results, scope=comprehension_scope)

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

    @staticmethod
    def _bind_opaque(*, name: str, kind: _OpaqueBinding, scope: _Scope, lineno: int) -> None:
        scope.bind(name=name, binding=_Binding(value=None, scope=scope, lineno=lineno, operator=None, opaque=kind))

    def _apply_declarations(self) -> None:
        """Move the bindings of a ``global`` or ``nonlocal`` name to the scope that owns it."""
        for scope in self._scopes:
            for name in sorted(scope.global_names):
                for binding in scope.bindings.pop(name, []):
                    self.module_scope.bind(name=name, binding=binding)
            for name in sorted(scope.nonlocal_names):
                owner = self._nonlocal_owner(scope=scope, name=name)
                moved = scope.bindings.pop(name, [])
                if owner is not None:
                    for binding in moved:
                        owner.bind(name=name, binding=binding)

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

#: What a name already followed is keyed by: its owning scope and itself.
_SeenKey: TypeAlias = tuple[int, str]


def _folded(*, left: set[_Shape], right: set[_Shape]) -> set[_Shape]:
    """The shapes of a concatenation: each left text's last run joined to each right text's first run."""
    if len(left) * len(right) > _MAX_FOLDED_SHAPES:
        return left | right
    return {(*left_shape[:-1], left_shape[-1] + right_shape[0], *right_shape[1:]) for left_shape, right_shape in itertools.product(left, right)}


def _short_source(*, expr: ast.expr, limit: int = 60) -> str:
    text = render_source(expr=expr)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_none(*, expr: ast.expr) -> bool:
    return isinstance(expr, ast.Constant) and expr.value is None


class _MessageReader:
    """Reads a message expression in the scope it is written in, through the bindings of the names it holds.

    Every binding it reads is recorded in ``trace``, as a signature writes it, so the identity of a call that breaks
    a rule changes whenever what it logs does.
    """

    def __init__(self, *, index: _ScopeIndex, trace: set[str]) -> None:
        self._index = index
        self.trace = trace

    # ---- the form, for the interpolation rule -----------------------------------------

    def form(self, *, expr: ast.expr, scope: _Scope, seen: frozenset[_SeenKey], allows_none: bool) -> _Form:
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
            case ast.Name(id=name):
                return self._name_form(name=name, scope=scope, seen=seen, allows_none=allows_none)
            case _:
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{_short_source(expr=expr)}`, not a literal")

    def _name_form(self, *, name: str, scope: _Scope, seen: frozenset[_SeenKey], allows_none: bool) -> _Form:
        location = self._index.locate(scope=scope, name=name)
        if isinstance(location, str):
            self.trace.add(f"{name} = {location}")
            if location == _CAPTURED_PLACEHOLDER:
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, captured from an enclosing function")
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound to no literal in its scope or at module level")
        key = (id(location), name)
        if key in seen:
            # A name read inside its own binding, `msg = msg + "!"`: the name's other bindings decide.
            return None
        seen |= {key}
        bindings = location.bindings_of(name=name)
        if not bindings:
            self.trace.add(f"{name} = {_UNBOUND_PLACEHOLDER}")
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound to no literal in its scope or at module level")
        first_form: _Form = None
        for binding in bindings:
            self.trace.add(binding.render(name=name))
            binding_form = self._binding_form(name=name, binding=binding, seen=seen, allows_none=allows_none)
            first_form = first_form or binding_form
        return first_form

    def _binding_form(self, *, name: str, binding: _Binding, seen: frozenset[_SeenKey], allows_none: bool) -> _Form:
        if binding.opaque is not None or binding.value is None:
            kind = binding.opaque or _OpaqueBinding.ASSIGNMENT_TARGET
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound at line {binding.lineno} as a {kind}, not to a literal")
        if binding.operator is None:
            value_form = self.form(expr=binding.value, scope=binding.scope, seen=seen, allows_none=allows_none)
            if value_form is None:
                return None
            return RuleBreach(rule=value_form.rule, detail=f"`{name}`, bound at line {binding.lineno} to {value_form.detail}")
        match binding.operator:
            case ast.Add():
                # `msg += "!"` keeps a literal literal; extending it by anything else is a concatenation.
                if self.form(expr=binding.value, scope=binding.scope, seen=seen, allows_none=False) is None:
                    return None
                return RuleBreach(rule=LogCallRule.CONCATENATION, detail=f"`{name}`, extended with `+=` at line {binding.lineno}")
            case ast.Mod():
                return RuleBreach(rule=LogCallRule.PERCENT_FORMAT, detail=f"`{name}`, formatted with `%=` at line {binding.lineno}")
            case _:
                symbol = _operator_symbol(operator=binding.operator)
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, updated with `{symbol}=` at line {binding.lineno}")

    # ---- the shapes, for the markup rule ----------------------------------------------

    def shapes(self, *, expr: ast.expr, scope: _Scope, seen: frozenset[_SeenKey]) -> set[_Shape]:
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
            case ast.Name(id=name):
                return self._name_shapes(name=name, scope=scope, seen=seen)
            case _:
                return {_UNKNOWN_SHAPE}

    def _name_shapes(self, *, name: str, scope: _Scope, seen: frozenset[_SeenKey]) -> set[_Shape]:
        """The texts a name can hold: each plain binding's, alone and extended by every later ``+=`` in source order."""
        location = self._index.locate(scope=scope, name=name)
        if isinstance(location, str):
            self.trace.add(f"{name} = {location}")
            return {_UNKNOWN_SHAPE}
        key = (id(location), name)
        if key in seen:
            return {_UNKNOWN_SHAPE}
        seen |= {key}
        bindings = location.bindings_of(name=name)
        result: set[_Shape] = set()
        for index_binding, binding in enumerate(bindings):
            self.trace.add(binding.render(name=name))
            if binding.value is None:
                result.add(_UNKNOWN_SHAPE)
                continue
            if binding.operator is not None:
                if isinstance(binding.operator, ast.Add):
                    result |= self.shapes(expr=binding.value, scope=binding.scope, seen=seen)
                continue
            base = self.shapes(expr=binding.value, scope=binding.scope, seen=seen)
            result |= base
            extended = base
            for later in bindings[index_binding + 1 :]:
                if isinstance(later.operator, ast.Add) and later.value is not None:
                    extended = _folded(left=extended, right=self.shapes(expr=later.value, scope=later.scope, seen=seen))
            result |= extended
        return result or {_UNKNOWN_SHAPE}


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


def imported_paths(*, tree: ast.Module, package: str) -> dict[str, set[str]]:
    """The dotted path each name a module imports is bound to, wherever it imports it.

    ``import a.b`` binds ``a`` to ``a``, ``import a.b as x`` binds ``x`` to ``a.b``, ``from a import b as c`` binds
    ``c`` to ``a.b``, a relative import resolves against the module's package, and a star import from a module that
    exports the facade binds its name. A name imported more than once keeps every path.
    """
    paths: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        match node:
            case ast.Import(names=aliases):
                for alias in aliases:
                    if alias.asname:
                        paths.setdefault(alias.asname, set()).add(alias.name)
                    else:
                        top_level = alias.name.partition(".")[0]
                        paths.setdefault(top_level, set()).add(top_level)
            case ast.ImportFrom(module=module, level=level, names=aliases):
                base = _absolute_module(module=module, level=level, package=package)
                if base is None:
                    continue
                for alias in aliases:
                    if alias.name == "*":
                        if base in FACADE_STAR_MODULES:
                            paths.setdefault(FACADE_NAME, set()).add(f"{base}.{FACADE_NAME}")
                        continue
                    paths.setdefault(alias.asname or alias.name, set()).add(f"{base}.{alias.name}")
            case _:
                pass
    return paths


def _dotted_parts(*, expr: ast.expr) -> list[str] | None:
    """``a.b.c`` as ``["a", "b", "c"]``, or ``None`` when the expression is not a dotted name."""
    attributes: list[str] = []
    while isinstance(expr, ast.Attribute):
        attributes.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    return [expr.id, *reversed(attributes)]


# --------------------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------------------


class _LogCallCollector(ast.NodeVisitor):
    """Walks one module, tracking the qualified name it is in, and records every facade call that breaks a rule."""

    def __init__(self, *, relative_path: str, module: ast.Module) -> None:
        self.relative_path = relative_path
        self.offending_calls: list[OffendingCall] = []
        self._index = _ScopeIndex(module=module)
        self._imported_paths = imported_paths(tree=module, package=module_package_of(relative_path=relative_path))
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
        """The facade method a call invokes, under whatever name or module path the module reaches the facade by."""
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in MARKUP_BOUND_METHODS:
            return None
        receiver_parts = _dotted_parts(expr=node.func.value)
        if receiver_parts is None:
            return None
        root_name, *attributes = receiver_parts
        for root_path in self._imported_paths.get(root_name, set()):
            if ".".join([root_path, *attributes]) in FACADE_PATHS:
                return node.func.attr
        return None

    def _check_call(self, *, node: ast.Call, method: str) -> None:
        scope = self._index.call_scopes[node]
        content = node.args[0] if node.args else next((keyword.value for keyword in node.keywords if keyword.arg == CONTENT_KEYWORD), None)
        parts: list[tuple[str | None, ast.expr]] = [(None, content)] if content is not None else []
        # A title or inline title that is statically `None` is no text at all.
        parts.extend((keyword.arg, keyword.value) for keyword in node.keywords if keyword.arg in TITLE_KEYWORDS and not _is_none(expr=keyword.value))

        trace: set[str] = set()
        reader = _MessageReader(index=self._index, trace=trace)
        breaches: list[RuleBreach] = []
        if method in INTERPOLATION_BOUND_METHODS:
            for label, expr in parts:
                form = reader.form(expr=expr, scope=scope, seen=frozenset(), allows_none=label is not None)
                if form is not None:
                    breaches.append(RuleBreach(rule=form.rule, detail=f"{_part_name(label=label)} is {form.detail}"))
        for label, expr in parts:
            for tag in markup_tags_of(shapes=reader.shapes(expr=expr, scope=scope, seen=frozenset())):
                breaches.append(RuleBreach(rule=LogCallRule.MARKUP, detail=f"{_part_name(label=label)} holds the markup tag `{tag}`"))

        if not breaches:
            return
        self.offending_calls.append(
            OffendingCall(
                relative_path=self.relative_path,
                qualified_name=self._qualified_name,
                lineno=node.lineno,
                signature=call_signature(method=method, parts=parts, rules={breach.rule for breach in breaches}, bindings=trace),
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
) -> str:
    """A call's identity in the baseline, never a line.

    Its method, its message's source and any title's, the rules it breaks in their declared order, and every binding
    the guard read to judge it, sorted: ``warning: msg [f-string] where msg = f"Loaded {alias}"``.
    """
    rendered = [render_source(expr=expr) if label is None else f"{label}={render_source(expr=expr)}" for label, expr in parts]
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
            stale.extend(StaleEntry(key=key, signature=signature) for _ in range(count - found))
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
