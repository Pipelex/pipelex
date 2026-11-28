"""Choice options and outcome words: the option table of a `choices` list, and the words a table may carry for people.

An option of `choices` is written as a string, which is its value, or as an option table carrying its `value` beside an
optional `label`, `description` and `tone` (spec: `mthds-format.md`, "Choice Options"). Only `value` is validated: the
three others are presentation. A condition's outcome table carries the same three words beside its `pipe` (spec: "Outcome
Labels"), so both read their words through `PresentationWords`.

Normal form, which the crate's fingerprint relies on: a table carrying `value` alone is the bare string of its value, so a
library that writes no words keeps the fingerprint it had whichever form it uses. The parse applies it, so a table that
reaches the blueprint always carries at least one word.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer

from pipelex.core.concepts.exceptions import ContractFactInvalidError
from pipelex.language.contract_facts import CHOICES_KEY, ContractFactReason, Tone, duplicate_option_message

PRESENTATION_WORD_KEYS: tuple[str, ...] = ("label", "description", "tone")
"""The words an option table or an outcome table may carry beside the key it is about, in the order they serialize."""


class PresentationWords(BaseModel):
    """The words a table carries for the people who read a code: its name, what it means, and how it reads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = None
    description: str | None = None
    tone: Tone | None = Field(default=None, strict=False)

    @property
    def has_words(self) -> bool:
        return self.label is not None or self.description is not None or self.tone is not None


class ChoiceOption(PresentationWords):
    """An option of a `choices` list written as a table: its value, and the words for the people who read it."""

    value: str

    @model_serializer(mode="wrap")
    def serialize_without_absent_words(self, handler: SerializerFunctionWrapHandler):
        """An absent word is an absent member, never `null`. The return is deliberately unannotated, as on `ConceptBlueprint`."""
        dumped: dict[str, Any] = handler(self)
        return {key: value for key, value in dumped.items() if value is not None}


ChoiceOptionValue = str | ChoiceOption


class OutcomeTable(PresentationWords):
    """A condition's outcome written as a table: its pipe reference (or special outcome), and the words for people."""

    pipe: str

    @model_serializer(mode="wrap")
    def serialize_without_absent_words(self, handler: SerializerFunctionWrapHandler):
        """An absent word is an absent member, never `null`. The return is deliberately unannotated, as on `ConceptBlueprint`."""
        dumped: dict[str, Any] = handler(self)
        return {key: value for key, value in dumped.items() if value is not None}


OutcomeValue = str | OutcomeTable


def outcome_pipe(*, outcome: OutcomeValue) -> str:
    """The pipe reference (or special outcome) an outcome names, whichever form wrote it."""
    return outcome if isinstance(outcome, str) else outcome.pipe


def parse_outcome(*, raw: Any) -> Any:
    """Read an authored outcome into normal form: a table carrying `pipe` alone becomes its pipe's string.

    A table missing `pipe`, carrying another key, or a word that breaks its rules is refused with a `ValueError`, which the
    standard reports as `method.schema_violation`. A value of another type is returned untouched, for the field's type to refuse.
    """
    if not isinstance(raw, dict):
        return raw
    table = cast("dict[str, Any]", raw)
    if "pipe" not in table:
        msg = "an outcome table must carry its 'pipe'"
        raise ValueError(msg)
    if not isinstance(table["pipe"], str) or not table["pipe"]:
        msg = f"the 'pipe' of an outcome table must be a non-empty string, got {table['pipe']!r}"
        raise ValueError(msg)
    fault = presentation_words_fault(table=table, key_name="pipe", table_name="an outcome table")
    if fault is not None:
        raise ValueError(fault)
    outcome = OutcomeTable.model_validate(table)
    return outcome if outcome.has_words else outcome.pipe


def choice_value(*, option: ChoiceOptionValue) -> str:
    """The value an option declares, whichever form wrote it."""
    return option if isinstance(option, str) else option.value


def choice_values(*, options: Sequence[ChoiceOptionValue]) -> list[str]:
    """The values a `choices` list declares, in declared order."""
    return [choice_value(option=option) for option in options]


def options_carry_words(*, options: Sequence[ChoiceOptionValue]) -> bool:
    """Whether at least one option of a list carries a word: a label, a description or a tone."""
    return any(isinstance(option, ChoiceOption) and option.has_words for option in options)


def _malformed(*, message: str) -> ContractFactInvalidError:
    return ContractFactInvalidError(message, fact=CHOICES_KEY, reason=ContractFactReason.MALFORMED)


def presentation_words_fault(*, table: dict[str, Any], key_name: str, table_name: str) -> str | None:
    """Why a table's keys or words break the rules: a key other than `key_name` and the three words, or a word that is
    not a non-empty string or not a tone. `None` when they hold.
    """
    allowed = (key_name, *PRESENTATION_WORD_KEYS)
    unknown_keys = [key for key in table if key not in allowed]
    if unknown_keys:
        return f"{', '.join(repr(key) for key in unknown_keys)} is not a key of {table_name}: its keys are {', '.join(allowed)}"
    for word_key in ("label", "description"):
        if word_key in table and (not isinstance(table[word_key], str) or not table[word_key]):
            return f"the '{word_key}' of {table_name} must be a non-empty string, got {table[word_key]!r}"
    if "tone" in table and (not isinstance(table["tone"], str) or table["tone"] not in set(Tone)):
        return f"the 'tone' of {table_name} must be one of {', '.join(Tone)}, got {table['tone']!r}"
    return None


def parse_choices(*, raw: Any) -> Any:
    """Read an authored `choices` list into options in normal form, refusing a malformed option table.

    A table carrying `value` alone becomes its value's string. An option table is held to the full rules: a non-empty value
    no other option of the list holds, string or table, and no label another option carries. A string option keeps the
    leniency it always had, so a bundle that was valid stays valid: an empty string or two string options sharing a value is
    warned about as `method.choice_option_dubious`, never refused (`dubious_string_options`). A value that is not a list is
    returned untouched, for the field's own type to refuse.

    Raises:
        ContractFactInvalidError: For an empty list, a malformed option table, or an option table colliding with another option.
    """
    if not isinstance(raw, list):
        return raw
    authored = cast("list[Any]", raw)
    if not authored:
        msg = "'choices' must hold at least one option"
        raise _malformed(message=msg)
    options: list[ChoiceOptionValue] = []
    table_values: list[str] = []
    for raw_option in authored:
        if isinstance(raw_option, str):
            options.append(raw_option)
            continue
        if not isinstance(raw_option, dict):
            msg = f"an option of 'choices' must be a string or an option table, got {raw_option!r}"
            raise _malformed(message=msg)
        table = cast("dict[str, Any]", raw_option)
        if "value" not in table:
            msg = "an option table must carry its 'value'"
            raise _malformed(message=msg)
        option_value = table["value"]
        if not isinstance(option_value, str) or not option_value:
            msg = f"the 'value' of an option table must be a non-empty string, got {option_value!r}"
            raise _malformed(message=msg)
        fault = presentation_words_fault(table=table, key_name="value", table_name="an option table")
        if fault is not None:
            raise _malformed(message=fault)
        option = ChoiceOption.model_validate(table)
        table_values.append(option.value)
        options.append(option if option.has_words else option.value)
    all_values = choice_values(options=options)
    for table_value in table_values:
        if all_values.count(table_value) > 1:
            msg = f"an option table shares the value {table_value!r} with another option of its list"
            raise ContractFactInvalidError(msg, fact=CHOICES_KEY, reason=ContractFactReason.DUPLICATE_OPTION)
    duplicate_label = duplicate_option_message(values=[], labels=[option.label if isinstance(option, ChoiceOption) else None for option in options])
    if duplicate_label is not None:
        raise ContractFactInvalidError(duplicate_label, fact=CHOICES_KEY, reason=ContractFactReason.DUPLICATE_OPTION)
    return options


class DubiousOptionReason(StrEnum):
    """Why a string option is dubious: the reasons of `method.choice_option_dubious`."""

    EMPTY_VALUE = "empty_value"
    DUPLICATE_VALUE = "duplicate_value"


def dubious_string_options(*, options: Sequence[ChoiceOptionValue]) -> list[DubiousOptionReason]:
    """The dubious string options of a list, for a warning: an empty string option, and a string option repeating another's value.

    Each reason is given once per list. A table option's collisions are refused at parse time, so only string options are judged.
    """
    reasons: list[DubiousOptionReason] = []
    string_values = [option for option in options if isinstance(option, str)]
    if any(not value for value in string_values):
        reasons.append(DubiousOptionReason.EMPTY_VALUE)
    if len(set(string_values)) < len(string_values):
        reasons.append(DubiousOptionReason.DUPLICATE_VALUE)
    return reasons
