"""Mock values that honour a site's contract facts, for the dry run.

Polyfactory honours the constraints pydantic states natively (bounds, lengths, a pattern) on a field typed by a field type,
but not the two kinds of site whose facts pydantic does not state: a field typed by a concept (`Number`, `Text`), whose facts
a validator enforces on the value the concept carries, and a text field asserting a `format`, which no generator knows. For
those the mock factory asks this module for a value. Each value is checked against every fact with the same judgment the
runtime enforces (`constraint_break_message`), so a mock is never a value the site refuses; when no candidate satisfies the
facts, the best candidate is returned and validation refuses it, as for any site no value can satisfy.
"""

import random
from collections.abc import Callable, Mapping
from typing import Any, cast

from polyfactory.value_generators.regex import RegexFactory

from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.language.contract_facts import (
    ContractFactKey,
    ValueFormat,
    constraint_break_message,
    format_sample,
    format_short_sample,
    is_plain_number,
)

# How far from a single bound a number mock may land, and how many regex draws a text mock tries.
_NUMBER_SPAN = 100.0
_PATTERN_DRAWS = 25
_REGEX_FACTORY = RegexFactory(random=random.Random())


def _honours(*, value: Any, facts: Mapping[str, Any]) -> bool:
    return constraint_break_message(value=value, facts=facts) is None


def _honouring_examples(*, facts: Mapping[str, Any]) -> list[Any]:
    examples = facts.get(ContractFactKey.EXAMPLES)
    if not isinstance(examples, list):
        return []
    return [example for example in cast("list[Any]", examples) if _honours(value=example, facts=facts)]


def mock_number(*, facts: Mapping[str, Any]) -> float:
    """A number inside the site's bounds: an honouring example when there is one, else a draw between the bounds."""
    examples = [example for example in _honouring_examples(facts=facts) if is_plain_number(value=example)]
    if examples:
        return float(random.choice(examples))
    lower_bounds = [facts[key] for key in (ContractFactKey.MINIMUM, ContractFactKey.EXCLUSIVE_MINIMUM) if key in facts]
    upper_bounds = [facts[key] for key in (ContractFactKey.MAXIMUM, ContractFactKey.EXCLUSIVE_MAXIMUM) if key in facts]
    lower: float = float(max(lower_bounds)) if lower_bounds else (float(min(upper_bounds)) - _NUMBER_SPAN if upper_bounds else 0.0)
    upper: float = float(min(upper_bounds)) if upper_bounds else lower + _NUMBER_SPAN
    drawn = random.uniform(lower, upper)
    if _honours(value=drawn, facts=facts):
        return drawn
    # A draw that landed on an exclusive end: the middle of the range is inside it whenever the range holds a value.
    return (lower + upper) / 2


def _text_candidates(*, facts: Mapping[str, Any]) -> list[str]:
    """Texts worth trying, most natural first: examples, the format's samples, regex draws, then a plain run of letters."""
    candidates: list[str] = [example for example in _honouring_examples(facts=facts) if isinstance(example, str)]
    text_format = facts.get(ContractFactKey.FORMAT)
    known_format = ValueFormat(text_format) if isinstance(text_format, str) and text_format in set(ValueFormat) else None
    if known_format is not None:
        candidates.extend([format_sample(text_format=known_format), format_short_sample(text_format=known_format)])
    pattern = facts.get(ContractFactKey.PATTERN)
    if isinstance(pattern, str):
        for _ in range(_PATTERN_DRAWS):
            drawn = _REGEX_FACTORY(pattern)
            # A pattern is searched, not matched whole: a draw for `@corp\.com$` reads `@corp.com`, which a format may
            # refuse alone, so each draw is also tried after the format's own sample and after a single letter.
            candidates.append(drawn)
            candidates.append(f"a{drawn}")
            if known_format is ValueFormat.EMAIL and drawn.startswith("@"):
                candidates.append(f"someone{drawn}")
    min_length = facts.get(ContractFactKey.MIN_LENGTH)
    length = min_length if isinstance(min_length, int) and min_length > 0 else 5
    candidates.append("a" * length)
    return candidates


def mock_text(*, facts: Mapping[str, Any]) -> str:
    """A text honouring every one of the site's facts, or the most natural candidate when none does."""
    candidates = _text_candidates(facts=facts)
    for candidate in candidates:
        if _honours(value=candidate, facts=facts):
            return candidate
    return candidates[0]


def mock_provider(*, annotation: Any, facts: Mapping[str, Any]) -> Callable[[], Any] | None:
    """A provider of values for a site holding `annotation` and declaring `facts`, or `None` when polyfactory honours them
    alone: a `Number` or `Text` content (or a refinement of one), and a text asserting a `format`.
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
    if annotation is str and ContractFactKey.FORMAT in facts:

        def text() -> str:
            return mock_text(facts=facts)

        return text
    return None
