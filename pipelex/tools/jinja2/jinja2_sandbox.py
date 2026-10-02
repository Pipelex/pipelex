"""The sandbox every Jinja2 template renders under: templates read data and call methods of plain values.

On the hosted plane a method author's prompts, compose templates, construct templates and condition
expressions render inside the shared runner and worker processes, so a template is customer code
running in-process. A plain `jinja2.Environment` lets it walk from a default global into Python module
globals, and Jinja's stock sandbox is not enough either: it refuses internals but not public methods,
so a template could still call pydantic's public constructors (`model_validate`, `model_copy`) and
forge content, such as an image pointing at another organisation's storage key.

`PipelexTemplateEnvironment` applies one policy instead:

- **Reading.** A template reads public attributes and items. A name starting with an underscore is
  refused, with a dot or with brackets, unless the value's type declares it in its template surface
  (`template_surface.py`), which is how `StuffArtefact` keeps its documented metadata fields readable.
  The one exception is a key of a plain `dict` read with brackets (`record['_id']`): a dict's items
  are data, and a key it does not hold falls back to an attribute read, which the rule above refuses.
  Jinja's own refusals (a function's globals, a frame, a class's `mro`) stay in force.
- **Calling.** A template calls Jinja's own runtime (macros, `caller`, `loop`, `cycler`, `joiner`,
  block references and the environment's globals), methods bound to an instance of a plain value type
  (`str`, numbers, dates and times, and the built-in containers), `str.format` through the sandbox's
  safe formatter, and the methods a type declares in its template surface. Everything else is
  refused: pydantic methods, `Stuff` and content methods, classes, free functions and class methods,
  and every method that changes a list, a dict or a set in place.
- **Refusing.** A refusal raises `jinja2.exceptions.SecurityError` at the point of access, which the
  render functions turn into `Jinja2TemplateSecurityError`. Jinja's stock sandbox returns an undefined
  value that prints as nothing, which would send a prompt with a hole in it.

Filters and tests are not calls in this sense: they are Pipelex's or Jinja's own code, registered by
the environment, and Jinja invokes them directly. That makes every filter trusted code with one
obligation: **a filter never calls a callable it was handed**, since that callable came from the
template's values and the policy above never vetted it. Jinja's own filters and markupsafe do look a
few names up on a value and call them, `__html__` when escaping and `items` in `dictsort` and
`xmlattr`, and a `namespace()` answers any name with whatever the template stored under it. So the
environment's `namespace` holds data only: storing a callable in one is refused.

Pipelex's own templates (the stuff viewer, the graph pages, the Mermaid pages) render under the same
policy, with no trusted variant: a trust switch is one more thing a later caller could flip on a
customer template by mistake. An internal template that needs something the policy refuses gets
plain data instead.
"""

from __future__ import annotations

import inspect
import types
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NoReturn

from jinja2.exceptions import SecurityError
from jinja2.runtime import BlockReference, Context, LoopContext, Macro, Undefined
from jinja2.sandbox import ImmutableSandboxedEnvironment, safe_range
from jinja2.utils import Cycler, Joiner, Namespace, generate_lorem_ipsum
from markupsafe import Markup
from typing_extensions import override

from pipelex.tools.jinja2.template_surface import get_template_surface

if TYPE_CHECKING:
    from collections.abc import Callable

# The types whose own methods a template may call on an instance: formatting, not program logic.
_PLAIN_VALUE_TYPES: tuple[type, ...] = (
    str,
    Markup,
    int,
    float,
    bool,
    Decimal,
    date,
    datetime,
    time,
    timedelta,
    list,
    tuple,
    dict,
    set,
    frozenset,
)


def _refuse_callable_in_namespace(*, name: str, value: object) -> None:
    # An undefined value is callable only so that calling it fails as an undefined value: storing it is harmless.
    if callable(value) and not isinstance(value, Undefined):
        msg = f"A template may not store {_describe_callable(obj=value)} in a namespace, as '{name}': a namespace holds data only."
        raise SecurityError(msg)


class DataNamespace(Namespace):
    """Jinja's `namespace()`, refusing to hold a callable.

    A namespace answers any attribute name with what the template stored under it, and markupsafe and some
    of Jinja's filters look a name up on a value and call it: `__html__` when escaping (`e`, `safe`,
    `striptags`, HTML autoescaping) and `items` in `dictsort` and `xmlattr`. A callable stored in a
    namespace would be called there without passing the sandbox's call check.
    """

    def __init__(self, /, *args: Any, **kwargs: Any) -> None:
        values: dict[str, Any] = dict(*args, **kwargs)
        for name, value in values.items():
            _refuse_callable_in_namespace(name=name, value=value)
        super().__init__(values)

    @override
    def __setitem__(self, name: str, value: Any) -> None:
        _refuse_callable_in_namespace(name=name, value=value)
        super().__setitem__(name, value)


# The callables the environment itself puts in a template's globals (`range` is the sandbox's capped one,
# `namespace` the data-only one).
_JINJA_GLOBAL_CALLABLES: tuple[Callable[..., Any], ...] = (safe_range, dict, generate_lorem_ipsum, Cycler, Joiner, DataNamespace)

# Instances of Jinja's runtime a template calls directly: `macro()`, `caller()`, a recursive `loop()`,
# `self.block()` and `super()`, `joiner()`. Calling an undefined value is allowed so that it keeps
# failing as an undefined value rather than as a refusal.
_JINJA_CALLABLE_INSTANCE_TYPES: tuple[type, ...] = (Macro, LoopContext, BlockReference, Joiner, Undefined)

# Instances of Jinja's runtime whose methods a template calls: `loop.cycle()`, `loop.changed()`,
# `cycler.next()`, `cycler.reset()`.
_JINJA_METHOD_OWNER_TYPES: tuple[type, ...] = (LoopContext, Cycler, BlockReference)

# The methods that change a mutable plain value in place, listed here rather than taken from Jinja's
# `modifies_known_mutable`, whose list misses `set.intersection_update`. The test suite checks this list
# against every public method of each type, so a method a later Python adds cannot slip through.
_MUTATING_METHOD_NAMES: dict[type, frozenset[str]] = {
    list: frozenset({"append", "clear", "extend", "insert", "pop", "remove", "reverse", "sort"}),
    dict: frozenset({"clear", "pop", "popitem", "setdefault", "update"}),
    set: frozenset({"add", "clear", "difference_update", "discard", "intersection_update", "pop", "remove", "symmetric_difference_update", "update"}),
}

_MISSING = object()


class _SandboxedStrFormat:
    """The `str.format` or `str.format_map` of a string, routed through the sandbox's safe formatter.

    Jinja builds this wrapper when a template reads `format` on a string, so that the replacement
    fields of the format string (`{0.name}`, `{0[key]}`) go through the environment's own attribute
    and item checks. Wrapping it in a type of its own lets the call policy recognise it by type,
    while the raw `str.format` stays refused.
    """

    __slots__ = ("_format",)

    def __init__(self, format_function: Callable[..., str]) -> None:
        self._format = format_function

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return self._format(*args, **kwargs)


def _is_private_name(*, name: str) -> bool:
    return name.startswith("_")


def _declares_private_name(*, obj: object, name: str) -> bool:
    surface = get_template_surface(obj)
    return surface is not None and name in surface.private_names


def _is_jinja_runtime_callable(*, obj: object) -> bool:
    if isinstance(obj, _JINJA_CALLABLE_INSTANCE_TYPES):
        return True
    if any(obj is jinja_global for jinja_global in _JINJA_GLOBAL_CALLABLES):
        return True
    if isinstance(obj, types.MethodType):
        bound_to = obj.__self__
        return not isinstance(bound_to, type) and isinstance(bound_to, _JINJA_METHOD_OWNER_TYPES)
    return False


def _is_plain_value_method(*, obj: object) -> bool:
    """Whether `obj` is a method a plain value type defines, bound to an instance of that type.

    The binding has to be to an instance, so a class method reached through an instance
    (`created_at.now()`, which reads the clock) is refused. The method has to be the plain type's own,
    so a subclass (a `StrEnum` member is a `str`) cannot add a callable method or override one.
    """
    if not isinstance(obj, (types.BuiltinMethodType, types.MethodType)):
        return False
    bound_to: object = getattr(obj, "__self__", None)
    if bound_to is None or isinstance(bound_to, (type, types.ModuleType)):
        return False
    plain_type = next((klass for klass in type(bound_to).__mro__ if klass in _PLAIN_VALUE_TYPES), None)
    if plain_type is None:
        return False
    name = obj.__name__
    if isinstance(bound_to, str) and name in {"format", "format_map"}:
        # Only the sandbox's own wrapper formats a string: the raw method would resolve `{0.__class__}`.
        return False
    if name in _MUTATING_METHOD_NAMES.get(plain_type, frozenset()):
        return False
    plain_member = inspect.getattr_static(plain_type, name, _MISSING)
    return plain_member is not _MISSING and inspect.getattr_static(type(bound_to), name, _MISSING) is plain_member


def _is_declared_template_method(*, obj: object) -> bool:
    """Whether `obj` is a method the type of its instance declares in its template surface."""
    if not isinstance(obj, types.MethodType):
        return False
    bound_to = obj.__self__
    if isinstance(bound_to, type):
        return False
    surface = get_template_surface(bound_to)
    if surface is None or obj.__name__ not in surface.callable_names:
        return False
    return inspect.getattr_static(type(bound_to), obj.__name__, _MISSING) is obj.__func__


def _describe_callable(*, obj: object) -> str:
    """Name a refused callable by what it is and what it was reached on, never by its value's repr."""
    if isinstance(obj, (types.BuiltinMethodType, types.MethodType)):
        name = obj.__name__
        bound_to: object = getattr(obj, "__self__", None)
        if isinstance(bound_to, type):
            return f"the method '{name}' of the class '{bound_to.__name__}'"
        if bound_to is None or isinstance(bound_to, types.ModuleType):
            return f"the function '{name}'"
        return f"the method '{name}' of a '{type(bound_to).__name__}' value"
    if isinstance(obj, type):
        return f"the class '{obj.__name__}'"
    if isinstance(obj, types.FunctionType):
        return f"the function '{obj.__name__}'"
    return f"a '{type(obj).__name__}' value"


class PipelexTemplateEnvironment(ImmutableSandboxedEnvironment):
    """The Jinja2 environment every Pipelex template renders under. The module docstring states its policy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.globals["namespace"] = DataNamespace

    @override
    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        if _is_private_name(name=attr) and _declares_private_name(obj=obj, name=attr):
            return True
        return super().is_safe_attribute(obj, attr, value)

    @override
    def is_safe_callable(self, obj: Any) -> bool:
        if not super().is_safe_callable(obj):
            return False
        return (
            isinstance(obj, _SandboxedStrFormat)
            or _is_jinja_runtime_callable(obj=obj)
            or _is_plain_value_method(obj=obj)
            or _is_declared_template_method(obj=obj)
        )

    @override
    def getattr(self, obj: Any, attribute: str) -> Any:
        # Refuse before the lookup, so an undeclared private name never runs a property or a
        # `__getattr__`, and never reaches Jinja's fallback to `obj[attribute]`, which it does not check.
        if _is_private_name(name=attribute) and not isinstance(obj, Undefined) and not _declares_private_name(obj=obj, name=attribute):
            self.unsafe_undefined(obj, attribute)
        return super().getattr(obj, attribute)

    @override
    def getitem(self, obj: Any, argument: Any) -> Any:
        # Jinja tries `obj[argument]` first and checks the name only when that fails, so an object whose
        # `__getitem__` answers any key would hand over what a dot could not: refuse the name up front.
        # A plain dict is the exception: its items are data, and a key it does not hold falls back to
        # an attribute read, which `is_safe_attribute` refuses for every underscore name.
        if (
            isinstance(argument, str)
            and _is_private_name(name=argument)
            and type(obj) is not dict
            and not isinstance(obj, Undefined)
            and not _declares_private_name(obj=obj, name=argument)
        ):
            self.unsafe_undefined(obj, argument)
        return super().getitem(obj, argument)

    @override
    def unsafe_undefined(self, obj: Any, attribute: str) -> NoReturn:
        msg = f"A template may not read '{attribute}' on a '{type(obj).__name__}' value."
        raise SecurityError(msg)

    @override
    def wrap_str_format(self, value: Any) -> Callable[..., str] | None:
        format_function = super().wrap_str_format(value)
        if format_function is None:
            return None
        return _SandboxedStrFormat(format_function)

    @override
    def call(self, context: Context, obj: Any, /, *args: Any, **kwargs: Any) -> Any:
        if not self.is_safe_callable(obj):
            msg = f"A template may not call {_describe_callable(obj=obj)}: templates read data and call methods of plain values only."
            raise SecurityError(msg)
        return context.call(obj, *args, **kwargs)
