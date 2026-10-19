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
  block references and the environment's globals), the methods of a plain value type (`str`, numbers,
  dates and times, and the built-in containers) that the budget's table lists for that type
  (`PLAIN_VALUE_METHOD_COSTS` in `jinja2_render_costs.py`), `str.format` through the sandbox's safe
  formatter, and the methods a type declares in its template surface. Everything else is refused:
  pydantic methods, `Stuff` and content methods, classes, free functions and class methods, every
  method that changes a list, a dict or a set in place, and the few that produce bytes.
- **Refusing.** A refusal raises `jinja2.exceptions.SecurityError` at the point of access, as the
  `SandboxRefusalError` that words it with the names it quotes and without them and carries the bare
  name it refused, which the render functions turn into `Jinja2TemplateSecurityError`, a Pipelex
  `SecurityError` like the runtime's other policy refusals, quoting and passing a name on only where
  the template spells it. Jinja's stock sandbox returns an undefined value that prints as nothing,
  which would send a prompt with a hole in it.
- **Spending.** What a template may reach says nothing about what it may spend, so every render also
  spends from one budget (`jinja2_render_budget.py`), charged by the hooks of this class, by wrappers
  around every filter and test, and by a rewrite of the parsed template for what no hook reaches
  (`jinja2_render_charging.py`, `jinja2_render_rewrite.py`). Converting Markdown, which markupsafe
  does through `__html__` where no hook sees it, charges the budget the template makes active while it
  renders (`markdown_parser.py`). An overdraft raises `RenderBudgetExceededError`, which the render
  functions turn into `Jinja2TemplateBudgetError`.

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
from typing import TYPE_CHECKING, Any, NamedTuple, NoReturn, cast

from jinja2.runtime import BlockReference, Context, LoopContext, Macro, Undefined
from jinja2.sandbox import ImmutableSandboxedEnvironment, safe_range
from jinja2.utils import Cycler, Joiner, Namespace, generate_lorem_ipsum
from markupsafe import Markup
from typing_extensions import override

from pipelex.tools.jinja2.exceptions import SandboxRefusalError
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, DescribedOperation, active_render_budget, compare_weight
from pipelex.tools.jinja2.jinja2_render_charging import (
    INTERNAL_FILTERS,
    BudgetedContext,
    BudgetedTemplate,
    SandboxedStrFormat,
    charge_registered_functions,
    charged_binop,
    charged_call,
    make_charged_finalize,
)
from pipelex.tools.jinja2.jinja2_render_costs import PLAIN_VALUE_METHOD_COSTS
from pipelex.tools.jinja2.jinja2_render_rewrite import rewrite_for_render_budget
from pipelex.tools.jinja2.template_surface import get_template_surface

if TYPE_CHECKING:
    from collections.abc import Callable

    from jinja2 import nodes

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
        # The name a template stores under can be a value of the run's data (`namespace({key: value})`).
        callable_description = _describe_callable(obj=value)
        msg = f"A template may not store {callable_description.text} in a namespace, as '{name}': a namespace holds data only."
        anonymous_msg = f"A template may not store {callable_description.anonymous_text} in a namespace: a namespace holds data only."
        raise SandboxRefusalError(
            msg,
            named=(name, *callable_description.named),
            anonymous_message=anonymous_msg,
            refused_name=_callable_name(obj=value),
        )


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

_MISSING = object()


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
    so a subclass (a `StrEnum` member is a `str`) cannot add a callable method or override one, and it
    has to be listed for that type in `PLAIN_VALUE_METHOD_COSTS`, which leaves out the methods that
    change a value in place and those whose cost the render budget cannot bound.
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
    # `format` and `format_map` are not listed: only the sandbox's own wrapper formats a string, since
    # the raw method would resolve `{0.__class__}`.
    if name not in PLAIN_VALUE_METHOD_COSTS[plain_type]:
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


def _callable_name(*, obj: object) -> str:
    """The bare name of a refused callable, as a template reaches for it: a method's, a function's, a macro's or a class's name.

    A callable value of another kind, which has no name of its own, is named by its class, a name of code.
    """
    if isinstance(obj, (types.BuiltinMethodType, types.MethodType, types.FunctionType, type)):
        return obj.__name__
    if isinstance(obj, Macro):
        return obj.name
    return type(obj).__name__


class _CallableDescription(NamedTuple):
    """A refused callable described with its name, ``text``, and without it, ``anonymous_text``.

    The name is the one a template reached it by when it read it with a dot, but one read by ``obj[key]`` or
    ``obj | attr(key)`` is reached by a value of the run's data: ``named`` holds the names ``text`` quotes. The class a
    value is of is named in both, a name of code.
    """

    text: str
    anonymous_text: str
    named: tuple[str, ...]


def _describe_callable(*, obj: object) -> _CallableDescription:
    """Name a refused callable by what it is and what it was reached on, never by its value's repr."""
    if isinstance(obj, (types.BuiltinMethodType, types.MethodType)):
        name = obj.__name__
        bound_to: object = getattr(obj, "__self__", None)
        if isinstance(bound_to, type):
            return _CallableDescription(
                text=f"the method '{name}' of the class '{bound_to.__name__}'",
                anonymous_text=f"a method of the class '{bound_to.__name__}'",
                named=(name,),
            )
        if bound_to is None or isinstance(bound_to, types.ModuleType):
            return _CallableDescription(text=f"the function '{name}'", anonymous_text="a function", named=(name,))
        return _CallableDescription(
            text=f"the method '{name}' of a '{type(bound_to).__name__}' value",
            anonymous_text=f"a method of a '{type(bound_to).__name__}' value",
            named=(name,),
        )
    if isinstance(obj, Macro):
        return _CallableDescription(text=f"the macro '{obj.name}'", anonymous_text="a macro", named=(obj.name,))
    if isinstance(obj, type):
        return _CallableDescription(text=f"the class '{obj.__name__}'", anonymous_text="a class", named=(obj.__name__,))
    if isinstance(obj, types.FunctionType):
        return _CallableDescription(text=f"the function '{obj.__name__}'", anonymous_text="a function", named=(obj.__name__,))
    value_description = f"a '{type(obj).__name__}' value"
    return _CallableDescription(text=value_description, anonymous_text=value_description, named=())


def _describe_call(*, obj: object) -> DescribedOperation:
    """A call the render budget refused, described with the callable's name and without it (see `_describe_callable`)."""
    callable_description = _describe_callable(obj=obj)
    return DescribedOperation(
        text=f"calling {callable_description.text}",
        anonymous_text=f"calling {callable_description.anonymous_text}",
        named=callable_description.named,
    )


class PipelexTemplateEnvironment(ImmutableSandboxedEnvironment):
    """The Jinja2 environment every Pipelex template renders under. The module docstring states its policy.

    `render_budget_units` is the budget each render gets. A caller's `finalize` is passed here, never
    assigned afterwards, since the environment's own `finalize` wraps it to charge what is printed.
    """

    context_class = BudgetedContext
    template_class = BudgetedTemplate
    intercepted_binops = frozenset({"+", "-", "*", "/", "//", "%", "**"})

    def __init__(
        self,
        *args: Any,
        finalize: Callable[..., Any] | None = None,
        render_budget_units: int = DEFAULT_RENDER_BUDGET_UNITS,
        **kwargs: Any,
    ) -> None:
        self.render_budget_units = render_budget_units
        self._charged_finalize = make_charged_finalize(inner=finalize)
        super().__init__(*args, finalize=self._charged_finalize, **kwargs)
        self.globals["namespace"] = DataNamespace
        self.filters.update(INTERNAL_FILTERS)

    @override
    def _generate(self, source: nodes.Template, name: str | None, filename: str | None, defer_init: bool = False) -> str:
        if self.finalize is not self._charged_finalize:
            msg = "A PipelexTemplateEnvironment takes its finalize at construction: one assigned afterwards would print uncharged."
            raise RuntimeError(msg)
        charge_registered_functions(filters=self.filters, tests=cast("dict[str, Callable[..., Any]]", self.tests))
        rewritten = rewrite_for_render_budget(source)
        rewritten.set_environment(self)
        return super()._generate(rewritten, name, filename, defer_init=defer_init)

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
            isinstance(obj, SandboxedStrFormat)
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
        key: object = argument
        if isinstance(key, tuple):
            # Reading with a tuple key hashes every element of it again, nested ones included.
            budget = active_render_budget()
            if budget is not None:
                budget.charge(units=compare_weight(key, limit=budget.remaining), operation="reading an item by a tuple key")
        return super().getitem(obj, argument)

    @override
    def unsafe_undefined(self, obj: Any, attribute: str) -> NoReturn:
        # The attribute is the template's own name for `.name`, but a value of the run's data for `obj[key]` or
        # `obj | attr(key)`.
        type_name = type(obj).__name__
        msg = f"A template may not read '{attribute}' on a '{type_name}' value."
        anonymous_msg = f"A template may not read an unsafe name on a '{type_name}' value."
        raise SandboxRefusalError(msg, named=(attribute,), anonymous_message=anonymous_msg, refused_name=attribute)

    @override
    def wrap_str_format(self, value: Any) -> Callable[..., str] | None:
        format_function = super().wrap_str_format(value)
        if format_function is None:
            return None
        return SandboxedStrFormat(
            format_function=format_function, environment=self, template=value.__self__, is_format_map=value.__name__ == "format_map"
        )

    @override
    def call(self, context: Context, obj: Any, /, *args: Any, **kwargs: Any) -> Any:
        if not self.is_safe_callable(obj):
            callable_description = _describe_callable(obj=obj)
            msg = f"A template may not call {callable_description.text}: templates read data and call methods of plain values only."
            anonymous_msg = (
                f"A template may not call {callable_description.anonymous_text}: templates read data and call methods of plain values only."
            )
            raise SandboxRefusalError(msg, named=callable_description.named, anonymous_message=anonymous_msg, refused_name=_callable_name(obj=obj))
        # A callable the sandbox lets a template call is a method of code, a plain value's or one a type declares, or the
        # template's own macro, so the budget's message names it, but only where the template spells its name: one read
        # by `obj[key]` or `obj | attr(key)` is named by a value of the run's data.
        return charged_call(context=context, obj=obj, args=args, kwargs=kwargs, operation=lambda: _describe_call(obj=obj))

    @override
    def call_binop(self, context: Context, operator: str, left: Any, right: Any) -> Any:
        return charged_binop(context=context, operator=operator, left=left, right=right, compute=self.binop_table[operator])
