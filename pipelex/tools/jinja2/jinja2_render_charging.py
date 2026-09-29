"""Where a render is charged: the hooks `PipelexTemplateEnvironment` installs, and the budget they share.

Every render gets its own `RenderBudget` with its context (`BudgetedContext`), and every hook below
reaches it through that context:

- **Calls and operators.** The sandbox's `call` and `call_binop` hooks hand over to `charged_call` and
  `charged_binop`.
- **Filters and tests.** Every filter and test registered on the environment is wrapped by
  `charged_filter` and `charged_test` before a template compiles (`charge_registered_functions`),
  which refuses a function the cost tables do not classify.
- **Printing.** `{{ value }}` goes through the environment's `finalize`, built by `make_charged_finalize`.
- **What no hook reaches.** Loops, `~`, comparisons, slices and static text compile to plain Python,
  so the environment rewrites the parsed template (`jinja2_render_rewrite.py`) to route each through
  one of the internal filters defined here.

The rule each hook applies is in `jinja2_render_budget.py`, and the estimates in `jinja2_render_costs.py`.
"""

from __future__ import annotations

import functools
import inspect
import operator
from typing import TYPE_CHECKING, Any, Final, cast

from jinja2 import pass_context
from jinja2.runtime import Context, LoopContext, Macro, markup_join, str_join
from jinja2.sandbox import SandboxedEscapeFormatter, SandboxedFormatter, safe_range
from jinja2.utils import generate_lorem_ipsum
from markupsafe import Markup, escape
from typing_extensions import override

from pipelex.tools.jinja2.jinja2_render_budget import (
    CALL_UNITS,
    DEFAULT_RENDER_BUDGET_UNITS,
    EAGER_TYPES,
    ESCAPE_FACTOR,
    STEP_UNITS,
    RenderBudget,
    charged_if_lazy,
    charged_iterable,
    check_int_result,
    compare_weight,
    is_data_object,
    produced_size,
    refuse_int_result,
    size_of,
    text_size,
)
from pipelex.tools.jinja2.jinja2_render_costs import (
    FILTER_COSTS,
    INTEGER_FILTERS,
    LINEAR,
    PLAIN_VALUE_METHOD_COSTS,
    TEST_COSTS,
    CostInputs,
    OperationCost,
    comparison_units,
    escaped_text_size,
    format_field_units,
    lipsum_units,
    percent_format_units,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sized

    from jinja2.environment import Environment

# The key a render's budget is kept under among its context's variables. It is no identifier, so no
# template can name it, and an included template, whose context is built from its includer's
# variables, shares it.
RENDER_BUDGET_KEY: Final = "pipelex:render-budget"


class BudgetedContext(Context):
    """A render's context, carrying the budget the render spends from."""

    def __init__(
        self,
        environment: Environment,
        parent: dict[str, Any],
        name: str | None,
        blocks: dict[str, Callable[[Context], Any]],
        **kwargs: Any,
    ) -> None:
        super().__init__(environment, parent, name, blocks, **kwargs)
        budget = parent.get(RENDER_BUDGET_KEY)
        if not isinstance(budget, RenderBudget):
            total: int = getattr(environment, "render_budget_units", DEFAULT_RENDER_BUDGET_UNITS)
            budget = RenderBudget(total=total)
            self.vars[RENDER_BUDGET_KEY] = budget
        self.render_budget: RenderBudget = budget


def render_budget_of(context: Context) -> RenderBudget:
    """The budget of the render `context` belongs to."""
    try:
        return cast("BudgetedContext", context).render_budget
    except AttributeError:
        msg = f"A Pipelex template renders with a '{BudgetedContext.__name__}', not a '{type(context).__name__}'"
        raise TypeError(msg) from None


def _inputs_units(*, values: tuple[Any, ...], keywords: dict[str, Any], step: int = STEP_UNITS) -> int:
    units = step
    for value in values:
        units += size_of(value)
    for value in keywords.values():
        units += size_of(value)
    return units


def _charge_result(*, budget: RenderBudget, result: Any, operation: str | Callable[[], str], produces_int: bool) -> Any:
    if produces_int and type(result) is int:
        check_int_result(value=result, operation=operation() if callable(operation) else operation)
    budget.charge(units=produced_size(result), operation=operation)
    return result


async def _charge_awaited(*, budget: RenderBudget, pending: Awaitable[Any], operation: str | Callable[[], str], produces_int: bool) -> Any:
    result = await pending
    return _charge_result(budget=budget, result=result, operation=operation, produces_int=produces_int)


def _finish(*, budget: RenderBudget, result: Any, operation: str | Callable[[], str], produces_int: bool = False) -> Any:
    """Charge an operation's result, once awaited when the operation is async."""
    if type(result) not in EAGER_TYPES and inspect.isawaitable(result):
        return _charge_awaited(budget=budget, pending=result, operation=operation, produces_int=produces_int)
    return _charge_result(budget=budget, result=result, operation=operation, produces_int=produces_int)


########################################################################################
# Calls
########################################################################################


_FORMATTING: Final = "formatting a replacement field"


class _ChargedFormatter(SandboxedFormatter):
    """The sandbox's formatter, charging every replacement field it formats.

    A field is formatted with its spec already resolved, so a width taken from an argument (`{:{w}}`)
    or from a mapping is read as the number it is, and the value is whatever the field's name led to
    (`{0.text}`), after the sandbox's own checks.
    """

    def __init__(self, environment: Environment, *, budget: RenderBudget, escaping: bool, **kwargs: Any) -> None:
        super().__init__(environment, **kwargs)
        self._budget = budget
        self._escaping = escaping
        self._text_sizes: dict[int, int] = {}

    @override
    def format_field(self, value: Any, format_spec: str) -> Any:
        budget = self._budget
        estimate = format_field_units(value=value, spec=format_spec, limit=budget.remaining, escaping=self._escaping, memo=self._text_sizes)
        budget.afford(units=STEP_UNITS + estimate, operation=_FORMATTING)
        text = super().format_field(value, format_spec)
        budget.charge(units=STEP_UNITS + size_of(text), operation=_FORMATTING)
        return text


class _ChargedEscapeFormatter(_ChargedFormatter, SandboxedEscapeFormatter):
    """The charged formatter of a markup format string, which escapes what it inserts."""


class SandboxedStrFormat:
    """The `str.format` or `str.format_map` of a string, routed through the sandbox's safe formatter.

    Jinja builds its own wrapper when a template reads `format` on a string, so that the replacement
    fields of the format string (`{0.name}`, `{0[key]}`) go through the environment's own attribute
    and item checks. Wrapping that in a type of its own lets the call policy recognise it by type,
    while the raw `str.format` stays refused, and lets a template's call format through a formatter
    that charges every field it formats (`format_charged`).
    """

    __slots__ = ("_environment", "_format", "_is_format_map", "template")

    def __init__(self, *, format_function: Callable[..., str], environment: Environment, template: str, is_format_map: bool) -> None:
        self._format = format_function
        self._environment = environment
        self._is_format_map = is_format_map
        self.template = template

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return self._format(*args, **kwargs)

    def format_charged(self, *, args: tuple[Any, ...], kwargs: dict[str, Any], budget: RenderBudget) -> str:
        """Format as `__call__` does, charging every replacement field to `budget` as it is formatted."""
        if self._is_format_map:
            if kwargs or len(args) != 1:
                # Jinja's own wrapper raises the error Python's `format_map` would.
                return self._format(*args, **kwargs)
            mapping: Any = args[0]
            args, kwargs = (), mapping
        formatter: _ChargedFormatter
        if isinstance(self.template, Markup):
            formatter = _ChargedEscapeFormatter(self._environment, budget=budget, escaping=True, escape=self.template.escape)
        else:
            formatter = _ChargedFormatter(self._environment, budget=budget, escaping=False)
        return type(self.template)(formatter.vformat(self.template, args, kwargs))


def _plain_method_cost(*, obj: Any) -> tuple[Any, OperationCost] | None:
    """The value a plain-value method is bound to and the method's cost, or None for any other callable."""
    bound_to: Any = getattr(obj, "__self__", None)
    if bound_to is None or isinstance(bound_to, type):
        return None
    name = getattr(obj, "__name__", "")
    for klass in type(bound_to).__mro__:
        table = PLAIN_VALUE_METHOD_COSTS.get(klass)
        if table is not None:
            cost = table.get(name)
            return (bound_to, cost) if cost is not None else None
    return None


def _call_inputs_units(*, obj: Any, plain_method: tuple[Any, OperationCost] | None, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
    """What a call is charged for its inputs, before it runs."""
    if plain_method is not None:
        bound_value, cost = plain_method
        return _inputs_units(values=(bound_value, *args) if cost.reads_value else args, keywords=kwargs, step=CALL_UNITS)
    if isinstance(obj, (Macro, SandboxedStrFormat)):
        # A macro takes its arguments by reference, and its body is charged step by step; a format
        # string is charged field by field.
        return CALL_UNITS
    return _inputs_units(values=args, keywords=kwargs, step=CALL_UNITS)


def charged_call(*, context: Context, obj: Any, args: tuple[Any, ...], kwargs: dict[str, Any], operation: Callable[[], str]) -> Any:
    """Make a call the sandbox has allowed, charging it to the render's budget."""
    budget = render_budget_of(context)
    plain_method = _plain_method_cost(obj=obj)
    bound_value: Any = plain_method[0] if plain_method is not None else None
    cost = plain_method[1] if plain_method is not None else LINEAR
    budget.charge(units=_call_inputs_units(obj=obj, plain_method=plain_method, args=args, kwargs=kwargs), operation=operation)
    if any(type(argument) not in EAGER_TYPES for argument in args):
        args = tuple(charged_if_lazy(value=argument, budget=budget) for argument in args)
    if kwargs:
        kwargs = {name: charged_if_lazy(value=argument, budget=budget) for name, argument in kwargs.items()}
    if cost.materializes and args and not isinstance(args[0], (str, list, tuple, dict, set, frozenset)):
        args = (list(args[0]), *args[1:])
    estimate = 0
    if isinstance(obj, SandboxedStrFormat):
        return _finish(budget=budget, result=obj.format_charged(args=args, kwargs=kwargs, budget=budget), operation=operation)
    if cost.estimate is not None:
        estimate = cost.estimate(inputs=CostInputs(value=bound_value, args=args, kwargs=kwargs, limit=budget.remaining, escaping=False))
    elif obj is generate_lorem_ipsum:
        estimate = lipsum_units(inputs=CostInputs(value=None, args=args, kwargs=kwargs, limit=budget.remaining, escaping=False))
    elif obj is safe_range:
        for bound in (*args, *kwargs.values()):
            if isinstance(bound, int):
                refuse_int_result(bits=bound.bit_length(), operation="a range bound")
    elif isinstance(obj, LoopContext) and args:
        # A recursive loop's `loop(children)` iterates `children` without passing the loop's own
        # iterable through the rewrite, so the elements are charged here.
        args = (charged_iterable(iterable=args[0], budget=budget), *args[1:])
    budget.afford(units=estimate, operation=operation)
    result = context.call(obj, *args, **kwargs)
    return _finish(budget=budget, result=result, operation=operation) if cost.reads_value else result


########################################################################################
# Operators
########################################################################################


_OPERATOR_DESCRIPTIONS: Final[dict[str, str]] = {operator: f"the operator '{operator}'" for operator in ("+", "-", "*", "/", "//", "%", "**")}


def _repeat_units(*, sequence: Any, times: Any) -> int | None:
    """The size of `sequence * times`, or None when that is not a repetition."""
    if isinstance(times, bool) or not isinstance(times, int) or not isinstance(sequence, (str, bytes, bytearray, list, tuple)):
        return None
    count: int = max(times, 0)
    per_element = 1 if isinstance(sequence, (str, bytes, bytearray)) else 8 + 64
    return len(cast("Sized", sequence)) * count * per_element


_ESTIMATED_OPERATORS: Final = frozenset({"*", "**", "%", "+"})


def _estimate_binop(*, operator: str, left: Any, right: Any, limit: int, describe: str) -> int:
    """Estimate an operator's result before it runs, refusing an integer result that would be too wide."""
    match operator:
        case "*":
            repeated = _repeat_units(sequence=left, times=right)
            if repeated is None:
                repeated = _repeat_units(sequence=right, times=left)
            if repeated is not None:
                return repeated
            if isinstance(left, int) and isinstance(right, int):
                refuse_int_result(bits=left.bit_length() + right.bit_length(), operation=describe)
        case "**":
            if isinstance(left, int) and isinstance(right, int) and right > 0 and abs(left) > 1:
                refuse_int_result(bits=(abs(left).bit_length() - 1) * right + 1, operation=describe)
        case "%":
            if isinstance(left, str):
                return percent_format_units(template=left, arguments=right, limit=limit, escaping=isinstance(left, Markup))
        case "+":
            if isinstance(left, (str, list, tuple)) and isinstance(right, (str, list, tuple)):
                # Adding text to markup escapes the text.
                left_factor = ESCAPE_FACTOR if isinstance(right, Markup) and not isinstance(left, Markup) else 1
                right_factor = ESCAPE_FACTOR if isinstance(left, Markup) and not isinstance(right, Markup) else 1
                return left_factor * size_of(left) + right_factor * size_of(right)
        case _:
            pass
    return 0


def charged_binop(*, context: Context, operator: str, left: Any, right: Any, compute: Callable[[Any, Any], Any]) -> Any:
    """Apply a binary operator the sandbox intercepted, charging it to the render's budget."""
    budget = render_budget_of(context)
    describe = _OPERATOR_DESCRIPTIONS[operator]
    budget.charge(units=STEP_UNITS + size_of(left) + size_of(right), operation=describe)
    if operator in _ESTIMATED_OPERATORS:
        budget.afford(units=_estimate_binop(operator=operator, left=left, right=right, limit=budget.remaining, describe=describe), operation=describe)
    return _charge_result(budget=budget, result=compute(left, right), operation=describe, produces_int=True)


########################################################################################
# Filters and tests
########################################################################################


def _pass_arg_of(*, function: Callable[..., Any]) -> str | None:
    """What a filter, test or finalize asked Jinja to pass before its value: the name of the mark Jinja's
    `pass_context`, `pass_eval_context` and `pass_environment` decorators leave on it.
    """
    mark = getattr(function, "jinja_pass_arg", None)
    return None if mark is None else str(mark.name)


def _first_argument(*, pass_arg: str | None, context: Context) -> tuple[Any, ...]:
    """What a filter or test asked Jinja to pass before its value, as Jinja would have passed it."""
    match pass_arg:
        case "context":
            return (context,)
        case "eval_context":
            return (context.eval_ctx,)
        case "environment":
            return (context.environment,)
        case _:
            return ()


async def _materialize_then(*, value: Any, then: Callable[[Any], Any]) -> Any:
    materialized = [element async for element in value]
    result = then(materialized)
    return await result if inspect.isawaitable(result) else result


CHARGED_MARK: Final = "pipelex_render_charged"


def _mark_charged(*, charged: Callable[..., Any], function: Callable[..., Any]) -> None:
    # `__wrapped__` lets `inspect.unwrap` find the filter or test behind the wrapper. The function's
    # `__dict__` is left behind (`updated=()`): it holds the function's own `jinja_pass_arg`, and the
    # wrapper's is its own.
    functools.update_wrapper(charged, function, updated=())
    setattr(charged, CHARGED_MARK, True)


def charged_filter(*, name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a filter so that applying it is charged to the render's budget."""
    cost = FILTER_COSTS.get(function)
    if cost is None:
        msg = f"The template filter '{name}' has no cost in the render budget's tables (jinja2_render_costs.py), so it cannot be registered."
        raise TypeError(msg)
    produces_int = function in INTEGER_FILTERS
    pass_arg = _pass_arg_of(function=function)
    operation = f"the filter '{name}'"

    def apply(*, context: Context, budget: RenderBudget, value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        escaping = bool(context.eval_ctx.autoescape)
        if cost.work is not None:
            inputs = CostInputs(value=value, args=args, kwargs=kwargs, limit=budget.remaining, escaping=escaping)
            budget.charge(units=cost.work(inputs=inputs), operation=operation)
        if cost.estimate is not None:
            inputs = CostInputs(value=value, args=args, kwargs=kwargs, limit=budget.remaining, escaping=escaping)
            budget.afford(units=cost.estimate(inputs=inputs), operation=operation)
        result = function(*_first_argument(pass_arg=pass_arg, context=context), value, *args, **kwargs)
        if not cost.reads_value:
            return result
        return _finish(budget=budget, result=result, operation=operation, produces_int=produces_int)

    @pass_context
    def charged(context: Context, value: Any, *args: Any, **kwargs: Any) -> Any:
        budget = render_budget_of(context)
        budget.charge(units=_inputs_units(values=(value, *args) if cost.reads_value else args, keywords=kwargs), operation=operation)
        value = charged_if_lazy(value=value, budget=budget)
        if cost.materializes and type(value) not in EAGER_TYPES:
            if hasattr(value, "__aiter__"):
                return _materialize_then(
                    value=value, then=lambda materialized: apply(context=context, budget=budget, value=materialized, args=args, kwargs=kwargs)
                )
            if hasattr(value, "__next__"):
                value = list(value)
        return apply(context=context, budget=budget, value=value, args=args, kwargs=kwargs)

    _mark_charged(charged=charged, function=function)
    return charged


def charged_test(*, name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a test so that applying it is charged to the render's budget."""
    cost = TEST_COSTS.get(function)
    if cost is None:
        msg = f"The template test '{name}' has no cost in the render budget's tables (jinja2_render_costs.py), so it cannot be registered."
        raise TypeError(msg)

    pass_arg = _pass_arg_of(function=function)
    operation = f"the test '{name}'"

    @pass_context
    def charged(context: Context, value: Any, *args: Any, **kwargs: Any) -> Any:
        budget = render_budget_of(context)
        # A test reads its value only when it compares it or scans its text, both charged below.
        units = _inputs_units(values=args, keywords=kwargs)
        if cost.comparison is not None and args:
            units += comparison_units(operator=cost.comparison, left=value, right=args[0], limit=budget.remaining)
        elif cost.scans_text and isinstance(value, str):
            units += len(value)
        budget.charge(units=units, operation=operation)
        return function(*_first_argument(pass_arg=pass_arg, context=context), value, *args, **kwargs)

    _mark_charged(charged=charged, function=function)
    return charged


def is_charged(*, function: Callable[..., Any]) -> bool:
    """Whether `function` is a filter or a test already wrapped to charge the render's budget."""
    return bool(getattr(function, CHARGED_MARK, False))


def charge_registered_functions(*, filters: dict[str, Callable[..., Any]], tests: dict[str, Callable[..., Any]]) -> None:
    """Wrap, in place, every filter and test registered since the last time, the budget's own filters apart.

    The environment calls this before it compiles a template, so a filter registered by assigning into
    `environment.filters`, as Jinja lets anyone do, is charged like the rest, and one the cost tables
    do not classify is refused before any template can use it.
    """
    for name, function in list(filters.items()):
        if not is_charged(function=function) and INTERNAL_FILTERS.get(name) is not function:
            filters[name] = charged_filter(name=name, function=function)
    for name, function in list(tests.items()):
        if not is_charged(function=function):
            tests[name] = charged_test(name=name, function=function)


########################################################################################
# Printing
########################################################################################


_PRINTING: Final = "printing a value"


def make_charged_finalize(*, inner: Callable[..., Any] | None) -> Callable[..., Any]:
    """The environment's `finalize`: convert a printed value to text, charged, after the caller's own `finalize`.

    Jinja converts what `finalize` returns once more (`str()`, or `escape()` under autoescape), which
    leaves text this has already converted unchanged.
    """
    inner_pass_arg = _pass_arg_of(function=inner) if inner is not None else None

    @pass_context
    def charged_finalize(context: Context, value: Any) -> Any:
        if inner is not None:
            value = inner(*_first_argument(pass_arg=inner_pass_arg, context=context), value)
        budget = render_budget_of(context)
        autoescape = context.eval_ctx.autoescape
        # An object of the run's data is not estimated: its estimate would convert it, which printing it
        # does once anyway, and it is charged once converted.
        if autoescape and not is_data_object(value=value):
            budget.afford(units=STEP_UNITS + escaped_text_size(value, limit=budget.remaining), operation=_PRINTING)
        elif type(value) is not str and not is_data_object(value=value):
            budget.afford(units=STEP_UNITS + text_size(value, limit=budget.remaining), operation=_PRINTING)
        text: Any = escape(value) if autoescape else value if isinstance(value, str) else str(value)
        budget.charge(units=STEP_UNITS + size_of(text), operation=_PRINTING)
        return text

    return charged_finalize


########################################################################################
# The internal filters the rewritten template calls
########################################################################################

ITERATE_FILTER: Final = "_pipelex_charged_iteration"
CONCAT_FILTER: Final = "_pipelex_charged_concat"
COMPARE_FILTER: Final = "_pipelex_charged_comparison"
COMPARED_FILTER: Final = "_pipelex_charged_operand"
SLICED_FILTER: Final = "_pipelex_charged_slice"

_COMPARISONS: Final[dict[str, Callable[[Any, Any], Any]]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gteq": operator.ge,
    "lt": operator.lt,
    "lteq": operator.le,
    "in": lambda left, right: left in right,
    "notin": lambda left, right: left not in right,
}


@pass_context
def charged_iteration(context: Context, iterable: Any) -> Any:
    """A loop's iterable, charged for every element the loop draws."""
    return charged_iterable(iterable=iterable, budget=render_budget_of(context))


@pass_context
def charged_concat(context: Context, parts: list[Any]) -> Any:
    """`a ~ b ~ c`: join the parts' text, estimated before it is built."""
    budget = render_budget_of(context)
    autoescape = bool(context.eval_ctx.autoescape)
    measure = escaped_text_size if autoescape else text_size
    estimate = sum(measure(part, limit=budget.remaining) for part in parts)
    budget.afford(units=STEP_UNITS + estimate, operation="joining text with '~'")
    joined = markup_join(parts) if autoescape else str_join(parts)
    budget.charge(units=STEP_UNITS + size_of(joined), operation="joining text with '~'")
    return joined


@pass_context
def charged_comparison(context: Context, left: Any, operator: str, right: Any) -> Any:
    """`left <operator> right`, one comparison, charged for what comparing the two can cost."""
    budget = render_budget_of(context)
    if operator in {"in", "notin"}:
        right = charged_if_lazy(value=right, budget=budget)
    units = STEP_UNITS + comparison_units(operator=operator, left=left, right=right, limit=budget.remaining)
    budget.charge(units=units, operation="a comparison")
    return _COMPARISONS[operator](left, right)


@pass_context
def charged_operand(context: Context, value: Any) -> Any:
    """An operand of a chained comparison (`a < b < c`), charged for everything comparing it can cost."""
    budget = render_budget_of(context)
    budget.charge(units=STEP_UNITS + compare_weight(value, limit=budget.remaining), operation="a comparison")
    return value


@pass_context
def charged_slice(context: Context, value: Any) -> Any:
    """The result of `value[start:stop]`, which Jinja slices without its `getitem` hook."""
    budget = render_budget_of(context)
    budget.charge(units=STEP_UNITS + produced_size(value), operation="a slice")
    return value


INTERNAL_FILTERS: Final[dict[str, Callable[..., Any]]] = {
    ITERATE_FILTER: charged_iteration,
    CONCAT_FILTER: charged_concat,
    COMPARE_FILTER: charged_comparison,
    COMPARED_FILTER: charged_operand,
    SLICED_FILTER: charged_slice,
}
