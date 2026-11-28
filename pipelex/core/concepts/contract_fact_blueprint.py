"""The contract-fact keys a structure field and an input slot both carry, declared once.

A structure field and an expanded input slot take the same contract facts (spec: `mthds-format.md`, "Contract Facts" and
"Input slot declarations"), so both blueprints inherit them from `ContractFactsBlueprint`: the eleven keys, each optional,
and the check that refuses a value breaking its key's own rules (`malformed`) before pydantic reads its type. Whether a key
applies where it is written, and whether two contradict each other, is judged by each blueprint, which knows its site.

Every key a site does not author is an absent member, never `null`, so a library that authors none keeps the fingerprint it
had before contract facts existed (`drop_absent_members`).
"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field, StrictFloat, StrictInt, ValidationInfo, field_validator

from pipelex.core.concepts.exceptions import ContractFactInvalidError
from pipelex.language.contract_facts import (
    CONTRACT_FACT_KEY_NAMES,
    Aggregate,
    ContractFactFinding,
    ContractFactKey,
    ContractFactReason,
    ValueFormat,
    authored_facts,
    malformed_fact_message,
)


def raise_first_finding(*, findings: Iterable[ContractFactFinding]) -> None:
    """Raise the first finding as the error its site's validator reports, or nothing when there is none."""
    for finding in findings:
        raise ContractFactInvalidError(finding.message, fact=finding.fact, reason=finding.reason)


def drop_absent_members(*, dumped: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    """Drop the members among `keys` a dump holds as `null`: an absent fact is an absent member."""
    for key in keys:
        if key in dumped and dumped[key] is None:
            del dumped[key]
    return dumped


class ContractFactsBlueprint(BaseModel):
    """The contract-fact keys of a site: bounds and lengths, a pattern and a format, a unit, an aggregate and examples."""

    minimum: StrictInt | StrictFloat | None = None
    """Inclusive lower bound of a number-valued site."""
    maximum: StrictInt | StrictFloat | None = None
    """Inclusive upper bound of a number-valued site."""
    exclusive_minimum: StrictInt | StrictFloat | None = None
    """Exclusive lower bound of a number-valued site."""
    exclusive_maximum: StrictInt | StrictFloat | None = None
    """Exclusive upper bound of a number-valued site."""
    min_length: StrictInt | None = Field(default=None, ge=0)
    """The fewest characters a text-valued site holds, counted in Unicode code points."""
    max_length: StrictInt | None = Field(default=None, ge=0)
    """The most characters a text-valued site holds, counted in Unicode code points."""
    pattern: str | None = None
    """A regular expression a text-valued site matches, anywhere unless anchored."""
    format: ValueFormat | None = Field(default=None, strict=False)
    """The format a text-valued site is well-formed in."""
    unit: str | None = None
    """What a number-valued site counts: an ISO 4217 currency code, `percent`, or a unit of measure."""
    aggregate: Aggregate | None = Field(default=None, strict=False)
    """How the values of a number-valued field combine across records. Never on an input slot."""
    examples: list[Any] | None = None
    """Examples of a good value, each written as the value itself."""

    @field_validator(*CONTRACT_FACT_KEY_NAMES, mode="before")
    @classmethod
    def refuse_malformed_fact(cls, value: Any, info: ValidationInfo) -> Any:
        """Refuse a fact whose own value breaks its key's rules, as `malformed`, before its type is read."""
        if value is None:
            return value
        key = ContractFactKey(str(info.field_name))
        message = malformed_fact_message(key=key, value=value)
        if message is not None:
            raise ContractFactInvalidError(message, fact=key, reason=ContractFactReason.MALFORMED)
        return value

    @property
    def contract_facts(self) -> dict[str, Any]:
        """The facts this site authors, by key in the standard's order, as plain values: a format or an aggregate as its string."""
        return authored_facts(values={key: _plain(value=getattr(self, key)) for key in CONTRACT_FACT_KEY_NAMES})


def _plain(*, value: Any) -> Any:
    """A fact's value as plain data, a `StrEnum` member as its string."""
    if isinstance(value, (ValueFormat, Aggregate)):
        return str(value)
    return value
