from typing import Any

import pytest

from pipelex.language.contract_facts import (
    ContractFactKey,
    ContractFactReason,
    TextFormat,
    ValueClass,
    applicability_findings,
    constraint_break_message,
    contradiction_findings,
    format_sample,
    is_unit_identifier,
    text_matches_format,
)


class TestContractFacts:
    @pytest.mark.parametrize(
        ("unit", "known"),
        [("EUR", True), ("XYZ", True), ("percent", True), ("m", True), ("kg", True), ("eur", False), ("pounds", False), ("", False)],
    )
    def test_unit_identifiers(self, unit: str, known: bool) -> None:
        """A currency is three uppercase letters, known or not; the units of measure are a closed list."""
        assert is_unit_identifier(unit=unit) is known

    @pytest.mark.parametrize("text_format", list(TextFormat))
    def test_every_format_sample_is_well_formed(self, text_format: TextFormat) -> None:
        """The dry run's sample of a format satisfies that format, so a mock never breaks its own field."""
        assert text_matches_format(text=format_sample(text_format=text_format), text_format=text_format)

    @pytest.mark.parametrize(
        ("facts", "is_integer", "fact", "reason"),
        [
            ({"minimum": 5, "maximum": 1}, False, ContractFactKey.MAXIMUM, ContractFactReason.CONTRADICTORY),
            ({"minimum": 0, "exclusive_minimum": 0}, False, ContractFactKey.EXCLUSIVE_MINIMUM, ContractFactReason.CONTRADICTORY),
            ({"min_length": 10, "max_length": 5}, False, ContractFactKey.MIN_LENGTH, ContractFactReason.CONTRADICTORY),
            ({"exclusive_minimum": 2, "exclusive_maximum": 3}, True, ContractFactKey.EXCLUSIVE_MAXIMUM, ContractFactReason.CONTRADICTORY),
        ],
    )
    def test_contradictions(self, facts: dict[str, Any], is_integer: bool, fact: ContractFactKey, reason: ContractFactReason) -> None:
        findings = contradiction_findings(facts=facts, is_integer=is_integer)
        assert [(finding.fact, finding.reason) for finding in findings][:1] == [(fact, reason)]

    @pytest.mark.parametrize(
        ("facts", "value_class", "is_slot", "has_choices", "reason"),
        [
            ({"minimum": 1}, ValueClass.TEXT, False, False, ContractFactReason.INAPPLICABLE),
            ({"max_length": 3}, ValueClass.NUMBER, False, False, ContractFactReason.INAPPLICABLE),
            ({"max_length": 80}, None, True, False, ContractFactReason.NOT_VALUE_SLOT),
            ({"aggregate": "sum"}, ValueClass.NUMBER, True, False, ContractFactReason.INAPPLICABLE),
            ({"examples": ["x"]}, ValueClass.TEXT, True, True, ContractFactReason.INAPPLICABLE),
            ({}, ValueClass.NUMBER, True, True, ContractFactReason.INAPPLICABLE),
        ],
    )
    def test_applicability(
        self, facts: dict[str, Any], value_class: ValueClass | None, is_slot: bool, has_choices: bool, reason: ContractFactReason
    ) -> None:
        findings = applicability_findings(facts=facts, value_class=value_class, is_slot=is_slot, has_choices=has_choices)
        assert findings
        assert findings[0].reason == reason

    @pytest.mark.parametrize(
        ("value", "facts", "breaks"),
        [
            (9, {"maximum": 5}, "above the maximum"),
            (0, {"exclusive_minimum": 0}, "not above the exclusive minimum"),
            ("ab", {"min_length": 3}, "fewer than 3 characters"),
            ("order PO-123 sent", {"pattern": "PO-[0-9]{3}"}, None),
            ("PO-12", {"pattern": "^PO-[0-9]{3}$"}, "does not match the pattern"),
            ("nope", {"format": "email"}, "not well-formed as email"),
            (3, {"maximum": 5, "unit": "EUR"}, None),
        ],
    )
    def test_constraint_breaks(self, value: Any, facts: dict[str, Any], breaks: str | None) -> None:
        """A pattern is searched, as JSON Schema does, and a description never refuses a value."""
        message = constraint_break_message(value=value, facts=facts)
        if breaks is None:
            assert message is None
        else:
            assert message is not None
            assert breaks in message
