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

import re
import string
from collections.abc import Collection, Mapping, Sized
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Protocol, cast

import jinja2.filters
import jinja2.tests
from markupsafe import Markup

from pipelex.tools.jinja2.jinja2_filters import escape_script_tag, tag, text_format
from pipelex.tools.jinja2.jinja2_render_budget import (
    ELEMENT_UNITS,
    ESCAPE_FACTOR,
    STEP_UNITS,
    compare_weight,
    escaped_length,
    json_string_length,
    text_size,
)
from pipelex.tools.jinja2.jinja2_with_images_filter import with_images

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


@dataclass(frozen=True)
class CostInputs:
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


@dataclass(frozen=True)
class OperationCost:
    """How the budget treats one method, filter or test beyond charging its inputs and its result.

    - `estimate`: the size of the result, checked before the operation runs.
    - `materializes`: a lazy input (a filter's value, a method's first argument) is drawn into a list
      first, so that the estimate can count it.
    """

    estimate: CostEstimate | None = None
    materializes: bool = False


# Charged by its inputs and its result only.
LINEAR: Final = OperationCost()


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
        total += factor * text_size(argument, limit=limit)
        if total > limit:
            return total
    return total


_SPEC_NUMBER: Final = re.compile(r"\d+")


def str_format_units(*, template: str, args: tuple[Any, ...], kwargs: dict[str, Any], limit: int, escaping: bool) -> int:
    """Estimate the result of `template.format(*args, **kwargs)`.

    Every replacement field counts the text of the argument it names, every number in its spec (a
    width or a precision), and, when the spec takes a width from an argument (`{:{w}}`), the largest
    integer argument; a date's spec is a `strftime` format, which counts a multiple of its length.
    """
    factor = ESCAPE_FACTOR if escaping else 1
    integers = [abs(argument) for argument in (*args, *kwargs.values()) if isinstance(argument, int)]
    largest_integer = max(integers, default=0)
    total = 0
    auto_index = 0
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError:
        # A malformed format string fails when it is formatted, before it allocates anything.
        return len(template)
    for literal, field_name, spec, _conversion in fields:
        total += len(literal)
        if field_name is None:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        argument: Any = None
        if not root:
            argument = args[auto_index] if auto_index < len(args) else None
            auto_index += 1
        elif root.isdigit():
            index = int(root) if len(root) < 6 else len(args)
            argument = args[index] if index < len(args) else None
        else:
            argument = kwargs.get(root)
        total += factor * text_size(argument, limit=limit)
        if spec:
            total += sum(_digits_value(digits=number, limit=limit) for number in _SPEC_NUMBER.findall(spec))
            total += largest_integer * spec.count("{")
            total += 32 * len(spec)
        if total > limit:
            return total
    return total


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


def _replacement_units(*, text: str, old: Any, new: Any, count: Any, escaping: bool) -> int:
    if not isinstance(old, str) or not isinstance(new, str):
        return len(text)
    # An empty `old` matches between every two characters.
    occurrences = text.count(old) if old else len(text) + 1
    if isinstance(count, int) and count >= 0:
        occurrences = min(occurrences, count)
    return len(text) + occurrences * len(new) * (ESCAPE_FACTOR if escaping else 1)


def _replaced(*, inputs: CostInputs) -> int:
    if not isinstance(inputs.value, str):
        return _length(value=inputs.value)
    return _replacement_units(
        text=inputs.value,
        old=inputs.arg(index=0, name="old"),
        new=inputs.arg(index=1, name="new"),
        count=inputs.arg(index=2, name="count", default=-1),
        escaping=inputs.escaping or isinstance(inputs.value, Markup),
    )


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
    for item in collection:
        total += factor * text_size(item, limit=limit)
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
    "endswith": LINEAR,
    "expandtabs": OperationCost(estimate=_expanded_tabs),
    "find": LINEAR,
    "index": LINEAR,
    "isalnum": LINEAR,
    "isalpha": LINEAR,
    "isascii": LINEAR,
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
    "startswith": LINEAR,
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
    dict: dict.fromkeys(("copy", "get", "items", "keys", "values"), LINEAR),
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
    text = inputs.value if isinstance(inputs.value, str) else ""
    return text_size(inputs.value, limit=inputs.limit) + _replacement_units(
        text=text,
        old=inputs.arg(index=0, name="old"),
        new=inputs.arg(index=1, name="new"),
        count=inputs.arg(index=2, name="count"),
        escaping=inputs.escaping,
    )


def _joined_filter(*, inputs: CostInputs) -> int:
    separator = inputs.arg(index=0, name="d", default="")
    return _joined_units(items=inputs.value, separator=separator if isinstance(separator, str) else "", limit=inputs.limit, escaping=inputs.escaping)


def _formatted_filter(*, inputs: CostInputs) -> int:
    template = inputs.value if isinstance(inputs.value, str) else ""
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


_FILTERS: Final = cast("dict[str, Callable[..., Any]]", jinja2.filters.FILTERS)

# The cost of every filter the environment can register, keyed by the filter function itself: Pipelex
# registers its own `format` under the name Jinja's has.
FILTER_COSTS: Final[dict[Callable[..., Any], OperationCost]] = {
    _FILTERS["abs"]: LINEAR,
    _FILTERS["attr"]: LINEAR,
    _FILTERS["batch"]: OperationCost(estimate=_batched),
    _FILTERS["capitalize"]: LINEAR,
    _FILTERS["center"]: OperationCost(estimate=_centered),
    _FILTERS["count"]: LINEAR,
    _FILTERS["default"]: LINEAR,
    _FILTERS["dictsort"]: OperationCost(estimate=_materialized),
    _FILTERS["escape"]: OperationCost(estimate=_escaped_text),
    _FILTERS["filesizeformat"]: LINEAR,
    _FILTERS["first"]: LINEAR,
    _FILTERS["float"]: LINEAR,
    _FILTERS["forceescape"]: OperationCost(estimate=_escaped_text),
    _FILTERS["format"]: OperationCost(estimate=_formatted_filter),
    _FILTERS["groupby"]: OperationCost(estimate=_materialized),
    _FILTERS["indent"]: OperationCost(estimate=_indented),
    _FILTERS["int"]: LINEAR,
    _FILTERS["items"]: LINEAR,
    _FILTERS["join"]: OperationCost(estimate=_joined_filter, materializes=True),
    _FILTERS["last"]: LINEAR,
    _FILTERS["list"]: OperationCost(estimate=_materialized),
    _FILTERS["lower"]: LINEAR,
    _FILTERS["map"]: LINEAR,
    _FILTERS["max"]: LINEAR,
    _FILTERS["min"]: LINEAR,
    _FILTERS["pprint"]: OperationCost(estimate=_pprint),
    _FILTERS["random"]: LINEAR,
    _FILTERS["reject"]: LINEAR,
    _FILTERS["rejectattr"]: LINEAR,
    _FILTERS["replace"]: OperationCost(estimate=_replaced_filter),
    _FILTERS["reverse"]: OperationCost(estimate=_reversed),
    _FILTERS["round"]: LINEAR,
    _FILTERS["safe"]: OperationCost(estimate=_text),
    _FILTERS["select"]: LINEAR,
    _FILTERS["selectattr"]: LINEAR,
    _FILTERS["slice"]: OperationCost(estimate=_sliced),
    _FILTERS["sort"]: OperationCost(estimate=_materialized),
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
    with_images: LINEAR,
}

# The filters whose result is template arithmetic, capped like an operator's.
INTEGER_FILTERS: Final[frozenset[Callable[..., Any]]] = frozenset({_FILTERS["int"], _FILTERS["sum"]})


########################################################################################
# Tests
########################################################################################


@dataclass(frozen=True)
class TestCost:
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
