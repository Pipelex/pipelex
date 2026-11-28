"""Mock values that honour a site's contract facts, for the dry run.

Polyfactory honours the bounds pydantic states natively on a field typed by a field type, but not the sites whose facts
pydantic does not state or polyfactory would build without bound: a field typed by a concept (`Number`, `Text`), whose facts
a validator enforces on the value the concept carries, and a text field with any text constraint, whose `pattern` and
`format` a validator asserts and whose lengths polyfactory would fill to their full size. For those the mock factory asks
this module for a value. Each value is checked against every fact with the same judgment the runtime enforces
(`constraint_break_message`), so a mock is never a value the site refuses; when no candidate satisfies the facts, the most
natural candidate is returned and validation refuses it, as for any site no value can satisfy.

A mock is a value the dry run builds and the standard sets no size for, so its size is bounded here, never at the language:
a mock text holds at most `MAX_MOCK_TEXT_LENGTH` characters, which leaves a site whose `min_length` passes it, with nothing
a realistic method writes, without an honouring mock rather than holding a gigabyte for a validation. A pattern's draws
stay short since the language bounds its counted repetitions (`MAX_PATTERN_EXPANDED_POSITIONS`), a draw longer than the
site's `max_length` is skipped, and the candidates stop at the first one whose search against the pattern passes its time
limit. The runtime searches a pattern with the `regex` engine, which reads constructs polyfactory's generator cannot draw
from, such as atomic groups `(?>…)`, possessive repeats `a++` and conditionals `(?(1)…|…)`: the first two are drawn from
in their plain form, `(?:…)` and `a+`, whose matches are checked like any draw, and a pattern the generator still cannot
read gives no draw, so the mock falls back to the site's examples and plain candidates, never crashing the dry run.

A number mock keeps an integer exact: an example is returned as it is written, and a site whose bounds are all integers
draws an integer between them, so a bound past a float's precision, such as `9007199254740993`, is honoured.
"""

import random
import re
from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast

from polyfactory.value_generators.regex import RegexFactory

from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.language.contract_facts import (
    TEXT_CONSTRAINT_KEYS,
    ContractFactKey,
    ValueFormat,
    constraint_break_message,
    format_sample,
    format_short_sample,
    is_plain_number,
    pattern_search_overruns,
)

# How far from a single bound a number mock may land, and how many regex draws a text mock tries.
_NUMBER_SPAN = 100.0
_PATTERN_DRAWS = 25
_REGEX_FACTORY = RegexFactory(random=random.Random())

MAX_MOCK_TEXT_LENGTH = 100_000
"""The most characters a mock text holds, whatever the site's `min_length`."""

_PLAIN_MOCK_LENGTH = 5
"""The length of the plain mock of a site stating no `min_length`, within its `max_length`."""

# A pattern read as tokens: an escape, a character class, an atomic group's opening, a possessive repeat, or any other
# character. Only the two `regex` constructs the generator does not read are rewritten, so the rest is kept as written.
_GENERATOR_TOKENS = re.compile(r"\\.|\[\^?\]?(?:\\.|[^\]\\])*\]|\(\?>|\{\d*,?\d*\}\+|[*+?]\+|.", re.DOTALL)
_ATOMIC_GROUP_OPENING = "(?>"


def _honours(*, value: Any, facts: Mapping[str, Any]) -> bool:
    return constraint_break_message(value=value, facts=facts) is None


def _honouring_examples(*, facts: Mapping[str, Any]) -> list[Any]:
    examples = facts.get(ContractFactKey.EXAMPLES)
    if not isinstance(examples, list):
        return []
    return [example for example in cast("list[Any]", examples) if _honours(value=example, facts=facts)]


def _integer_draw(*, facts: Mapping[str, Any]) -> int | None:
    """An integer inside the site's bounds when each bound it states is an integer and the range holds one, else `None`.

    Drawn as an integer, so a bound past a float's precision is honoured exactly.
    """
    bounds = [facts[key] for key in (ContractFactKey.MINIMUM, ContractFactKey.EXCLUSIVE_MINIMUM, ContractFactKey.MAXIMUM, ContractFactKey.EXCLUSIVE_MAXIMUM) if key in facts]
    if not bounds or not all(isinstance(bound, int) and not isinstance(bound, bool) for bound in bounds):
        return None
    lower_bounds: list[int] = []
    if ContractFactKey.MINIMUM in facts:
        lower_bounds.append(facts[ContractFactKey.MINIMUM])
    if ContractFactKey.EXCLUSIVE_MINIMUM in facts:
        lower_bounds.append(facts[ContractFactKey.EXCLUSIVE_MINIMUM] + 1)
    upper_bounds: list[int] = []
    if ContractFactKey.MAXIMUM in facts:
        upper_bounds.append(facts[ContractFactKey.MAXIMUM])
    if ContractFactKey.EXCLUSIVE_MAXIMUM in facts:
        upper_bounds.append(facts[ContractFactKey.EXCLUSIVE_MAXIMUM] - 1)
    span = int(_NUMBER_SPAN)
    lower = max(lower_bounds) if lower_bounds else min(upper_bounds) - span
    upper = min(upper_bounds) if upper_bounds else lower + span
    if lower > upper:
        return None
    return random.randint(lower, upper)


def mock_number(*, facts: Mapping[str, Any]) -> int | float:
    """A number inside the site's bounds: an honouring example as it is written when there is one, else an integer between
    integer bounds, else a draw between the bounds.
    """
    examples = [example for example in _honouring_examples(facts=facts) if is_plain_number(value=example)]
    if examples:
        return cast("int | float", random.choice(examples))
    integer = _integer_draw(facts=facts)
    if integer is not None:
        return integer
    lower_bounds = [facts[key] for key in (ContractFactKey.MINIMUM, ContractFactKey.EXCLUSIVE_MINIMUM) if key in facts]
    upper_bounds = [facts[key] for key in (ContractFactKey.MAXIMUM, ContractFactKey.EXCLUSIVE_MAXIMUM) if key in facts]
    lower: float = float(max(lower_bounds)) if lower_bounds else (float(min(upper_bounds)) - _NUMBER_SPAN if upper_bounds else 0.0)
    upper: float = float(min(upper_bounds)) if upper_bounds else lower + _NUMBER_SPAN
    drawn = random.uniform(lower, upper)
    if _honours(value=drawn, facts=facts):
        return drawn
    # A draw that landed on an exclusive end: the middle of the range is inside it whenever the range holds a value.
    return (lower + upper) / 2


def _length_bounds(*, facts: Mapping[str, Any]) -> tuple[int, int]:
    """The shortest and longest a mock text of the site may be: its lengths, the longest capped at `MAX_MOCK_TEXT_LENGTH`."""
    min_length = facts.get(ContractFactKey.MIN_LENGTH)
    max_length = facts.get(ContractFactKey.MAX_LENGTH)
    shortest = min(min_length, MAX_MOCK_TEXT_LENGTH) if isinstance(min_length, int) and min_length > 0 else 0
    longest = min(max_length, MAX_MOCK_TEXT_LENGTH) if isinstance(max_length, int) else MAX_MOCK_TEXT_LENGTH
    return shortest, longest


def _padded(*, text: str, shortest: int) -> list[str]:
    """A text lengthened to `shortest` with letters after it, then before it, so a pattern anchored at one end still matches."""
    missing = shortest - len(text)
    if missing <= 0:
        return []
    return [f"{text}{'a' * missing}", f"{'a' * missing}{text}"]


def _generator_dialect(*, pattern: str) -> str:
    """The pattern with the `regex` constructs the generator does not read written in their plain form: an atomic group
    `(?>…)` as `(?:…)`, and a possessive repeat (`a*+`, `a++`, `a?+`, `a{2,}+`) as its greedy one.

    The plain form matches every text the pattern matches and more, so each draw is still checked against the pattern.
    """
    tokens: list[str] = []
    for token_match in _GENERATOR_TOKENS.finditer(pattern):
        token = token_match.group()
        if token == _ATOMIC_GROUP_OPENING:
            tokens.append("(?:")
        elif len(token) > 1 and token.endswith("+") and token[0] in "*+?{":
            tokens.append(token[:-1])
        else:
            tokens.append(token)
    return "".join(tokens)


def _pattern_draw(*, pattern: str) -> str | None:
    """A text drawn from the pattern by polyfactory's generator, or `None` when the generator cannot draw from it.

    The generator reads a pattern with Python's own parser and maps each construct to a draw: one it has no draw for, such
    as a conditional, is a `KeyError`, and a class it finds no character for, such as one excluding every printable
    character, an `IndexError`.
    """
    try:
        return _REGEX_FACTORY(_generator_dialect(pattern=pattern))
    except (KeyError, IndexError):
        return None


def _text_candidates(*, facts: Mapping[str, Any]) -> Iterator[str]:
    """Texts worth trying, most natural first: examples, the format's samples, regex draws and their padded forms, then a
    plain run of letters as long as the lengths allow. None is longer than `MAX_MOCK_TEXT_LENGTH`.
    """
    shortest, longest = _length_bounds(facts=facts)
    for example in _honouring_examples(facts=facts):
        if isinstance(example, str):
            yield example
    text_format = facts.get(ContractFactKey.FORMAT)
    known_format = ValueFormat(text_format) if isinstance(text_format, str) and text_format in set(ValueFormat) else None
    if known_format is not None:
        yield format_sample(text_format=known_format)
        yield format_short_sample(text_format=known_format)
    pattern = facts.get(ContractFactKey.PATTERN)
    if isinstance(pattern, str):
        for _ in range(_PATTERN_DRAWS):
            drawn = _pattern_draw(pattern=pattern)
            if drawn is None:
                break
            if len(drawn) > longest:
                continue
            # A pattern is searched, not matched whole: a draw for `@corp\.com$` reads `@corp.com`, which a format may
            # refuse alone, so each draw is also tried after the format's own sample and after a single letter, and
            # lengthened to the site's `min_length`.
            yield drawn
            yield f"a{drawn}"
            if known_format is ValueFormat.EMAIL and drawn.startswith("@"):
                yield f"someone{drawn}"
            yield from _padded(text=drawn, shortest=shortest)
    plain_length = shortest or _PLAIN_MOCK_LENGTH
    yield "a" * min(plain_length, longest)


def mock_text(*, facts: Mapping[str, Any]) -> str:
    """A text honouring every one of the site's facts, or the most natural candidate when none does.

    The search stops at the first candidate whose search against the site's `pattern` passes its time limit: a pattern
    that backtracks catastrophically would spend that limit on every candidate.
    """
    first_candidate: str | None = None
    for candidate in _text_candidates(facts=facts):
        if first_candidate is None:
            first_candidate = candidate
        if pattern_search_overruns(value=candidate, facts=facts):
            break
        if _honours(value=candidate, facts=facts):
            return candidate
    return first_candidate or ""


def mock_provider(*, annotation: Any, facts: Mapping[str, Any]) -> Callable[[], Any] | None:
    """A provider of values for a site holding `annotation` and declaring `facts`, or `None` when polyfactory honours them
    alone: a `Number` or `Text` content (or a refinement of one), and a text with a length, a `pattern` or a `format`.
    """
    if isinstance(annotation, type) and issubclass(annotation, NumberContent):
        number_class = annotation

        def number_content() -> Any:
            return number_class(number=mock_number(facts=facts))

        return number_content
    if isinstance(annotation, type) and issubclass(annotation, TextContent):
        text_class = annotation

        def text_content() -> Any:
            return text_class(text=mock_text(facts=facts))

        return text_content
    if annotation is str and any(key in facts for key in TEXT_CONSTRAINT_KEYS):

        def text() -> str:
            return mock_text(facts=facts)

        return text
    return None
