"""What each operation a template can perform costs: the tables and the estimates of the render budget.

Most operations are charged by their inputs and their result alone (`jinja2_render_budget.py`), which
is enough when the result is at most a small multiple of the inputs. The operations here can produce
much more than they are given, from a width, a count, a separator or a nesting, so each has an
estimate of its result that the render checks before running it. The tables are exhaustive on
purpose: a method of a plain value, a filter or a test that is not in them is refused, so one that a
later Python or Jinja adds cannot be reached before someone has decided what it costs, and the tests
check the tables against everything the running versions offer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Mapping, Sized
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, cast

import jinja2.filters
import jinja2.tests
from markupsafe import Markup
from pydantic import BaseModel

from pipelex.tools.jinja2.jinja2_filters import escape_script_tag, tag, text_format
from pipelex.tools.jinja2.jinja2_render_budget import (
    ELEMENT_UNITS,
    ESCAPE_FACTOR,
    STEP_UNITS,
    compare_weight,
    escaped_length,
    is_data_object,
    json_string_length,
    text_size,
)
from pipelex.tools.jinja2.jinja2_with_images_filter import with_images

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


class CostInputs(NamedTuple):
    """What an estimate reads: the operation's inputs and what is left of the budget.

    `value` is the value the operation applies to: a filter's input, or the value a method is bound
    to. `escaping` says whether the operation escapes what it inserts. `limit` is what is left of the
    budget, past which a walk may stop counting.
    """

    value: Any
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    limit: int
    escaping: bool

    def arg(self, *, index: int, name: str, default: Any = None) -> Any:
        """An argument passed either at `index` or by `name`."""
        if len(self.args) > index:
            return self.args[index]
        return self.kwargs.get(name, default)


class CostEstimate(Protocol):
    """The units an operation's result will take, estimated from its inputs before it runs."""

    def __call__(self, *, inputs: CostInputs) -> int: ...


class OperationCost(NamedTuple):
    """How the budget treats one method or filter beyond charging its inputs and its result.

    - `estimate`: the size of the result, checked before the operation runs.
    - `work`: what the operation spends beyond reading its inputs, such as the comparisons of a sort,
      charged before it runs.
    - `materializes`: a lazy input (a filter's value, a method's first argument) is drawn into a list
      first, so that the estimates can count it.
    - `reads_value`: whether the operation reads the whole of its value (a filter's input, the value a
      method is bound to), which is then charged by its size, like its result. One that does not, such
      as `len` or `dict.get`, reads a fixed part of its value and returns a reference into it or a small
      value, so it is charged a step and its arguments only.
    """

    estimate: CostEstimate | None = None
    work: CostEstimate | None = None
    materializes: bool = False
    reads_value: bool = True


# Charged by its inputs and its result only.
LINEAR: Final = OperationCost()

# Charged a step and its arguments: it reads a fixed part of its value, whatever the value's size, and
# returns a reference into it or a small value.
CONSTANT: Final = OperationCost(reads_value=False)


def _length(*, value: Any) -> int:
    return len(value) if isinstance(value, Sized) else 0


def _digits_value(*, digits: str, limit: int) -> int:
    """The integer a run of digits in a format spec stands for, saturating past `limit`."""
    if len(digits) > len(str(limit)):
        return limit + 1
    return int(digits)


########################################################################################
# Format strings: `%`, the `format` filter and `str.format`
########################################################################################

_PERCENT_SPEC: Final = re.compile(
    r"%(?:\((?P<key>[^)]*)\))?[#0\- +]*(?P<width>\*|\d+)?(?:\.(?P<precision>\*|\d+))?[hlL]?(?P<conversion>.)", re.DOTALL
)


def percent_format_units(*, template: str, arguments: Any, limit: int, escaping: bool) -> int:
    """Estimate the result of `template % arguments`: its text, every width and precision, every argument."""
    factor = ESCAPE_FACTOR if escaping else 1
    positional: list[Any] = list(cast("tuple[Any, ...]", arguments)) if isinstance(arguments, tuple) else [arguments]
    mapping: Mapping[Any, Any] = cast("Mapping[Any, Any]", arguments) if isinstance(arguments, Mapping) else {}
    total = len(template)
    position = 0
    memo: dict[int, int] = {}
    for spec in _PERCENT_SPEC.finditer(template):
        if spec["conversion"] == "%":
            continue
        for part in (spec["width"], spec["precision"]):
            if part == "*":
                star = positional[position] if position < len(positional) else 0
                position += 1
                total += abs(star) if isinstance(star, int) else 0
            elif part:
                total += _digits_value(digits=part, limit=limit)
        if spec["key"] is not None:
            argument = mapping.get(spec["key"])
        else:
            argument = positional[position] if position < len(positional) else None
            position += 1
        total += factor * text_size(argument, limit=limit, memo=memo)
        if total > limit:
            return total
    return total


_SPEC_NUMBER: Final = re.compile(r"\d+")


def format_field_units(*, value: Any, spec: str, limit: int, escaping: bool, memo: dict[int, int]) -> int:
    """Estimate `format(value, spec)`, one replacement field of `str.format` with its spec already resolved.

    It counts the value's text, every number in the spec (a width or a precision), and a multiple of
    the spec's length, which a date's spec takes as a `strftime` format.
    """
    total = text_size(value, limit=limit, memo=memo)
    if spec:
        total += sum(_digits_value(digits=number, limit=limit) for number in _SPEC_NUMBER.findall(spec))
        total += 32 * len(spec)
    return total * (ESCAPE_FACTOR if escaping else 1)


########################################################################################
# Methods of plain values
########################################################################################

# The characters `str.split()` splits on, and those `str.splitlines()` ends a line at.
_ASCII_WHITESPACE: Final = " \t\n\r\x0b\x0c\x1c\x1d\x1e\x1f"
_WHITESPACE: Final = _ASCII_WHITESPACE + "\x85\xa0                　"
_ASCII_LINE_BREAKS: Final = "\n\r\x0b\x0c\x1c\x1d\x1e"
_LINE_BREAKS: Final = _ASCII_LINE_BREAKS + "\x85  "


def _count_any(*, text: str, characters: str) -> int:
    return sum(text.count(character) for character in characters)


def _padded_width(*, inputs: CostInputs) -> int:
    # `center`, `ljust`, `rjust` and `zfill` pad to their width.
    width = inputs.arg(index=0, name="width", default=0)
    return max(_length(value=inputs.value), width if isinstance(width, int) else 0)


def _expanded_tabs(*, inputs: CostInputs) -> int:
    tab_size = inputs.arg(index=0, name="tabsize", default=8)
    if not isinstance(inputs.value, str) or not isinstance(tab_size, int):
        return _length(value=inputs.value)
    return len(inputs.value) + inputs.value.count("\t") * max(tab_size, 0)


def _replacement_units(*, text: str, old: str, new: str, count: Any, escaping: bool) -> int:
    """Estimate `text.replace(old, new, count)`, where escaping can grow the text and the replacement sixfold."""
    if escaping:
        text_length = escaped_length(text)
        # The escaped text can hold `old` where the text does not, so every place it could fit counts.
        occurrences = text_length // len(old) + 1 if old else text_length + 1
        new_length = ESCAPE_FACTOR * len(new)
    else:
        text_length = len(text)
        # An empty `old` matches between every two characters.
        occurrences = text.count(old) if old else text_length + 1
        new_length = len(new)
    if isinstance(count, int) and count >= 0:
        occurrences = min(occurrences, count)
    return text_length + occurrences * new_length


def _replaced(*, inputs: CostInputs) -> int:
    old = inputs.arg(index=0, name="old")
    new = inputs.arg(index=1, name="new")
    if not isinstance(inputs.value, str) or not isinstance(old, str) or not isinstance(new, str):
        # `str.replace` takes strings only, and fails on anything else before it allocates.
        return _length(value=inputs.value)
    return _replacement_units(
        text=inputs.value,
        old=old,
        new=new,
        count=inputs.arg(index=2, name="count", default=-1),
        escaping=isinstance(inputs.value, Markup),
    )


def _value_text(*, value: Any, limit: int) -> str | None:
    """The text a filter converts `value` to, or None when that text would be longer than `limit`.

    A filter that converts its value (`str(value)`) and then works on the text is estimated on the
    text: converting first costs what the filter's own conversion would, and is refused when a
    container's text would already be too long.
    """
    if isinstance(value, str):
        return value
    if not is_data_object(value=value) and text_size(value, limit=limit) > limit:
        return None
    return str(value)


def _joined_units(*, items: Any, separator: str, limit: int, escaping: bool) -> int:
    if not isinstance(items, Collection):
        return len(separator)
    collection = cast("Collection[Any]", items)
    factor = ESCAPE_FACTOR if escaping else 1
    count = len(collection)
    # Joining draws the items into a sequence first, one reference and often one new object each.
    total = count * (len(separator) * factor + ELEMENT_UNITS)
    if isinstance(collection, str):
        return total + count * factor
    memo: dict[int, int] = {}
    for item in collection:
        total += factor * text_size(item, limit=limit, memo=memo)
        if total > limit:
            return total
    return total


def _joined(*, inputs: CostInputs) -> int:
    # `separator.join(items)`: the method is bound to the separator.
    separator = inputs.value if isinstance(inputs.value, str) else ""
    items = inputs.arg(index=0, name="iterable")
    return _joined_units(items=items, separator=separator, limit=inputs.limit, escaping=inputs.escaping or isinstance(inputs.value, Markup))


def _longest_replacement(*, table: Any, limit: int) -> int:
    if isinstance(table, str):
        return 1
    replacements: Iterable[Any]
    if isinstance(table, Mapping):
        replacements = cast("Mapping[Any, Any]", table).values()
    elif isinstance(table, (list, tuple)):
        replacements = cast("Sequence[Any]", table)
    else:
        return ELEMENT_UNITS
    longest = 1
    for replacement in replacements:
        longest = max(longest, text_size(replacement, limit=limit))
    return longest


def _translated(*, inputs: CostInputs) -> int:
    table = inputs.arg(index=0, name="table")
    return _length(value=inputs.value) * _longest_replacement(table=table, limit=inputs.limit)


def _split_pieces(*, inputs: CostInputs) -> int:
    # `split` and `rsplit`: every piece is a new string.
    if not isinstance(inputs.value, str):
        return _length(value=inputs.value)
    separator = inputs.arg(index=0, name="sep")
    max_split = inputs.arg(index=1, name="maxsplit", default=-1)
    if isinstance(separator, str) and separator:
        pieces = inputs.value.count(separator) + 1
    else:
        pieces = _count_any(text=inputs.value, characters=_ASCII_WHITESPACE if inputs.value.isascii() else _WHITESPACE) + 1
    if isinstance(max_split, int) and max_split >= 0:
        pieces = min(pieces, max_split + 1)
    return len(inputs.value) + ELEMENT_UNITS * pieces


def _split_lines(*, inputs: CostInputs) -> int:
    if not isinstance(inputs.value, str):
        return _length(value=inputs.value)
    pieces = _count_any(text=inputs.value, characters=_ASCII_LINE_BREAKS if inputs.value.isascii() else _LINE_BREAKS) + 1
    return len(inputs.value) + ELEMENT_UNITS * pieces


def _stripped_tags(*, inputs: CostInputs) -> int:
    # markupsafe's `striptags` rebuilds the whole string for every comment and every tag it removes.
    text = inputs.value if isinstance(inputs.value, str) else ""
    length = text_size(inputs.value, limit=inputs.limit)
    return length * (1 + text.count("<")) if text else length * (1 + length)


def _formatted_time(*, inputs: CostInputs) -> int:
    # A `strftime` directive of two characters prints at most a few dozen: `%c` is a whole date.
    time_format = inputs.arg(index=0, name="format", default="")
    return STEP_UNITS + 32 * _length(value=time_format)


def _set_operands(*, inputs: CostInputs) -> int:
    # A set operation builds a set from each operand first: a string becomes a set of its characters.
    return _length(value=inputs.value) * ELEMENT_UNITS + sum(ELEMENT_UNITS * _length(value=operand) for operand in inputs.args)


_STR_METHOD_COSTS: Final[dict[str, OperationCost]] = {
    "capitalize": LINEAR,
    "casefold": LINEAR,
    "center": OperationCost(estimate=_padded_width),
    "count": LINEAR,
    "endswith": CONSTANT,
    "expandtabs": OperationCost(estimate=_expanded_tabs),
    "find": LINEAR,
    "index": LINEAR,
    "isalnum": LINEAR,
    "isalpha": LINEAR,
    "isascii": CONSTANT,
    "isdecimal": LINEAR,
    "isdigit": LINEAR,
    "isidentifier": LINEAR,
    "islower": LINEAR,
    "isnumeric": LINEAR,
    "isprintable": LINEAR,
    "isspace": LINEAR,
    "istitle": LINEAR,
    "isupper": LINEAR,
    "join": OperationCost(estimate=_joined, materializes=True),
    "ljust": OperationCost(estimate=_padded_width),
    "lower": LINEAR,
    "lstrip": LINEAR,
    "partition": LINEAR,
    "removeprefix": LINEAR,
    "removesuffix": LINEAR,
    "replace": OperationCost(estimate=_replaced),
    "rfind": LINEAR,
    "rindex": LINEAR,
    "rjust": OperationCost(estimate=_padded_width),
    "rpartition": LINEAR,
    "rsplit": OperationCost(estimate=_split_pieces),
    "rstrip": LINEAR,
    "split": OperationCost(estimate=_split_pieces),
    "splitlines": OperationCost(estimate=_split_lines),
    "startswith": CONSTANT,
    "strip": LINEAR,
    "swapcase": LINEAR,
    "title": LINEAR,
    "translate": OperationCost(estimate=_translated),
    "upper": LINEAR,
    "zfill": OperationCost(estimate=_padded_width),
}

_REFUSED_STR_METHODS: Final[dict[str, str]] = {
    "encode": "it produces bytes, which a template has no use for, and some codecs cost the square of their input",
    "format": "a string formats through the sandbox's own formatter, never the raw method",
    "format_map": "a string formats through the sandbox's own formatter, never the raw method",
}

_INT_METHOD_COSTS: Final[dict[str, OperationCost]] = dict.fromkeys(("as_integer_ratio", "bit_count", "bit_length", "conjugate", "is_integer"), LINEAR)

_DATE_METHOD_COSTS: Final[dict[str, OperationCost]] = {
    **dict.fromkeys(("ctime", "isocalendar", "isoformat", "isoweekday", "replace", "timetuple", "toordinal", "weekday"), LINEAR),
    "strftime": OperationCost(estimate=_formatted_time),
}

_TIME_METHOD_COSTS: Final[dict[str, OperationCost]] = {
    **dict.fromkeys(("dst", "isoformat", "replace", "tzname", "utcoffset"), LINEAR),
    "strftime": OperationCost(estimate=_formatted_time),
}

_SET_OPERATION_COST: Final = OperationCost(estimate=_set_operands)

_FROZENSET_METHOD_COSTS: Final[dict[str, OperationCost]] = {
    "copy": LINEAR,
    **dict.fromkeys(("difference", "intersection", "isdisjoint", "issubset", "issuperset", "symmetric_difference", "union"), _SET_OPERATION_COST),
}

_MUTATES: Final = "it changes the value in place"

# The methods a template may call on an instance of each plain value type, with their cost. A method
# absent from its type's table is refused. Class methods and static methods are refused before this
# table is read, since they are bound to no instance.
PLAIN_VALUE_METHOD_COSTS: Final[dict[type, dict[str, OperationCost]]] = {
    str: _STR_METHOD_COSTS,
    Markup: {**_STR_METHOD_COSTS, "striptags": OperationCost(estimate=_stripped_tags), "unescape": LINEAR},
    int: _INT_METHOD_COSTS,
    bool: _INT_METHOD_COSTS,
    float: dict.fromkeys(("as_integer_ratio", "conjugate", "hex", "is_integer"), LINEAR),
    # Every `Decimal` operation is bounded by the context's precision.
    Decimal: dict.fromkeys(
        (
            "adjusted",
            "as_integer_ratio",
            "as_tuple",
            "canonical",
            "compare",
            "compare_signal",
            "compare_total",
            "compare_total_mag",
            "conjugate",
            "copy_abs",
            "copy_negate",
            "copy_sign",
            "exp",
            "fma",
            "is_canonical",
            "is_finite",
            "is_infinite",
            "is_nan",
            "is_normal",
            "is_qnan",
            "is_signed",
            "is_snan",
            "is_subnormal",
            "is_zero",
            "ln",
            "log10",
            "logb",
            "logical_and",
            "logical_invert",
            "logical_or",
            "logical_xor",
            "max",
            "max_mag",
            "min",
            "min_mag",
            "next_minus",
            "next_plus",
            "next_toward",
            "normalize",
            "number_class",
            "quantize",
            "radix",
            "remainder_near",
            "rotate",
            "same_quantum",
            "scaleb",
            "shift",
            "sqrt",
            "to_eng_string",
            "to_integral",
            "to_integral_exact",
            "to_integral_value",
        ),
        LINEAR,
    ),
    date: _DATE_METHOD_COSTS,
    datetime: {
        **_DATE_METHOD_COSTS,
        **dict.fromkeys(("astimezone", "date", "dst", "time", "timestamp", "timetz", "tzname", "utcoffset", "utctimetuple"), LINEAR),
    },
    time: _TIME_METHOD_COSTS,
    timedelta: {"total_seconds": LINEAR},
    list: dict.fromkeys(("copy", "count", "index"), LINEAR),
    tuple: dict.fromkeys(("count", "index"), LINEAR),
    dict: {"copy": LINEAR, **dict.fromkeys(("get", "items", "keys", "values"), CONSTANT)},
    set: _FROZENSET_METHOD_COSTS,
    frozenset: _FROZENSET_METHOD_COSTS,
}

# The public instance methods of each plain value type a template may not call, and why. With
# `PLAIN_VALUE_METHOD_COSTS` they classify every public instance method each type has, which the tests
# check, so a method a later Python adds is refused until someone decides what it costs.
REFUSED_PLAIN_VALUE_METHODS: Final[dict[type, dict[str, str]]] = {
    str: _REFUSED_STR_METHODS,
    Markup: _REFUSED_STR_METHODS,
    int: {"to_bytes": "it produces bytes of any length it is asked for"},
    bool: {"to_bytes": "it produces bytes of any length it is asked for"},
    list: dict.fromkeys(("append", "clear", "extend", "insert", "pop", "remove", "reverse", "sort"), _MUTATES),
    dict: dict.fromkeys(("clear", "pop", "popitem", "setdefault", "update"), _MUTATES),
    set: dict.fromkeys(
        ("add", "clear", "difference_update", "discard", "intersection_update", "pop", "remove", "symmetric_difference_update", "update"), _MUTATES
    ),
}


########################################################################################
# Comparisons
########################################################################################


def comparison_units(*, operator: str, left: Any, right: Any, limit: int) -> int:
    """Estimate what comparing `left` with `right` costs, for `in`, `not in` and the ordering operators.

    `x in text` scans the text. `x in mapping` hashes `x`. `x in sequence` compares `x` with every
    element, each comparison costing at most the lighter of the two. An ordering operator or an
    equality stops at the end of the lighter operand.
    """
    if operator in {"in", "notin"}:
        if isinstance(right, str):
            return len(right) + (len(left) if isinstance(left, str) else 0)
        if isinstance(right, (dict, set, frozenset)):
            return compare_weight(left, limit=limit)
        if isinstance(right, (list, tuple)):
            elements = cast("Sequence[Any]", right)
            left_weight = compare_weight(left, limit=limit)
            total = 8 * len(elements)
            weights: dict[int, int] = {}
            for element in elements:
                weight = weights.get(id(element))
                if weight is None:
                    weight = min(compare_weight(element, limit=left_weight), left_weight)
                    weights[id(element)] = weight
                total += weight
                if total > limit:
                    return total
            return total
        return STEP_UNITS
    left_weight = compare_weight(left, limit=limit)
    return min(left_weight, compare_weight(right, limit=left_weight))


########################################################################################
# Filters
########################################################################################


def _text(*, inputs: CostInputs) -> int:
    return text_size(inputs.value, limit=inputs.limit)


def escaped_text_size(value: Any, *, limit: int) -> int:
    """Estimate the length of `markupsafe.escape(value)`: exact for a string, which is already safe when it is markup."""
    if isinstance(value, Markup) or hasattr(value, "__html__"):
        return text_size(value, limit=limit)
    if isinstance(value, str):
        return escaped_length(value)
    return ESCAPE_FACTOR * text_size(value, limit=limit)


def _escaped_text(*, inputs: CostInputs) -> int:
    return escaped_text_size(inputs.value, limit=inputs.limit)


def _script_tag_escaped(*, inputs: CostInputs) -> int:
    # Every `<` becomes `\u003c`; any other value passes through unchanged.
    return len(inputs.value) + 5 * inputs.value.count("<") if isinstance(inputs.value, str) else 0


def _url_encoded_text(*, inputs: CostInputs) -> int:
    # A character outside ASCII is up to four UTF-8 bytes, each quoted as `%XX`.
    return 12 * text_size(inputs.value, limit=inputs.limit)


def _nesting_depth(*, value: Any, limit: int) -> int:
    """How deep containers nest under `value`, stopping past `limit`."""
    deepest = 0
    pending: list[tuple[Any, int]] = [(value, 1)]
    seen: set[int] = set()
    while pending:
        current, depth = pending.pop()
        identity = id(current)
        if identity in seen or not isinstance(current, (list, tuple, dict, set, frozenset)):
            continue
        seen.add(identity)
        deepest = max(deepest, depth)
        if deepest > limit:
            return deepest
        children = cast("dict[Any, Any]", current).values() if isinstance(current, dict) else cast("Collection[Any]", current)
        pending.extend((child, depth + 1) for child in children)
    return deepest


def _indented_serialisation(*, value: Any, indent: int, limit: int) -> int:
    # Every line of an indented dump is indented once per level it sits at, and a character outside
    # ASCII can take twelve.
    text = text_size(value, limit=limit)
    return 12 * text + indent * text * _nesting_depth(value=value, limit=limit)


def _tojson(*, inputs: CostInputs) -> int:
    if isinstance(inputs.value, str):
        return json_string_length(inputs.value)
    indent = inputs.arg(index=0, name="indent")
    return _indented_serialisation(value=inputs.value, indent=indent if isinstance(indent, int) and indent > 0 else 0, limit=inputs.limit)


def _pprint(*, inputs: CostInputs) -> int:
    return _indented_serialisation(value=inputs.value, indent=1, limit=inputs.limit)


def _materialized(*, inputs: CostInputs) -> int:
    # A new list with an element per item: a string becomes a list of its characters. A lazy input is
    # charged element by element as it is drawn.
    return ELEMENT_UNITS * _length(value=inputs.value)


def _reversed(*, inputs: CostInputs) -> int:
    return _length(value=inputs.value) if isinstance(inputs.value, str) else ELEMENT_UNITS * _length(value=inputs.value)


def _centered(*, inputs: CostInputs) -> int:
    width = inputs.arg(index=0, name="width", default=80)
    return max(text_size(inputs.value, limit=inputs.limit), width if isinstance(width, int) else 0)


def _indented(*, inputs: CostInputs) -> int:
    width = inputs.arg(index=0, name="width", default=4)
    indentation = len(width) if isinstance(width, str) else width if isinstance(width, int) else 0
    text = text_size(inputs.value, limit=inputs.limit)
    lines = inputs.value.count("\n") + 1 if isinstance(inputs.value, str) else text + 1
    return text + lines * max(indentation, 0)


def _wrapped(*, inputs: CostInputs) -> int:
    if not isinstance(inputs.value, str):
        return text_size(inputs.value, limit=inputs.limit)
    width = inputs.arg(index=0, name="width", default=79)
    break_long_words = inputs.arg(index=1, name="break_long_words", default=True)
    wrap_string = inputs.arg(index=2, name="wrapstring")
    width = max(width, 1) if isinstance(width, int) else 79
    separator_length = len(wrap_string) if isinstance(wrap_string, str) else 1
    lines = len(inputs.value) // width + inputs.value.count("\n") + 1
    total = len(inputs.value) + lines * separator_length
    if break_long_words and width < len(inputs.value):
        # textwrap cuts a word longer than the width one piece at a time, copying the rest each time.
        for word in re.finditer(rf"\S{{{width + 1},}}", inputs.value):
            word_length = word.end() - word.start()
            total += word_length * (word_length // width)
            if total > inputs.limit:
                return total
    return total


def _replaced_filter(*, inputs: CostInputs) -> int:
    # The filter converts its value, `old` and `new` to text before it replaces.
    text = _value_text(value=inputs.value, limit=inputs.limit)
    old = _value_text(value=inputs.arg(index=0, name="old"), limit=inputs.limit)
    new = _value_text(value=inputs.arg(index=1, name="new"), limit=inputs.limit)
    if text is None or old is None or new is None:
        return inputs.limit + 1
    count = inputs.arg(index=2, name="count")
    return len(text) + _replacement_units(text=text, old=old, new=new, count=count, escaping=inputs.escaping or isinstance(inputs.value, Markup))


def _joined_filter(*, inputs: CostInputs) -> int:
    separator = inputs.arg(index=0, name="d", default="")
    return _joined_units(items=inputs.value, separator=separator if isinstance(separator, str) else "", limit=inputs.limit, escaping=inputs.escaping)


def _formatted_filter(*, inputs: CostInputs) -> int:
    # The filter converts its value to text, which is the format string.
    template = _value_text(value=inputs.value, limit=inputs.limit)
    if template is None:
        return inputs.limit + 1
    return percent_format_units(template=template, arguments=inputs.kwargs or inputs.args, limit=inputs.limit, escaping=inputs.escaping)


def _batched(*, inputs: CostInputs) -> int:
    # The last batch is padded up to the batch size when a filler is given.
    line_count = inputs.arg(index=0, name="linecount", default=0)
    padding = line_count if isinstance(line_count, int) and inputs.arg(index=1, name="fill_with") is not None else 0
    return ELEMENT_UNITS * (2 * _length(value=inputs.value) + max(padding, 0))


def _sliced(*, inputs: CostInputs) -> int:
    # One list per slice, each padded by one filler when a filler is given.
    slices = inputs.arg(index=0, name="slices", default=0)
    return ELEMENT_UNITS * (_length(value=inputs.value) + 2 * max(slices if isinstance(slices, int) else 0, 0))


def _summed(*, inputs: CostInputs) -> int:
    start = inputs.arg(index=1, name="start", default=0)
    value = inputs.value
    length = _length(value=value)
    if isinstance(start, (int, float)) or not isinstance(value, Collection):
        return ELEMENT_UNITS * length
    items = cast("Collection[Any]", value)
    # Adding sequences copies the running total at every step: the square of their length.
    total = _length(value=start)
    for item in items:
        total += _length(value=item)
    return 8 * total * (length + 1)


def _url_linked(*, inputs: CostInputs) -> int:
    # Every word may become a link, which repeats the URL and carries the `target` and `rel` attributes.
    text = text_size(inputs.value, limit=inputs.limit)
    target = inputs.arg(index=2, name="target")
    rel = inputs.arg(index=3, name="rel")
    per_link = ELEMENT_UNITS + ESCAPE_FACTOR * (text_size(target, limit=inputs.limit) + text_size(rel, limit=inputs.limit))
    return 2 * ESCAPE_FACTOR * text + (text // 2 + 1) * per_link


def _counted_words(*, inputs: CostInputs) -> int:
    # The words are found as a list before they are counted.
    text = text_size(inputs.value, limit=inputs.limit)
    return text + ELEMENT_UNITS * (text // 2 + 1)


def _attribute_of(*, value: Any, attribute: Any) -> Any:
    """What `value.attribute` holds, read without running any code: a dict's item, a list's element or a
    pydantic model's field, down a dotted path. Anything else stands for itself, which weighs at least
    as much as any attribute of it.
    """
    current: object = value
    for part in str(attribute).split("."):
        key: object = int(part) if part.isdigit() else part
        found: object = _MISSING
        if isinstance(current, dict):
            found = cast("dict[object, object]", current).get(key, _MISSING)
        elif isinstance(current, (list, tuple)) and isinstance(key, int):
            sequence = cast("Sequence[object]", current)
            found = sequence[key] if key < len(sequence) else _MISSING
        elif isinstance(current, BaseModel):
            found = vars(current).get(part, _MISSING)
        if found is _MISSING:
            return cast("object", current)
        current = found
    return current


_MISSING: Final = object()


def _ordering_units(*, items: Any, attribute: Any, case_sensitive: Any, comparisons: Callable[..., int], limit: int) -> int:
    """What ordering `items` costs: `comparisons(n)` comparisons, each weighing the heaviest key.

    Keys that are not compared case-sensitively are lowered first, one copy each.
    """
    if not isinstance(items, Collection):
        return STEP_UNITS
    collection = cast("Collection[Any]", items)
    count = len(collection)
    heaviest = 0
    lowered = 0
    weights: dict[int, int] = {}
    for item in collection:
        key = item if attribute is None else _attribute_of(value=item, attribute=attribute)
        weight = weights.get(id(key))
        if weight is None:
            weight = compare_weight(key, limit=limit)
            weights[id(key)] = weight
        heaviest = max(heaviest, weight)
        if not case_sensitive and isinstance(key, str):
            lowered += len(key)
        if heaviest > limit or lowered > limit:
            return limit + 1
    return ELEMENT_UNITS * count + comparisons(count=count) * heaviest + lowered


def _sorting_comparisons(*, count: int) -> int:
    return count * math.ceil(math.log2(count)) if count > 1 else 0


def _scanning_comparisons(*, count: int) -> int:
    return count


def _grouping_comparisons(*, count: int) -> int:
    # A sort by the key, then one comparison per item to find where each group ends.
    return _sorting_comparisons(count=count) + count


def _sorting_work(*, inputs: CostInputs) -> int:
    # `sort(reverse, case_sensitive, attribute)`
    return _ordering_units(
        items=inputs.value,
        attribute=inputs.arg(index=2, name="attribute"),
        case_sensitive=inputs.arg(index=1, name="case_sensitive", default=False),
        comparisons=_sorting_comparisons,
        limit=inputs.limit,
    )


def _dict_sorting_work(*, inputs: CostInputs) -> int:
    # `dictsort(case_sensitive, by, reverse)`: the items are sorted by their key or by their value.
    value = inputs.value
    if not isinstance(value, Mapping):
        return STEP_UNITS
    mapping = cast("Mapping[Any, Any]", value)
    by = inputs.arg(index=1, name="by", default="key")
    return _ordering_units(
        items=list(mapping.values()) if by == "value" else list(mapping.keys()),
        attribute=None,
        case_sensitive=inputs.arg(index=0, name="case_sensitive", default=False),
        comparisons=_sorting_comparisons,
        limit=inputs.limit,
    )


def _grouping_work(*, inputs: CostInputs) -> int:
    # `groupby(attribute, default, case_sensitive)`: a sort by the attribute, then one comparison per item.
    return _ordering_units(
        items=inputs.value,
        attribute=inputs.arg(index=0, name="attribute"),
        case_sensitive=inputs.arg(index=2, name="case_sensitive", default=False),
        comparisons=_grouping_comparisons,
        limit=inputs.limit,
    )


def _extremum_work(*, inputs: CostInputs) -> int:
    # `min(case_sensitive, attribute)` and `max`: one comparison per item.
    return _ordering_units(
        items=inputs.value,
        attribute=inputs.arg(index=1, name="attribute"),
        case_sensitive=inputs.arg(index=0, name="case_sensitive", default=False),
        comparisons=_scanning_comparisons,
        limit=inputs.limit,
    )


def _rendered_with_images(*, inputs: CostInputs) -> int:
    # A list renders each of its items and joins them, so an item repeated a thousand times renders a
    # thousand times; a single value renders its own data once, and is charged once rendered.
    value = inputs.value
    if not isinstance(value, (list, tuple)):
        return 0
    memo: dict[int, int] = {}
    total = 0
    for item in cast("Sequence[Any]", value):
        total += ELEMENT_UNITS + text_size(item, limit=inputs.limit, memo=memo)
        if total > inputs.limit:
            return total
    return total


_FILTERS: Final = cast("dict[str, Callable[..., Any]]", jinja2.filters.FILTERS)

# The cost of every filter the environment can register, keyed by the filter function itself: Pipelex
# registers its own `format` under the name Jinja's has.
FILTER_COSTS: Final[dict[Callable[..., Any], OperationCost]] = {
    _FILTERS["abs"]: LINEAR,
    _FILTERS["attr"]: CONSTANT,
    _FILTERS["batch"]: OperationCost(estimate=_batched),
    _FILTERS["capitalize"]: LINEAR,
    _FILTERS["center"]: OperationCost(estimate=_centered),
    # `count` is `length`, and `len` reads no element.
    _FILTERS["count"]: CONSTANT,
    _FILTERS["default"]: CONSTANT,
    _FILTERS["dictsort"]: OperationCost(estimate=_materialized, work=_dict_sorting_work),
    _FILTERS["escape"]: OperationCost(estimate=_escaped_text),
    _FILTERS["filesizeformat"]: LINEAR,
    _FILTERS["first"]: CONSTANT,
    _FILTERS["float"]: LINEAR,
    _FILTERS["forceescape"]: OperationCost(estimate=_escaped_text),
    _FILTERS["format"]: OperationCost(estimate=_formatted_filter),
    _FILTERS["groupby"]: OperationCost(estimate=_materialized, work=_grouping_work, materializes=True),
    _FILTERS["indent"]: OperationCost(estimate=_indented),
    _FILTERS["int"]: LINEAR,
    _FILTERS["items"]: LINEAR,
    _FILTERS["join"]: OperationCost(estimate=_joined_filter, materializes=True),
    _FILTERS["last"]: CONSTANT,
    _FILTERS["list"]: OperationCost(estimate=_materialized),
    _FILTERS["lower"]: LINEAR,
    _FILTERS["map"]: LINEAR,
    _FILTERS["max"]: OperationCost(work=_extremum_work, materializes=True),
    _FILTERS["min"]: OperationCost(work=_extremum_work, materializes=True),
    _FILTERS["pprint"]: OperationCost(estimate=_pprint),
    _FILTERS["random"]: CONSTANT,
    _FILTERS["reject"]: LINEAR,
    _FILTERS["rejectattr"]: LINEAR,
    _FILTERS["replace"]: OperationCost(estimate=_replaced_filter),
    _FILTERS["reverse"]: OperationCost(estimate=_reversed),
    _FILTERS["round"]: LINEAR,
    _FILTERS["safe"]: OperationCost(estimate=_text),
    _FILTERS["select"]: LINEAR,
    _FILTERS["selectattr"]: LINEAR,
    _FILTERS["slice"]: OperationCost(estimate=_sliced),
    _FILTERS["sort"]: OperationCost(estimate=_materialized, work=_sorting_work, materializes=True),
    _FILTERS["string"]: OperationCost(estimate=_text),
    _FILTERS["striptags"]: OperationCost(estimate=_stripped_tags),
    _FILTERS["sum"]: OperationCost(estimate=_summed, materializes=True),
    _FILTERS["title"]: LINEAR,
    _FILTERS["tojson"]: OperationCost(estimate=_tojson),
    _FILTERS["trim"]: LINEAR,
    _FILTERS["truncate"]: LINEAR,
    _FILTERS["unique"]: OperationCost(estimate=_materialized),
    _FILTERS["upper"]: LINEAR,
    _FILTERS["urlencode"]: OperationCost(estimate=_url_encoded_text),
    _FILTERS["urlize"]: OperationCost(estimate=_url_linked),
    _FILTERS["wordcount"]: OperationCost(estimate=_counted_words),
    _FILTERS["wordwrap"]: OperationCost(estimate=_wrapped),
    _FILTERS["xmlattr"]: OperationCost(estimate=_escaped_text),
    text_format: LINEAR,
    tag: LINEAR,
    escape_script_tag: OperationCost(estimate=_script_tag_escaped),
    with_images: OperationCost(estimate=_rendered_with_images),
}

# The filters whose result is template arithmetic, capped like an operator's.
INTEGER_FILTERS: Final[frozenset[Callable[..., Any]]] = frozenset({_FILTERS["int"], _FILTERS["sum"]})


########################################################################################
# Tests
########################################################################################


class TestCost(NamedTuple):
    """How the budget treats a test: a comparison is charged like the operator it spells."""

    comparison: str | None = None
    scans_text: bool = False


_TESTS: Final = cast("dict[str, Callable[..., Any]]", jinja2.tests.TESTS)
_EQUALITY: Final = TestCost(comparison="eq")

TEST_COSTS: Final[dict[Callable[..., Any], TestCost]] = {
    **{
        _TESTS[name]: TestCost()
        for name in (
            "boolean",
            "callable",
            "defined",
            "divisibleby",
            "escaped",
            "even",
            "false",
            "filter",
            "float",
            "integer",
            "iterable",
            "mapping",
            "none",
            "number",
            "odd",
            "sameas",
            "sequence",
            "string",
            "test",
            "true",
            "undefined",
        )
    },
    **{_TESTS[name]: _EQUALITY for name in ("==", "!=", "<", "<=", ">", ">=")},
    _TESTS["in"]: TestCost(comparison="in"),
    _TESTS["lower"]: TestCost(scans_text=True),
    _TESTS["upper"]: TestCost(scans_text=True),
}


########################################################################################
# Globals
########################################################################################


def lipsum_units(*, inputs: CostInputs) -> int:
    """Estimate `lipsum(n, html, min, max)`: `n` paragraphs of up to `max` words of a dozen characters."""
    paragraphs = inputs.arg(index=0, name="n", default=5)
    fewest = inputs.arg(index=2, name="min", default=20)
    most = inputs.arg(index=3, name="max", default=100)
    words = max(fewest if isinstance(fewest, int) else 0, most if isinstance(most, int) else 0)
    return max(paragraphs if isinstance(paragraphs, int) else 0, 0) * (16 * words + ELEMENT_UNITS)
