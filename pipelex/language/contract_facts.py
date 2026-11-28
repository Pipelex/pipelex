"""Contract facts — what a field, an input slot or a concept states about its value beyond its type.

Single owner of the MTHDS contract-fact rules (spec: `mthds/docs/spec/mthds-format.md`, "Contract Facts", "Formats",
"Units", "Aggregates" and "Choice Options"): the closed set of keys, the value class each applies to, the formats, unit
identifiers, aggregates and tones, and the judgments every site shares, so that a structure field, an input slot and a
concept are refused by one set of rules. The blueprints call these judgments and raise what they find; the projection into
the generated classes and the form descriptors reads the same keys.

Two groups of facts, with different consequences:

- **Constraints**, the four numeric bounds, `min_length`, `max_length`, `pattern` and `format`: a value that breaks one is
  invalid, and the runtime enforces them wherever it validates the value's type.
- **Descriptions**, `unit`, `aggregate` and `examples`: they describe a value and never make it invalid.

Pure standard knowledge: stdlib only, no pydantic and no other `pipelex` import but the hints vocabulary, so every layer may
read it.
"""

import ipaddress
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any, NamedTuple, cast
from uuid import UUID

from pipelex.language.intent_hints import HintSiteValueKind


class ContractFactKey(StrEnum):
    """The keys a contract fact is written under, on a structure field, an input slot or (for `unit`) a concept."""

    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    EXCLUSIVE_MINIMUM = "exclusive_minimum"
    EXCLUSIVE_MAXIMUM = "exclusive_maximum"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    PATTERN = "pattern"
    FORMAT = "format"
    UNIT = "unit"
    AGGREGATE = "aggregate"
    EXAMPLES = "examples"

    @property
    def applicable_classes(self) -> frozenset["ValueClass"]:
        """The value classes a site must hold for this key to apply there."""
        match self:
            case (
                ContractFactKey.MINIMUM
                | ContractFactKey.MAXIMUM
                | ContractFactKey.EXCLUSIVE_MINIMUM
                | ContractFactKey.EXCLUSIVE_MAXIMUM
                | ContractFactKey.UNIT
                | ContractFactKey.AGGREGATE
            ):
                return frozenset({ValueClass.NUMBER})
            case ContractFactKey.MIN_LENGTH | ContractFactKey.MAX_LENGTH | ContractFactKey.PATTERN | ContractFactKey.FORMAT:
                return frozenset({ValueClass.TEXT})
            case ContractFactKey.EXAMPLES:
                return frozenset(ValueClass)

    @property
    def is_constraint(self) -> bool:
        """Whether a value breaking this fact is invalid: the bounds, the lengths, `pattern` and `format`."""
        match self:
            case (
                ContractFactKey.MINIMUM
                | ContractFactKey.MAXIMUM
                | ContractFactKey.EXCLUSIVE_MINIMUM
                | ContractFactKey.EXCLUSIVE_MAXIMUM
                | ContractFactKey.MIN_LENGTH
                | ContractFactKey.MAX_LENGTH
                | ContractFactKey.PATTERN
                | ContractFactKey.FORMAT
            ):
                return True
            case ContractFactKey.UNIT | ContractFactKey.AGGREGATE | ContractFactKey.EXAMPLES:
                return False


CHOICES_KEY = "choices"
"""The key a site lists its choice options under, which `method.contract_fact_invalid` names as its `fact` too."""

NUMERIC_BOUND_KEYS: tuple[ContractFactKey, ...] = (
    ContractFactKey.MINIMUM,
    ContractFactKey.MAXIMUM,
    ContractFactKey.EXCLUSIVE_MINIMUM,
    ContractFactKey.EXCLUSIVE_MAXIMUM,
)
LENGTH_KEYS: tuple[ContractFactKey, ...] = (ContractFactKey.MIN_LENGTH, ContractFactKey.MAX_LENGTH)
TEXT_CONSTRAINT_KEYS: frozenset[ContractFactKey] = frozenset(
    {ContractFactKey.MIN_LENGTH, ContractFactKey.MAX_LENGTH, ContractFactKey.PATTERN, ContractFactKey.FORMAT}
)
CONTRACT_FACT_KEY_NAMES: tuple[str, ...] = tuple(ContractFactKey)
"""Every contract-fact key, in the order the standard's key table lists them, which is the order a site serializes them in."""


class ContractFactReason(StrEnum):
    """The reasons of `method.contract_fact_invalid`, as the standard's error registry lists them."""

    INAPPLICABLE = "inapplicable"
    NOT_VALUE_SLOT = "not_value_slot"
    MALFORMED = "malformed"
    CONTRADICTORY = "contradictory"
    VALUE_BREAKS_CONTRACT = "value_breaks_contract"
    DUPLICATE_OPTION = "duplicate_option"


class ValueClass(StrEnum):
    """The value classes a site holds, which decide the contract facts it takes. Every other site holds none."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    TIME = "time"

    @classmethod
    def of_site_kind(cls, *, site_kind: HintSiteValueKind) -> "ValueClass | None":
        """The value class of a site classified for hints, or `None` for a site holding no plain value."""
        match site_kind:
            case HintSiteValueKind.TEXT_VALUED:
                return ValueClass.TEXT
            case HintSiteValueKind.NUMBER_VALUED:
                return ValueClass.NUMBER
            case HintSiteValueKind.DATE_VALUED:
                return ValueClass.DATE
            case HintSiteValueKind.TIME_VALUED:
                return ValueClass.TIME
            case HintSiteValueKind.IMAGE_VALUED | HintSiteValueKind.DOCUMENT_VALUED | HintSiteValueKind.OTHER:
                return None


class FactSiteType(StrEnum):
    """The precise type of the value a site with a value class holds, which decides what an example or a bound may be.

    A field typed by a field type knows it exactly; a site typed by a concept knows only its value class, so a date-valued
    concept takes either a date or a date-time, and a number-valued one any number.
    """

    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    DATE_OR_DATETIME = "date_or_datetime"
    TIME = "time"

    @property
    def value_class(self) -> ValueClass:
        match self:
            case FactSiteType.TEXT:
                return ValueClass.TEXT
            case FactSiteType.INTEGER | FactSiteType.NUMBER:
                return ValueClass.NUMBER
            case FactSiteType.DATE | FactSiteType.DATETIME | FactSiteType.DATE_OR_DATETIME:
                return ValueClass.DATE
            case FactSiteType.TIME:
                return ValueClass.TIME

    @property
    def is_integer(self) -> bool:
        match self:
            case FactSiteType.INTEGER:
                return True
            case (
                FactSiteType.TEXT
                | FactSiteType.NUMBER
                | FactSiteType.DATE
                | FactSiteType.DATETIME
                | FactSiteType.DATE_OR_DATETIME
                | FactSiteType.TIME
            ):
                return False

    @classmethod
    def of_concept_class(cls, *, value_class: ValueClass) -> "FactSiteType":
        """The type of a site typed by a concept of a value class, which states no finer type."""
        match value_class:
            case ValueClass.TEXT:
                return FactSiteType.TEXT
            case ValueClass.NUMBER:
                return FactSiteType.NUMBER
            case ValueClass.DATE:
                return FactSiteType.DATE_OR_DATETIME
            case ValueClass.TIME:
                return FactSiteType.TIME


class ValueFormat(StrEnum):
    """The closed set of `format` values, each the JSON Schema format of the same name."""

    EMAIL = "email"
    URI = "uri"
    DATE_TIME = "date-time"
    UUID = "uuid"
    HOSTNAME = "hostname"
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class Aggregate(StrEnum):
    """How the values of a number-valued field combine across the records that hold it."""

    SUM = "sum"
    AVERAGE = "average"


class Tone(StrEnum):
    """How a choice option or a condition's outcome reads to a person. Never a colour: each consumer maps it to its own palette."""

    POSITIVE = "positive"
    CAUTION = "caution"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


PERCENT_UNIT = "percent"

UNITS_OF_MEASURE: frozenset[str] = frozenset(
    {
        # Length
        "mm",
        "cm",
        "m",
        "km",
        # Area
        "m2",
        # Volume
        "ml",
        "l",
        # Mass
        "g",
        "kg",
        "t",
        # Duration
        "ms",
        "s",
        "min",
        "h",
        "day",
        # Data size, in powers of 1000
        "byte",
        "kB",
        "MB",
        "GB",
    }
)
"""The units of measure the standard lists, compared exactly, letter case included."""

_CURRENCY_CODE_PATTERN = re.compile(r"[A-Z]{3}")


def is_unit_identifier(*, unit: str) -> bool:
    """Whether a string is a unit identifier: an ISO 4217-shaped currency code, `percent`, or a listed unit of measure.

    A currency is any three uppercase ASCII letters: the standard has a validator warn, never refuse, about a code its copy of
    ISO 4217 does not list, since the list changes over time.
    """
    return bool(_CURRENCY_CODE_PATTERN.fullmatch(unit)) or unit == PERCENT_UNIT or unit in UNITS_OF_MEASURE


# ---- Formats ------------------------------------------------------------------------------------------------------------

# RFC 5321's `Mailbox` with a dot-string local part and a domain of host-name labels: the shape every validator of the
# JSON Schema `email` format reads alike. A quoted local part and an address literal are left out, as they are by the
# common validators.
_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
# RFC 3986: a scheme, a colon, then characters a URI may hold, with no white space.
_URI_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>\"{}|\\^`]*")
# RFC 3339 `date-time`: a full date, `T` (or `t`, or a space is NOT allowed), a time with optional fraction, and an offset.
_DATE_TIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})")
_UUID_PATTERN = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
_HOSTNAME_LABEL_PATTERN = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_IPV4_PATTERN = re.compile(r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}")
_HOSTNAME_MAX_LENGTH = 253


def format_sample(*, text_format: ValueFormat) -> str:
    """A well-formed text of a format, for a mock value that has to satisfy the format and has no authored example."""
    match text_format:
        case ValueFormat.EMAIL:
            return "someone@example.com"
        case ValueFormat.URI:
            return "https://example.com/"
        case ValueFormat.DATE_TIME:
            return "2026-01-01T09:00:00Z"
        case ValueFormat.UUID:
            return "123e4567-e89b-42d3-a456-426614174000"
        case ValueFormat.HOSTNAME:
            return "example.com"
        case ValueFormat.IPV4:
            return "192.0.2.1"
        case ValueFormat.IPV6:
            return "2001:db8::1"


def format_short_sample(*, text_format: ValueFormat) -> str:
    """The shortest well-formed text of a format a mock tries when the site's `max_length` leaves no room for `format_sample`."""
    match text_format:
        case ValueFormat.EMAIL:
            return "a@b.co"
        case ValueFormat.URI:
            return "https://a.co"
        case ValueFormat.DATE_TIME:
            return "2026-01-01T09:00:00Z"
        case ValueFormat.UUID:
            return "123e4567-e89b-42d3-a456-426614174000"
        case ValueFormat.HOSTNAME:
            return "a.co"
        case ValueFormat.IPV4:
            return "1.1.1.1"
        case ValueFormat.IPV6:
            return "::1"


def text_matches_format(*, text: str, text_format: ValueFormat) -> bool:
    """Whether a text is well-formed in a format. The runtime asserts every format, whatever a schema validator does by default."""
    match text_format:
        case ValueFormat.EMAIL:
            return bool(_EMAIL_PATTERN.fullmatch(text))
        case ValueFormat.URI:
            return bool(_URI_PATTERN.fullmatch(text))
        case ValueFormat.DATE_TIME:
            if not _DATE_TIME_PATTERN.fullmatch(text):
                return False
            try:
                datetime.fromisoformat(text.replace("z", "Z").replace("t", "T"))
            except ValueError:
                return False
            return True
        case ValueFormat.UUID:
            if not _UUID_PATTERN.fullmatch(text):
                return False
            UUID(text)
            return True
        case ValueFormat.HOSTNAME:
            if not text or len(text) > _HOSTNAME_MAX_LENGTH:
                return False
            return all(_HOSTNAME_LABEL_PATTERN.fullmatch(label) for label in text.removesuffix(".").split("."))
        case ValueFormat.IPV4:
            return bool(_IPV4_PATTERN.fullmatch(text))
        case ValueFormat.IPV6:
            try:
                ipaddress.IPv6Address(text)
            except ValueError:
                return False
            return True


def pattern_compile_error(*, pattern: str) -> str | None:
    """Why a `pattern` does not compile, or `None` when it does.

    The pattern is compiled as the runtime enforces it, with Python's `re`, which reads the interoperable subset of
    ECMA-262 the standard has authors keep to alike.
    """
    try:
        re.compile(pattern)
    except re.error as exc:
        return str(exc)
    return None


def text_matches_pattern(*, text: str, pattern: str) -> bool:
    """Whether a text matches a pattern anywhere, as JSON Schema's `pattern` does: an anchored pattern matches the whole text."""
    return re.search(pattern, text) is not None


# ---- Shapes -------------------------------------------------------------------------------------------------------------


def is_plain_number(*, value: Any) -> bool:
    """Whether a value is a number as a bound or an example holds one: an int or a float, never a boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def malformed_fact_message(*, key: ContractFactKey, value: Any) -> str | None:
    """Why a fact's own value breaks the rules for its key, whatever site carries it, or `None` when it does not."""
    match key:
        case ContractFactKey.MINIMUM | ContractFactKey.MAXIMUM | ContractFactKey.EXCLUSIVE_MINIMUM | ContractFactKey.EXCLUSIVE_MAXIMUM:
            if not is_plain_number(value=value) or not math.isfinite(value):
                return f"'{key}' must be a finite number, got {value!r}"
        case ContractFactKey.MIN_LENGTH | ContractFactKey.MAX_LENGTH:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return f"'{key}' must be an integer of at least 0, got {value!r}"
        case ContractFactKey.PATTERN:
            if not isinstance(value, str):
                return f"'pattern' must be a string, got {value!r}"
            compile_error = pattern_compile_error(pattern=value)
            if compile_error is not None:
                return f"'pattern' does not compile as a regular expression: {compile_error}"
        case ContractFactKey.FORMAT:
            if not isinstance(value, str) or value not in set(ValueFormat):
                return f"'format' must be one of {', '.join(ValueFormat)}, got {value!r}"
        case ContractFactKey.UNIT:
            if not isinstance(value, str) or not is_unit_identifier(unit=value):
                return (
                    f"'unit' must be a unit identifier: three uppercase letters naming a currency, 'percent', or one of "
                    f"{', '.join(sorted(UNITS_OF_MEASURE))}; got {value!r}"
                )
        case ContractFactKey.AGGREGATE:
            if not isinstance(value, str) or value not in set(Aggregate):
                return f"'aggregate' must be one of {', '.join(Aggregate)}, got {value!r}"
        case ContractFactKey.EXAMPLES:
            if not isinstance(value, list) or not value:
                return f"'examples' must be a non-empty array, got {value!r}"
    return None


# ---- Judgments ----------------------------------------------------------------------------------------------------------


class ContractFactFinding(NamedTuple):
    """One fault of a site's contract facts: the key at fault, why, and a sentence naming it."""

    fact: str
    reason: ContractFactReason
    message: str


def contradiction_findings(*, facts: Mapping[str, Any], is_integer: bool) -> list[ContractFactFinding]:
    """The facts of one site that contradict each other, judged without its value class: two lower or two upper bounds,
    a range that holds no value of the site, and a minimum length above the maximum one.

    `is_integer` is whether the site holds integers, for which an exclusive range between two neighbours is empty.
    """
    findings: list[ContractFactFinding] = []
    minimum = facts.get(ContractFactKey.MINIMUM)
    exclusive_minimum = facts.get(ContractFactKey.EXCLUSIVE_MINIMUM)
    maximum = facts.get(ContractFactKey.MAXIMUM)
    exclusive_maximum = facts.get(ContractFactKey.EXCLUSIVE_MAXIMUM)
    if minimum is not None and exclusive_minimum is not None:
        findings.append(
            ContractFactFinding(
                ContractFactKey.EXCLUSIVE_MINIMUM, ContractFactReason.CONTRADICTORY, "'minimum' and 'exclusive_minimum' cannot both be set"
            )
        )
    if maximum is not None and exclusive_maximum is not None:
        findings.append(
            ContractFactFinding(
                ContractFactKey.EXCLUSIVE_MAXIMUM, ContractFactReason.CONTRADICTORY, "'maximum' and 'exclusive_maximum' cannot both be set"
            )
        )
    if not findings and _range_is_empty(
        minimum=minimum, exclusive_minimum=exclusive_minimum, maximum=maximum, exclusive_maximum=exclusive_maximum, is_integer=is_integer
    ):
        upper_key = ContractFactKey.MAXIMUM if maximum is not None else ContractFactKey.EXCLUSIVE_MAXIMUM
        findings.append(
            ContractFactFinding(upper_key, ContractFactReason.CONTRADICTORY, "the bounds leave no value the site may hold: the range is empty")
        )
    min_length = facts.get(ContractFactKey.MIN_LENGTH)
    max_length = facts.get(ContractFactKey.MAX_LENGTH)
    if min_length is not None and max_length is not None and min_length > max_length:
        findings.append(
            ContractFactFinding(
                ContractFactKey.MIN_LENGTH,
                ContractFactReason.CONTRADICTORY,
                f"'min_length' ({min_length}) exceeds 'max_length' ({max_length})",
            )
        )
    return findings


def _range_is_empty(
    *,
    minimum: float | None,
    exclusive_minimum: float | None,
    maximum: float | None,
    exclusive_maximum: float | None,
    is_integer: bool,
) -> bool:
    lower = minimum if minimum is not None else exclusive_minimum
    upper = maximum if maximum is not None else exclusive_maximum
    if lower is None or upper is None:
        return False
    if is_integer:
        lowest = math.floor(exclusive_minimum) + 1 if minimum is None and exclusive_minimum is not None else math.ceil(lower)
        highest = math.ceil(exclusive_maximum) - 1 if maximum is None and exclusive_maximum is not None else math.floor(upper)
        return lowest > highest
    if lower > upper:
        return True
    return lower == upper and (minimum is None or maximum is None)


def applicability_findings(
    *,
    facts: Mapping[str, Any],
    value_class: ValueClass | None,
    is_slot: bool,
    has_choices: bool,
) -> list[ContractFactFinding]:
    """The facts of a site that do not apply to its value class, and the choices a slot may not carry.

    On an input slot whose concept holds no plain value, every fact and `choices` are refused as `not_value_slot`; on any
    other site, a key whose value classes exclude the site's as `inapplicable`. `aggregate` never applies to a slot, and
    `choices` only to a text-valued slot.
    """
    findings: list[ContractFactFinding] = []
    if is_slot and value_class is None:
        for key in [*facts, *([CHOICES_KEY] if has_choices else [])]:
            findings.append(
                ContractFactFinding(
                    key,
                    ContractFactReason.NOT_VALUE_SLOT,
                    f"'{key}' is not allowed on an input slot whose concept holds no plain value (text, number, date or time): "
                    "the fields of a structure carry such facts themselves",
                )
            )
        return findings
    for key_name in facts:
        key = ContractFactKey(key_name)
        if is_slot and key is ContractFactKey.AGGREGATE:
            findings.append(
                ContractFactFinding(
                    key,
                    ContractFactReason.INAPPLICABLE,
                    "'aggregate' is not allowed on an input slot, which holds one value, never a column of records",
                )
            )
            continue
        if value_class is None or value_class not in key.applicable_classes:
            applicable = " or ".join(f"{applicable_class}-valued" for applicable_class in sorted(key.applicable_classes))
            held = f"{value_class}-valued" if value_class is not None else "of no value class"
            findings.append(
                ContractFactFinding(key, ContractFactReason.INAPPLICABLE, f"'{key}' applies to a {applicable} site, and this site is {held}")
            )
    if is_slot and has_choices:
        if value_class is not ValueClass.TEXT:
            findings.append(
                ContractFactFinding(CHOICES_KEY, ContractFactReason.INAPPLICABLE, "'choices' is allowed on a text-valued input slot only")
            )
        else:
            # The options already decide every value the slot holds, so a text constraint beside them says nothing a value
            # could break, or contradicts an option.
            for key_name in facts:
                key = ContractFactKey(key_name)
                if key in TEXT_CONSTRAINT_KEYS or key is ContractFactKey.EXAMPLES:
                    findings.append(
                        ContractFactFinding(
                            key, ContractFactReason.INAPPLICABLE, f"'{key}' is not allowed beside 'choices': the options list every value"
                        )
                    )
    return findings


def value_type_message(*, value: Any, site_type: FactSiteType) -> str | None:
    """Why a value (an example, a default) is not a value of the site's type, or `None` when it is."""
    match site_type:
        case FactSiteType.TEXT:
            valid = isinstance(value, str)
        case FactSiteType.INTEGER:
            valid = isinstance(value, int) and not isinstance(value, bool)
        case FactSiteType.NUMBER:
            valid = is_plain_number(value=value)
        case FactSiteType.DATE:
            valid = isinstance(value, date) and not isinstance(value, datetime)
        case FactSiteType.DATETIME:
            valid = isinstance(value, datetime)
        case FactSiteType.DATE_OR_DATETIME:
            valid = isinstance(value, date)
        case FactSiteType.TIME:
            valid = isinstance(value, time)
    if valid:
        return None
    return f"{value!r} is not a value of a {str(site_type).replace('_', ' ')} site"


def constraint_break_message(*, value: Any, facts: Mapping[str, Any]) -> str | None:
    """The first constraint of a site a value of the site's type breaks, as a sentence, or `None` when it breaks none."""
    if is_plain_number(value=value):
        minimum = facts.get(ContractFactKey.MINIMUM)
        if minimum is not None and value < minimum:
            return f"{value!r} is below the minimum {minimum!r}"
        maximum = facts.get(ContractFactKey.MAXIMUM)
        if maximum is not None and value > maximum:
            return f"{value!r} is above the maximum {maximum!r}"
        exclusive_minimum = facts.get(ContractFactKey.EXCLUSIVE_MINIMUM)
        if exclusive_minimum is not None and value <= exclusive_minimum:
            return f"{value!r} is not above the exclusive minimum {exclusive_minimum!r}"
        exclusive_maximum = facts.get(ContractFactKey.EXCLUSIVE_MAXIMUM)
        if exclusive_maximum is not None and value >= exclusive_maximum:
            return f"{value!r} is not below the exclusive maximum {exclusive_maximum!r}"
    if isinstance(value, str):
        min_length = facts.get(ContractFactKey.MIN_LENGTH)
        if min_length is not None and len(value) < min_length:
            return f"{value!r} holds fewer than {min_length} characters"
        max_length = facts.get(ContractFactKey.MAX_LENGTH)
        if max_length is not None and len(value) > max_length:
            return f"{value!r} holds more than {max_length} characters"
        pattern = facts.get(ContractFactKey.PATTERN)
        if pattern is not None and pattern_compile_error(pattern=pattern) is None and not text_matches_pattern(text=value, pattern=pattern):
            return f"{value!r} does not match the pattern {pattern!r}"
        text_format = facts.get(ContractFactKey.FORMAT)
        if (
            isinstance(text_format, str)
            and text_format in set(ValueFormat)
            and not text_matches_format(text=value, text_format=ValueFormat(text_format))
        ):
            return f"{value!r} is not well-formed as {text_format}"
    return None


def value_findings(*, facts: Mapping[str, Any], site_type: FactSiteType, default_value: Any = None) -> list[ContractFactFinding]:
    """The examples and the default of a site that are not valid values of it.

    Judged once the site's type is known: an example must be a value of the site's type that satisfies every constraint the
    site declares, and so must a default. (`examples` beside `choices` never reaches here: an enumeration field holds no value
    class, and a slot's options refuse it as `inapplicable`.)
    """
    findings: list[ContractFactFinding] = []
    examples = facts.get(ContractFactKey.EXAMPLES)
    if isinstance(examples, list):
        for example in cast("list[Any]", examples):
            example_message = value_type_message(value=example, site_type=site_type) or constraint_break_message(value=example, facts=facts)
            if example_message is not None:
                findings.append(
                    ContractFactFinding(ContractFactKey.EXAMPLES, ContractFactReason.VALUE_BREAKS_CONTRACT, f"the example {example_message}")
                )
                break
    if default_value is not None:
        default_message = constraint_break_message(value=default_value, facts=facts)
        if default_message is not None:
            broken_key = broken_constraint_key(value=default_value, facts=facts)
            findings.append(ContractFactFinding(broken_key, ContractFactReason.VALUE_BREAKS_CONTRACT, f"the default_value {default_message}"))
    return findings


def broken_constraint_key(*, value: Any, facts: Mapping[str, Any]) -> str:
    """The first constraint of a site, in the standard's order, that a value breaks on its own: the fact a refusal names.

    Each constraint is judged alone, so `{minimum: 0, maximum: 10}` refusing 20 names `maximum`, not the first key declared.
    `default_value` stands in when no single constraint is broken alone, which `constraint_break_message` never lets happen.
    """
    for key in CONTRACT_FACT_KEY_NAMES:
        if key in facts and ContractFactKey(key).is_constraint and constraint_break_message(value=value, facts={key: facts[key]}) is not None:
            return key
    return "default_value"


def authored_facts(*, values: Mapping[str, Any]) -> dict[str, Any]:
    """The contract facts a site authors, by key in the standard's order, the keys it leaves out absent."""
    return {key: values[key] for key in CONTRACT_FACT_KEY_NAMES if values.get(key) is not None}


def json_example(*, value: Any) -> Any:
    """An example as JSON holds it: a date, a date-time or a time as its ISO 8601 string, any other value as itself."""
    if isinstance(value, (date, time)):
        return value.isoformat()
    return value


def duplicate_option_message(*, values: Sequence[str], labels: Sequence[str | None]) -> str | None:
    """Why options of one list collide, sharing a value or a label, or `None` when none do."""
    seen_values: set[str] = set()
    for value in values:
        if value in seen_values:
            return f"two options share the value {value!r}"
        seen_values.add(value)
    seen_labels: set[str] = set()
    for label in labels:
        if label is None:
            continue
        if label in seen_labels:
            return f"two options share the label {label!r}"
        seen_labels.add(label)
    return None
