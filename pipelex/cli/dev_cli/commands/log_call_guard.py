"""AST core for the log-call guard.

Pipelex's log-call conventions, written for contributors in ``docs/tools/logging.md`` ("Log-call conventions"), say
that a line's message is a fixed sentence and that its values ride in ``fields``. This module checks the ones that
can be read off the source, on every call of the ``log`` facade in ``pipelex/`` outside ``pipelex/tools/log/``
and in the ``api/`` member's ``api/pipelex_api/``:

1. **The interpolation rule, at INFO and above** (``info``, ``warning``, ``error``, ``critical``). The message is a
   literal written at the call: a string constant, an f-string without a placeholder, a ``+`` of literals, a
   conditional between literals, or a name bound only to literals in the enclosing function or at module level. A
   message built by an f-string, by ``%``, by ``+`` or by ``.format()`` is refused under that form's name, and so is
   a name bound to one of those in the enclosing function, the binding's line given. Any other expression, a
   parameter, an attribute, a call's result, a mapping, is refused as ``non-literal``: the guard cannot tell that it
   is fixed, and every such message the first census found was built from values.
2. **The markup rule, at every level.** No literal part of a message, its title or its inline title holds a Rich
   markup tag: a closing tag (``[/red]``, ``[/]``), an ``@`` handler, or a tag whose text Rich reads as a style
   (``[red]``, ``[bold green]``, ``[link=https://…]``) or as one of its theme's style names. A bracketed word that
   is no style, ``list[int]``, is text and passes. A tag escaped with a backslash passes.

The title and the inline title join the message (the dispatch renders them into it), so both rules read them too.
DEBUG and VERBOSE may keep an f-string; the markup rule holds there as everywhere.

**The baseline.** The calls that broke the rules when the guard arrived are listed in the committed
``log_call_baseline.toml`` at the repo root, under the key ``<relative_path>::<qualified_name>`` of the function that
makes them, ``<module>`` for a module-level call, each by its signature: the method and the message's source text
(``warning: f'Could not parse METHODS.toml: {exc.message}'``), rendered the same on every supported Python. Line
numbers never enter it. The baseline can only shrink, and the comparison is exact both ways: a call the baseline does
not list fails, and so does a listed signature no call matches any more, whether the call now complies, moved to
another function or had its message changed, until its entry is removed. Changing a listed call's message is
therefore converting it. ``prune_baseline`` removes stale signatures and never adds one; nothing here adds one.

There is no escape hatch: a message that must vary is a fixed message with fields.

The presentation layer wired into the ``pipelex-dev`` Typer app lives in ``check_log_calls_cmd.py``.
"""

from __future__ import annotations

import ast
import copy
import json
import re
import tomllib
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol, TypeAlias, cast

from rich.default_styles import DEFAULT_STYLES
from rich.errors import StyleSyntaxError
from rich.style import Style
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

#: The trees the guard scans, relative to the repo root: the runtime and the API server, which logs through the same facade.
SCAN_ROOTS: tuple[Path, ...] = (Path("pipelex"), Path("api") / "pipelex_api")

#: The facade's own package, whose internals build messages for the sinks and are not call sites.
EXCLUDED_ROOTS: tuple[Path, ...] = (Path("pipelex") / "tools" / "log",)

#: The committed baseline of the calls that broke the rules when the guard arrived, relative to the repo root.
BASELINE_FILE = Path("log_call_baseline.toml")

#: The only version of the baseline's shape.
BASELINE_VERSION = 1

#: The modules the facade is imported from, and the name it is imported under.
FACADE_MODULES = frozenset({"pipelex", "pipelex.tools.log.log"})
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


class LogCallGuardError(Exception):
    """The guard cannot run as configured: a missing scan root or a malformed baseline, never a violation.

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
        signature: The call's identity in the baseline: its method and its message's source text.
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
# The message's signature, the same text on every supported Python
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


# --------------------------------------------------------------------------------------
# Scopes and bindings
# --------------------------------------------------------------------------------------

_ScopeNode: TypeAlias = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda


def _iter_scope_nodes(*, scope: _ScopeNode) -> Iterator[ast.AST]:
    """Every node a scope's own body holds, never descending into a nested function, class or lambda."""
    stack: list[ast.AST] = list(scope.body) if not isinstance(scope, ast.Lambda) else [scope.body]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            # The definition binds its name in this scope; its body is a scope of its own.
            continue
        stack.extend(ast.iter_child_nodes(node))


class _Binding(NamedTuple):
    """What a name is bound to in one scope: the bound expression, or ``None`` when the binding is opaque."""

    value: ast.expr | None
    lineno: int
    is_augmented: bool


def _parameter_names(*, scope: _ScopeNode) -> set[str]:
    if isinstance(scope, ast.Module | ast.ClassDef):
        return set()
    arguments = scope.args
    names = {argument.arg for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}
    if arguments.vararg is not None:
        names.add(arguments.vararg.arg)
    if arguments.kwarg is not None:
        names.add(arguments.kwarg.arg)
    return names


def _bindings_of(*, name: str, scope: _ScopeNode) -> list[_Binding]:
    """Every binding of ``name`` in the scope's own body, in source order."""
    bindings: list[_Binding] = []
    for node in _iter_scope_nodes(scope=scope):
        match node:
            case ast.Assign(targets=targets, value=value):
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        bindings.append(_Binding(value=value, lineno=node.lineno, is_augmented=False))
                    elif any(isinstance(element, ast.Name) and element.id == name for element in ast.walk(target)):
                        bindings.append(_Binding(value=None, lineno=node.lineno, is_augmented=False))
            case ast.AnnAssign(target=ast.Name(id=target_name), value=value) if target_name == name and value is not None:
                bindings.append(_Binding(value=value, lineno=node.lineno, is_augmented=False))
            case ast.AugAssign(target=ast.Name(id=target_name), value=value) if target_name == name:
                bindings.append(_Binding(value=value, lineno=node.lineno, is_augmented=True))
            case ast.NamedExpr(target=ast.Name(id=target_name), value=value) if target_name == name:
                bindings.append(_Binding(value=value, lineno=node.lineno, is_augmented=False))
            case ast.For(target=target) | ast.AsyncFor(target=target):
                if any(isinstance(element, ast.Name) and element.id == name for element in ast.walk(target)):
                    bindings.append(_Binding(value=None, lineno=node.lineno, is_augmented=False))
            case ast.withitem(optional_vars=optional_vars) if optional_vars is not None:
                if any(isinstance(element, ast.Name) and element.id == name for element in ast.walk(optional_vars)):
                    bindings.append(_Binding(value=None, lineno=optional_vars.lineno, is_augmented=False))
            case ast.ExceptHandler(name=handler_name) if handler_name == name:
                bindings.append(_Binding(value=None, lineno=node.lineno, is_augmented=False))
            case ast.Import(names=aliases) | ast.ImportFrom(names=aliases):
                if any((alias.asname or alias.name.partition(".")[0]) == name for alias in aliases):
                    bindings.append(_Binding(value=None, lineno=node.lineno, is_augmented=False))
            case ast.FunctionDef(name=def_name) | ast.AsyncFunctionDef(name=def_name) | ast.ClassDef(name=def_name) if def_name == name:
                bindings.append(_Binding(value=None, lineno=node.lineno, is_augmented=False))
            case _:
                pass
    return sorted(bindings, key=lambda binding: binding.lineno)


# --------------------------------------------------------------------------------------
# Classifying a message
# --------------------------------------------------------------------------------------

#: The form a message expression takes: ``None`` when it is fixed, otherwise the rule it breaks and what it is,
#: as a noun phrase the report completes ("the message is an f-string").
_Form: TypeAlias = RuleBreach | None


class _NameFormResolver(Protocol):
    """Reads the form of what a name holds, the names already followed in ``seen``."""

    def __call__(self, *, name: str, seen: frozenset[str]) -> _Form: ...


class _NameFragmentsResolver(Protocol):
    """Reads the literal text a name's bindings hold, the names already followed in ``seen``."""

    def __call__(self, *, name: str, seen: frozenset[str]) -> list[str]: ...


def _classify(*, expr: ast.expr, resolve_name: _NameFormResolver, seen: frozenset[str]) -> _Form:
    """Whether a message expression is fixed, and if not, the rule it breaks.

    The outermost form names the rule: ``f"{x}" + "!"`` is a concatenation.
    """
    match expr:
        case ast.Constant(value=str()):
            return None
        case ast.JoinedStr(values=values):
            if any(isinstance(value, ast.FormattedValue) for value in values):
                return RuleBreach(rule=LogCallRule.F_STRING, detail="an f-string")
            return None
        case ast.BinOp(op=ast.Add(), left=left, right=right):
            left_form = _classify(expr=left, resolve_name=resolve_name, seen=seen)
            right_form = _classify(expr=right, resolve_name=resolve_name, seen=seen)
            if left_form is None and right_form is None:
                return None
            return RuleBreach(rule=LogCallRule.CONCATENATION, detail="a `+` concatenation")
        case ast.BinOp(op=ast.Mod()):
            return RuleBreach(rule=LogCallRule.PERCENT_FORMAT, detail="a `%` format")
        case ast.Call(func=ast.Attribute(attr="format")):
            return RuleBreach(rule=LogCallRule.FORMAT_CALL, detail="a `.format()` call")
        case ast.IfExp(body=body, orelse=orelse):
            return _classify(expr=body, resolve_name=resolve_name, seen=seen) or _classify(expr=orelse, resolve_name=resolve_name, seen=seen)
        case ast.Name(id=name):
            return resolve_name(name=name, seen=seen)
        case _:
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{_short_source(expr=expr)}`, not a literal")


def _short_source(*, expr: ast.expr, limit: int = 60) -> str:
    text = render_source(expr=expr)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _literal_fragments(*, expr: ast.expr, resolve_fragments: _NameFragmentsResolver, seen: frozenset[str]) -> list[str]:
    """The literal text a message expression writes at the call or through a binding it names, for the markup rule."""
    match expr:
        case ast.Constant(value=str() as text):
            return [text]
        case ast.JoinedStr(values=values):
            return [value.value for value in values if isinstance(value, ast.Constant) and isinstance(value.value, str)]
        case ast.BinOp(op=ast.Add(), left=left, right=right):
            return [
                *_literal_fragments(expr=left, resolve_fragments=resolve_fragments, seen=seen),
                *_literal_fragments(expr=right, resolve_fragments=resolve_fragments, seen=seen),
            ]
        case ast.BinOp(op=ast.Mod(), left=left):
            return _literal_fragments(expr=left, resolve_fragments=resolve_fragments, seen=seen)
        case ast.Call(func=ast.Attribute(attr="format", value=receiver)):
            return _literal_fragments(expr=receiver, resolve_fragments=resolve_fragments, seen=seen)
        case ast.IfExp(body=body, orelse=orelse):
            return [
                *_literal_fragments(expr=body, resolve_fragments=resolve_fragments, seen=seen),
                *_literal_fragments(expr=orelse, resolve_fragments=resolve_fragments, seen=seen),
            ]
        case ast.Name(id=name):
            return resolve_fragments(name=name, seen=seen)
        case _:
            return []


# --------------------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------------------


def _facade_names(*, tree: ast.Module) -> frozenset[str]:
    """The names the module binds the ``log`` facade to, wherever it imports it."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in FACADE_MODULES:
            for alias in node.names:
                if alias.name == FACADE_NAME:
                    names.add(alias.asname or alias.name)
    return frozenset(names)


class _LogCallCollector(ast.NodeVisitor):
    """Walks one module, tracking its scopes, and records every facade call that breaks a rule."""

    def __init__(self, *, relative_path: str, module: ast.Module) -> None:
        self.relative_path = relative_path
        self.module = module
        self.facade_names = _facade_names(tree=module)
        self.offending_calls: list[OffendingCall] = []
        self._scopes: list[_ScopeNode] = [module]
        self._qualified_parts: list[str] = []

    # ---- scope tracking -------------------------------------------------------------

    def _visit_named_scope(self, *, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        # Decorators, defaults and bases run in the enclosing scope.
        for decorator in node.decorator_list:
            self.visit(decorator)
        if isinstance(node, ast.ClassDef):
            for base in (*node.bases, *node.keywords):
                self.visit(base)
        else:
            for default in (*node.args.defaults, *(default for default in node.args.kw_defaults if default is not None)):
                self.visit(default)
        self._scopes.append(node)
        self._qualified_parts.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self._qualified_parts.pop()
        self._scopes.pop()

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

    # ---- name resolution --------------------------------------------------------------

    def _lookup_scopes(self) -> list[_ScopeNode]:
        """The scopes a name read in the current one resolves through: its own, then the module's (classes are skipped)."""
        current = self._scopes[-1]
        if current is self.module:
            return [self.module]
        return [current, self.module]

    def _resolve_form(self, *, name: str, seen: frozenset[str]) -> _Form:
        """The form of what a name holds, read from its bindings in the current scope, else at module level."""
        if name in seen:
            return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, built from itself")
        seen |= {name}
        for scope in self._lookup_scopes():
            if name in _parameter_names(scope=scope):
                return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, a parameter")
            bindings = _bindings_of(name=name, scope=scope)
            if not bindings:
                continue
            for binding in bindings:
                if binding.value is None:
                    return RuleBreach(
                        rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound at line {binding.lineno} to something other than a literal"
                    )
                if binding.is_augmented:
                    return RuleBreach(rule=LogCallRule.CONCATENATION, detail=f"`{name}`, extended with `+=` at line {binding.lineno}")
                form = _classify(expr=binding.value, resolve_name=self._resolve_form, seen=seen)
                if form is not None:
                    return RuleBreach(rule=form.rule, detail=f"`{name}`, bound at line {binding.lineno} to {form.detail}")
            return None
        return RuleBreach(rule=LogCallRule.NON_LITERAL, detail=f"`{name}`, bound to no literal in this function or at module level")

    def _resolve_fragments(self, *, name: str, seen: frozenset[str]) -> list[str]:
        """The literal text the bindings of a name hold, read the way ``_resolve_form`` reads them."""
        if name in seen:
            return []
        seen |= {name}
        for scope in self._lookup_scopes():
            if name in _parameter_names(scope=scope):
                return []
            bindings = _bindings_of(name=name, scope=scope)
            if not bindings:
                continue
            fragments: list[str] = []
            for binding in bindings:
                if binding.value is not None:
                    fragments.extend(_literal_fragments(expr=binding.value, resolve_fragments=self._resolve_fragments, seen=seen))
            return fragments
        return []

    # ---- the calls --------------------------------------------------------------------

    @override
    def visit_Call(self, node: ast.Call) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        method = self._facade_method(node=node)
        if method is not None:
            self._check_call(node=node, method=method)
        self.generic_visit(node)

    def _facade_method(self, *, node: ast.Call) -> str | None:
        match node.func:
            case ast.Attribute(value=ast.Name(id=receiver), attr=attr) if receiver in self.facade_names and attr in MARKUP_BOUND_METHODS:
                return attr
            case _:
                return None

    def _check_call(self, *, node: ast.Call, method: str) -> None:
        content = node.args[0] if node.args else next((keyword.value for keyword in node.keywords if keyword.arg == CONTENT_KEYWORD), None)
        parts: list[tuple[str | None, ast.expr]] = [(None, content)] if content is not None else []
        parts.extend((keyword.arg, keyword.value) for keyword in node.keywords if keyword.arg in TITLE_KEYWORDS)

        breaches: list[RuleBreach] = []
        if method in INTERPOLATION_BOUND_METHODS:
            for label, expr in parts:
                form = _classify(expr=expr, resolve_name=self._resolve_form, seen=frozenset())
                if form is not None:
                    breaches.append(RuleBreach(rule=form.rule, detail=f"{_part_name(label=label)} is {form.detail}"))
        for label, expr in parts:
            for fragment in _literal_fragments(expr=expr, resolve_fragments=self._resolve_fragments, seen=frozenset()):
                for tag in find_markup_tags(text=fragment):
                    breaches.append(RuleBreach(rule=LogCallRule.MARKUP, detail=f"{_part_name(label=label)} holds the markup tag `{tag}`"))

        if not breaches:
            return
        self.offending_calls.append(
            OffendingCall(
                relative_path=self.relative_path,
                qualified_name=self._qualified_name,
                lineno=node.lineno,
                signature=call_signature(method=method, parts=parts),
                breaches=tuple(breaches),
            )
        )


def _part_name(*, label: str | None) -> str:
    """How the report names a part of a call's message: the message itself, or the keyword a title rides."""
    return "the message" if label is None else f"`{label}=`"


def call_signature(*, method: str, parts: Sequence[tuple[str | None, ast.expr]]) -> str:
    """A call's identity in the baseline: its method, then its message's source and any title's, never a line."""
    rendered = [render_source(expr=expr) if label is None else f"{label}={render_source(expr=expr)}" for label, expr in parts]
    return f"{method}: {', '.join(rendered) or '<no message>'}"


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
    "Keyed by <relative_path>::<qualified_name>, each call listed by its method and its message's source.",
    "It only shrinks: convert a call, then remove its signature (pipelex-dev check-log-calls --prune).",
    "Never add an entry. See docs/contribute/log-calls.md.",
)


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
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        msg = f"The log-call baseline '{path}' is not valid TOML: {exc}"
        raise LogCallGuardError(msg) from exc
    version = raw.pop("version", None)
    if version != BASELINE_VERSION:
        msg = f"The log-call baseline '{path}' must declare `version = {BASELINE_VERSION}` (found: {version!r})"
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


def build_baseline(*, offending: Sequence[OffendingCall]) -> Baseline:
    """The baseline that lists exactly the given calls, which is how the committed one was first generated."""
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


_TOML_SHORT_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _toml_basic_string(*, text: str) -> str:
    """A TOML basic string holding ``text``: the short escapes where TOML has one, a unicode escape for any other control character."""
    escaped: list[str] = []
    for character in text:
        if character in _TOML_SHORT_ESCAPES:
            escaped.append(_TOML_SHORT_ESCAPES[character])
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            escaped.append(f"\\u{ord(character):04X}")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def render_baseline(*, baseline: Mapping[str, Sequence[str]]) -> str:
    """The baseline file's text: the header, the version, then every key in sorted order with its sorted calls.

    Written by hand rather than through a TOML library so that it comes out exactly as ``plxt fmt`` leaves it, and a
    prune followed by ``make format`` moves nothing else.
    """
    lines = [f"# {line}" for line in _BASELINE_HEADER]
    lines.extend(["", f"version = {BASELINE_VERSION}"])
    for key in sorted(baseline):
        lines.extend(["", f"[{_toml_basic_string(text=key)}]", "calls = ["])
        lines.extend(f"  {_toml_basic_string(text=signature)}," for signature in sorted(baseline[key]))
        lines.append("]")
    return "\n".join(lines) + "\n"


def write_baseline(*, baseline: Mapping[str, Sequence[str]], repo_root: Path) -> None:
    """Write the baseline file at the repo root."""
    (repo_root / BASELINE_FILE).write_text(render_baseline(baseline=baseline), encoding="utf-8")


def package_area_of(*, key: str) -> str:
    """The package area a baseline key belongs to, for the report: ``pipelex/<area>``, ``pipelex`` for a root module, or the API server."""
    parts = key.partition("::")[0].split("/")
    if parts[0] == "api":
        return "api/pipelex_api"
    if len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]
