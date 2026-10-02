"""The budget a template render spends from, and the sizes it is charged in.

A sandbox limits what a template can reach, not what it can spend, and a template renders inside the
shared runner and worker processes, on their event loop, where no timeout can interrupt it: a render
never yields. So every render spends from one budget of **work units**, where a unit stands for roughly
one byte read or allocated, and the render stops with `RenderBudgetExceededError` the moment an
operation would overdraw it. One number bounds the CPU a render takes, since every step of work is
charged, the memory it takes, since every allocation is charged, and its output, which is allocated
like anything else.

An operation is charged for its inputs before it runs, for its result after it runs, and, when its
result can be much larger than its inputs, for an estimate of that result before it runs:

- Charging the inputs first means an operation never starts on inputs larger than what is left, so an
  operation whose result is a small multiple of its inputs overshoots by at most that multiple of what
  was left.
- Charging the result afterwards makes repeated steps add up: a string doubled in a loop is charged at
  every doubling.
- Estimating the result first stops a single step from allocating a gigabyte: `'x' * 10**9` is refused
  before it runs.

Where the charges are made, and the estimates, are in `jinja2_render_charging.py` and
`jinja2_render_costs.py`; the environment that applies them is `PipelexTemplateEnvironment`.

A render's budget is also its **active** budget while the render runs (`active_render_budget`), for the
work a template sets off in code that no hook reaches and that costs far more than the bytes it
produces: converting a Markdown value to HTML, which markupsafe does through `__html__` wherever a
value is escaped, is charged where it happens (`markdown_parser.py`).
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator, Sized
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar, cast

from jinja2.exceptions import TemplateError
from jinja2.runtime import LoopContext, Undefined
from jinja2.utils import Namespace
from markupsafe import Markup
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Callable, Collection, Generator, Iterable

# A render's budget unless the environment is given another: a few hundred megabytes allocated in
# total at the very worst, and well under a second of CPU.
DEFAULT_RENDER_BUDGET_UNITS: Final[int] = 128 * 1024 * 1024

# The flat cost of one step: a call, an operator, a filter, a test, a comparison, a printed value. It
# is what an empty loop body or a macro that renders nothing still costs, and it is set so that a step
# costs about as many units as the nanoseconds it takes, like the bytes the other charges count.
STEP_UNITS: Final[int] = 256

# The flat cost of a call a template makes, a method's or a macro's, which takes several steps' time.
CALL_UNITS: Final[int] = 1024

# The cost of one element a template draws from an iterable or finds in a container it produced: a
# reference, plus the small object behind it when the element is new, and the time a loop takes to
# draw it.
ELEMENT_UNITS: Final[int] = 64

# The cost of converting one character of Markdown to HTML, or one cell of a table, which a render pays
# wherever a template sets the conversion off (`markdown_parser.py`): the `markdown` filter, or printing,
# joining or formatting a Markdown value in an HTML template. markdown-it-py takes up to about ten
# microseconds and five hundred bytes of tokens a character, and five microseconds and a kilobyte a table
# cell, so the charge stops a render at about 65,000 characters of Markdown under the default budget,
# which the slowest text measured converts in about six tenths of a second.
MARKDOWN_UNITS_PER_CHARACTER: Final[int] = 2048

# The factor by which escaping can grow a text: `'` becomes `&#39;` in HTML and `'` in JSON.
ESCAPE_FACTOR: Final[int] = 6

# The widest integer template arithmetic may produce. Multiplying huge integers costs more than their
# size suggests, and integers past 2**61 can be chosen to share a hash, which makes a set or a dict of
# them quadratic to build; 64 bits allows neither.
MAX_INT_BITS: Final[int] = 64

# The types whose storage `sys.getsizeof` measures in constant time; every other object counts a step.
_SIZED_TYPES: Final[tuple[type, ...]] = (str, bytes, bytearray, int, float, list, tuple, dict, set, frozenset)

# The types whose own storage is a few bytes whatever their length: a range, and the key, value and item
# views of a dict. A filter iterating one does as much work as on the list it stands for, so it is
# sized like that list, a pointer per element.
_EMPTY_DICT: Final[dict[object, object]] = {}
_VIEW_TYPES: Final[tuple[type, ...]] = (range, type(_EMPTY_DICT.keys()), type(_EMPTY_DICT.values()), type(_EMPTY_DICT.items()))
_POINTER_UNITS: Final = 8

# The exact types that are never lazy and never awaitable, checked first on the hot paths.
EAGER_TYPES: Final[frozenset[type]] = frozenset({str, Markup, int, float, bool, type(None), list, tuple, dict, set, frozenset, range})

# The key, value and item views of a dict, which print every element they show.
_DICT_VIEW_TYPES: Final[tuple[type, ...]] = (type(_EMPTY_DICT.keys()), type(_EMPTY_DICT.values()), type(_EMPTY_DICT.items()))

# The containers a template can build, fill or read a view of, whose elements a walk visits.
_CONTAINER_TYPES: Final[tuple[type, ...]] = (list, tuple, dict, set, frozenset, Namespace, *_DICT_VIEW_TYPES)

_ElementT = TypeVar("_ElementT")


class RenderBudgetExceededError(TemplateError):
    """A template render tried to spend more than its budget allows.

    Raised from the hook that caught the overdraft, and turned into `Jinja2TemplateBudgetError` by the
    render functions. It derives from nothing a filter or Jinja's runtime catches on the way.
    """


class RenderBudget:
    """What is left of one render's budget. Every render gets its own, created with its context."""

    __slots__ = ("remaining", "total")

    def __init__(self, *, total: int) -> None:
        self.total = total
        self.remaining = total

    def charge(self, *, units: int, operation: str | Callable[[], str]) -> None:
        """Spend `units`, or refuse the operation if they are more than what is left."""
        if units > self.remaining:
            self._refuse(units=units, operation=operation)
        self.remaining -= units

    def afford(self, *, units: int, operation: str | Callable[[], str]) -> None:
        """Refuse the operation if its estimate is more than what is left, without spending anything."""
        if units > self.remaining:
            self._refuse(units=units, operation=operation)

    def _refuse(self, *, units: int, operation: str | Callable[[], str]) -> None:
        described = operation() if callable(operation) else operation
        msg = (
            f"Rendering the template would spend more than its budget of {self.total:,} work units: "
            f"{described} needs about {units:,}, and {self.remaining:,} are left."
        )
        raise RenderBudgetExceededError(msg)


_ACTIVE_RENDER_BUDGET: Final[ContextVar[RenderBudget | None]] = ContextVar("pipelex_active_render_budget", default=None)


def active_render_budget() -> RenderBudget | None:
    """The budget of the template render running now, or None outside any render."""
    return _ACTIVE_RENDER_BUDGET.get()


@contextmanager
def spending_from(*, budget: RenderBudget) -> Generator[None, None, None]:
    """Make `budget` the active one for the duration of a render, and the previous one again after it."""
    token = _ACTIVE_RENDER_BUDGET.set(budget)
    try:
        yield
    finally:
        _ACTIVE_RENDER_BUDGET.reset(token)


def refuse_int_result(*, bits: int, operation: str) -> None:
    """Refuse an integer result wider than `MAX_INT_BITS`."""
    if bits > MAX_INT_BITS:
        msg = (
            f"Rendering the template would produce an integer of about {bits:,} bits by {operation}; "
            f"template arithmetic stops at {MAX_INT_BITS} bits."
        )
        raise RenderBudgetExceededError(msg)


def check_int_result(*, value: object, operation: str) -> None:
    """Refuse `value` if it is an integer wider than `MAX_INT_BITS`."""
    if isinstance(value, int):
        refuse_int_result(bits=value.bit_length(), operation=operation)


def size_of(value: Any) -> int:
    """The bytes `value`'s own storage takes, taken in constant time; a flat cost for any other object."""
    if isinstance(value, _SIZED_TYPES):
        return sys.getsizeof(cast("object", value))
    if isinstance(value, _VIEW_TYPES):
        return _view_size(value=cast("Sized", value))
    return ELEMENT_UNITS


def _view_size(*, value: Sized) -> int:
    try:
        length = len(value)
    except OverflowError:
        # A range longer than a machine integer can count.
        return sys.maxsize
    return sys.getsizeof(value) + _POINTER_UNITS * length


def produced_size(value: Any) -> int:
    """What producing `value` cost: its own storage, plus a flat cost per element of a container."""
    size = size_of(value)
    if isinstance(value, (list, tuple, dict, set, frozenset)):
        size += ELEMENT_UNITS * len(cast("Sized", value))
    return size


def is_lazy(value: object) -> bool:
    """Whether `value` produces its elements as it is iterated: an iterator, a generator, an async one.

    An undefined value and a loop's `loop` are neither, though Jinja gives the first an `__aiter__` and
    the second a `__next__`: wrapped, they would stop behaving as what they are.
    """
    if type(value) in EAGER_TYPES or isinstance(value, (Undefined, LoopContext)):
        return False
    return hasattr(value, "__aiter__") or (hasattr(value, "__next__") and hasattr(value, "__iter__"))


class ChargedIterator(Generic[_ElementT]):
    """An iterable that charges the render's budget for every element drawn from it.

    An element that already existed costs `ELEMENT_UNITS`; an element a lazy iterable produced on the
    way also costs its size.
    """

    __slots__ = ("_budget", "_charges_elements", "_iterator")

    def __init__(self, *, iterable: Iterable[_ElementT], budget: RenderBudget) -> None:
        self._budget = budget
        self._charges_elements = is_lazy(iterable)
        self._iterator = iter(iterable)

    def __iter__(self) -> ChargedIterator[_ElementT]:
        return self

    def __next__(self) -> _ElementT:
        element = next(self._iterator)
        budget = self._budget
        units = ELEMENT_UNITS + produced_size(element) if self._charges_elements else ELEMENT_UNITS
        if units > budget.remaining:
            budget.charge(units=units, operation="drawing the next element of an iteration")
        budget.remaining -= units
        return element


class ChargedSizedIterator(ChargedIterator[_ElementT]):
    """A `ChargedIterator` over a sized iterable, whose length stays readable, so `loop.length` on a
    list does not have to exhaust it.
    """

    __slots__ = ("_length",)

    def __init__(self, *, iterable: Iterable[_ElementT], budget: RenderBudget) -> None:
        super().__init__(iterable=iterable, budget=budget)
        self._length = len(cast("Sized", iterable))

    def __len__(self) -> int:
        return self._length


class ChargedAsyncIterator(Generic[_ElementT]):
    """The async counterpart of `ChargedIterator`, for the async iterables Jinja's async filters return."""

    __slots__ = ("_budget", "_iterator")

    def __init__(self, *, iterable: AsyncIterable[_ElementT], budget: RenderBudget) -> None:
        self._budget = budget
        self._iterator: AsyncIterator[_ElementT] = aiter(iterable)

    def __aiter__(self) -> ChargedAsyncIterator[_ElementT]:
        return self

    async def __anext__(self) -> _ElementT:
        element = await anext(self._iterator)
        self._budget.charge(units=ELEMENT_UNITS + produced_size(element), operation="drawing the next element of an iteration")
        return element


def charged_iterable(*, iterable: Any, budget: RenderBudget) -> ChargedIterator[Any] | ChargedAsyncIterator[Any] | Undefined:
    """Wrap `iterable` so that drawing from it is charged, keeping it async when it is async.

    An undefined value is handed back as it is: it iterates as empty, or fails as Jinja would have it fail.
    """
    if isinstance(iterable, Undefined):
        return iterable
    if hasattr(iterable, "__aiter__"):
        return ChargedAsyncIterator(iterable=iterable, budget=budget)
    if isinstance(iterable, Sized):
        return ChargedSizedIterator(iterable=cast("Iterable[Any]", iterable), budget=budget)
    return ChargedIterator(iterable=iterable, budget=budget)


_CHARGED_TYPES: Final = frozenset({ChargedIterator, ChargedSizedIterator, ChargedAsyncIterator})


def charged_if_lazy(*, value: Any, budget: RenderBudget) -> Any:
    """Wrap `value` in a charged iterable when it is lazy; hand anything else back as it is."""
    if type(value) in EAGER_TYPES or type(value) in _CHARGED_TYPES or not is_lazy(value):
        return value
    return charged_iterable(iterable=value, budget=budget)


def _children(*, value: Any) -> Iterator[object] | None:
    """The elements a walk visits under `value`, or None when `value` is a leaf."""
    if isinstance(value, dict):
        return _dict_children(value=cast("dict[Any, Any]", value))
    if isinstance(value, (list, tuple, set, frozenset)):
        return iter(cast("Collection[Any]", value))
    if isinstance(value, _DICT_VIEW_TYPES):
        # An item view's pairs are temporaries a walk could not remember by identity: walk its dict.
        if isinstance(value, type(_EMPTY_DICT.items())):
            return _dict_children(value=cast("dict[Any, Any]", cast("Any", value).mapping))
        return iter(cast("Collection[Any]", value))
    if isinstance(value, Namespace):
        # A namespace prints as `<Namespace {...}>`, the dict of what the template stored in it.
        # A namespace answers any name with what was stored under it, except its own store.
        attrs: dict[str, Any] = getattr(value, "_Namespace__attrs", {})
        return iter((attrs,))
    return None


def _dict_children(*, value: dict[Any, Any]) -> Iterator[object]:
    # Keys and values separately, never `items()`, whose tuples are temporaries a walk could not
    # remember by identity.
    yield from value.keys()
    yield from value.values()


def _walk(
    *,
    root: object,
    leaf_units: Callable[[object], int],
    container_units: Callable[[object], int],
    limit: int,
    children: Callable[..., Iterator[object] | None] = _children,
) -> int:
    """Add up a value's units over the containers under it, without recursing and stopping past `limit`.

    Each container is totalled once and its total counted at every reference to it, so a list holding
    the same big string a hundred thousand times costs a hundred thousand times the string, while the
    walk visits the string once. A container reached again while it is being totalled is a cycle, and
    counts a step.
    """
    totals: dict[int, int] = {}
    in_progress: set[int] = set()
    root_children = children(value=root)
    if root_children is None:
        return leaf_units(root)
    # Each frame is the container, the elements left to visit, and the running total.
    frames: list[list[Any]] = [[root, root_children, container_units(root)]]
    in_progress.add(id(root))
    while frames:
        frame = frames[-1]
        child = next(frame[1], _END)
        if child is _END:
            frames.pop()
            finished: object = frame[0]
            finished_total: int = frame[2]
            in_progress.discard(id(finished))
            totals[id(finished)] = finished_total
            if not frames:
                return finished_total
            parent_total: int = frames[-1][2] + finished_total
            frames[-1][2] = parent_total
            if parent_total > limit:
                return parent_total
            continue
        child_id = id(child)
        known = totals.get(child_id)
        if known is not None:
            frame[2] += known
        elif child_id in in_progress:
            frame[2] += ELEMENT_UNITS
        else:
            grandchildren = children(value=child)
            if grandchildren is None:
                units = leaf_units(child)
                totals[child_id] = units
                frame[2] += units
            else:
                in_progress.add(child_id)
                frames.append([child, grandchildren, container_units(child)])
                continue
        running_total: int = frame[2]
        if running_total > limit:
            return running_total
    return 0


_END: Final = object()


def _int_text_size(*, value: int) -> int:
    # A decimal digit carries about 3.32 bits.
    return value.bit_length() * 10 // 33 + 2


def _repr_leaf_size(value: Any) -> int:
    """The length of `repr(value)` for an element inside a printed container."""
    if isinstance(value, Markup):
        return len(value) + 10
    if isinstance(value, str):
        return len(value) + 2
    if isinstance(value, bool) or value is None:
        return 5
    if isinstance(value, int):
        return _int_text_size(value=value)
    if isinstance(value, float):
        return 24
    if isinstance(value, Undefined):
        return 16
    return len(repr(value))


def _repr_container_size(value: Any) -> int:
    """What a container's printed form adds to its elements: brackets, separators, a class name."""
    kind = type(cast("object", value))
    if isinstance(value, Namespace):
        return 13
    if isinstance(value, _DICT_VIEW_TYPES):
        # `dict_items([('k', 'v')])`: the view's name and brackets, and a pair's parentheses and separators.
        return 16 + 6 * len(cast("Sized", value))
    if not isinstance(value, (list, tuple, dict, set, frozenset)):
        return 0
    length = len(cast("Sized", value))
    if isinstance(value, dict):
        return 2 + 4 * length
    size = 11 + 2 * length
    if kind not in {list, tuple, set, frozenset}:
        # A named tuple prints its class and field names.
        size += len(kind.__name__) + 16 * length
    return size


def escaped_length(text: str) -> int:
    """The exact length of `markupsafe.escape(text)`: `&`, `"` and `'` grow by four, `<` and `>` by three."""
    return len(text) + 4 * (text.count("&") + text.count('"') + text.count("'")) + 3 * (text.count("<") + text.count(">"))


_CONTROL_CHARACTERS: Final[dict[int, None]] = dict.fromkeys(range(32))


def json_string_length(text: str) -> int:
    r"""At most the length of `text` dumped as a JSON string by Jinja's `tojson`.

    A control character is escaped as `\u00XX` and `<`, `>`, `&` and `'` as `\u003c` and the like; a
    quote and a backslash take one more backslash; a character outside ASCII takes one or two `\uXXXX`.
    """
    non_ascii = 0 if text.isascii() else len(text) - len(text.encode("ascii", "ignore"))
    controls = len(text) - len(text.translate(_CONTROL_CHARACTERS))
    html_sensitive = text.count("<") + text.count(">") + text.count("&") + text.count("'")
    return 2 + len(text) + text.count('"') + text.count("\\") + 5 * (controls + html_sensitive) + 11 * non_ascii


def is_data_object(*, value: object) -> bool:
    """Whether `value` is an object of the run's data: neither text, a number, nothing, an undefined value
    nor a container a template can build.
    """
    return not isinstance(value, (str, int, float, type(None), Undefined, *_CONTAINER_TYPES))


def _data_text_size(*, value: object, memo: dict[int, int] | None) -> int:
    # An object of the run's data is converted to count its text: that is the conversion the
    # operation being estimated makes, and the object's text is the run's, not the template's. The
    # memo converts an object repeated a thousand times once.
    if memo is None:
        return len(str(value))
    known = memo.get(id(value))
    if known is None:
        known = len(str(value))
        memo[id(value)] = known
    return known


def text_size(value: Any, *, limit: int, memo: dict[int, int] | None = None) -> int:
    """Estimate the length of `str(value)`, stopping once past `limit`.

    A string's length is exact. A container prints the `repr` of its elements, so it is walked (see
    `_walk`), and an element that is neither a string, a number nor a container counts the length of
    its own `repr`, taken once. An object of the run's data at the top level is converted, once per
    `memo` (see `_data_text_size`).
    """
    if isinstance(value, str):
        return len(value)
    if isinstance(value, Undefined):
        return 0
    if isinstance(value, bool) or value is None:
        return 5
    if isinstance(value, int):
        return _int_text_size(value=value)
    if isinstance(value, float):
        return 24
    if not isinstance(value, _CONTAINER_TYPES):
        return _data_text_size(value=cast("object", value), memo=memo)
    return _walk(root=cast("object", value), leaf_units=_repr_leaf_size, container_units=_repr_container_size, limit=limit)


def _compare_children(*, value: object) -> Iterator[object] | None:
    # Two pydantic models are equal when their fields are, so a model is walked like a dict of its fields.
    if isinstance(value, BaseModel):
        return iter(vars(value).values())
    return _children(value=value)


def _compare_leaf_units(value: Any) -> int:
    if isinstance(value, (str, bytes, bytearray)):
        return len(cast("Sized", value))
    # A number, nothing, an undefined value, or an object whose equality is its own: a step. An
    # object's `repr` is never taken, since the comparison would not take it.
    return 8


def _compare_container_units(value: Any) -> int:
    if isinstance(value, Namespace):
        return 8
    if isinstance(value, (list, tuple, dict, set, frozenset)):
        return 8 * len(cast("Sized", value))
    if isinstance(value, BaseModel):
        return 8 * len(vars(value))
    return 0


def compare_weight(value: Any, *, limit: int) -> int:
    """Estimate what comparing `value` with another value can cost, stopping once past `limit`.

    A string costs its length, since two strings of the same length are compared character by
    character; a container costs a reference per element plus the weight of each element, counted at
    every reference, since comparing two containers compares their elements in turn. A pydantic model
    is a container of its fields.
    """
    return _walk(root=value, leaf_units=_compare_leaf_units, container_units=_compare_container_units, limit=limit, children=_compare_children)
