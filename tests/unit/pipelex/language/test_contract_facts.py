import time
from typing import Any

import pytest

from pipelex.language.contract_facts import (
    MAX_PATTERN_EXPANDED_POSITIONS,
    PATTERN_SEARCH_TIMEOUT_SECONDS,
    ContractFactKey,
    ContractFactReason,
    FactSiteType,
    ValueClass,
    ValueFormat,
    applicability_findings,
    constraint_break_message,
    contradiction_findings,
    format_sample,
    is_unit_identifier,
    malformed_fact_message,
    pattern_expanded_positions,
    text_matches_format,
    value_findings,
)


class TestContractFacts:
    @pytest.mark.parametrize(
        ("unit", "known"),
        [("EUR", True), ("XYZ", True), ("percent", True), ("m", True), ("kg", True), ("eur", False), ("pounds", False), ("", False)],
    )
    def test_unit_identifiers(self, unit: str, known: bool) -> None:
        """A currency is three uppercase letters, known or not; the units of measure are a closed list."""
        assert is_unit_identifier(unit=unit) is known

    @pytest.mark.parametrize("text_format", list(ValueFormat))
    def test_every_format_sample_is_well_formed(self, text_format: ValueFormat) -> None:
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

    @pytest.mark.parametrize(
        ("facts", "site_type", "default_value", "fact"),
        [
            ({"minimum": 0, "maximum": 10}, FactSiteType.NUMBER, 20, ContractFactKey.MAXIMUM),
            ({"minimum": 0, "maximum": 10}, FactSiteType.NUMBER, -1, ContractFactKey.MINIMUM),
            ({"min_length": 1, "pattern": "^a"}, FactSiteType.TEXT, "bcd", ContractFactKey.PATTERN),
            ({"min_length": 4, "pattern": "^a"}, FactSiteType.TEXT, "abc", ContractFactKey.MIN_LENGTH),
            ({"max_length": 20, "format": "email"}, FactSiteType.TEXT, "nope", ContractFactKey.FORMAT),
        ],
    )
    def test_a_refused_default_names_the_constraint_it_breaks(
        self, facts: dict[str, Any], site_type: FactSiteType, default_value: Any, fact: ContractFactKey
    ) -> None:
        """The fact named is the one the default breaks, never merely the first constraint declared."""
        findings = value_findings(facts=facts, site_type=site_type, default_value=default_value)
        assert [(finding.fact, finding.reason) for finding in findings] == [(fact, ContractFactReason.VALUE_BREAKS_CONTRACT)]

    def test_a_catastrophic_pattern_is_stopped_and_refuses_the_value(self) -> None:
        """A pattern that backtracks without bound is searched with a time limit: the value is refused, never let through,
        and the search returns within a small multiple of the limit rather than doubling with each character.
        """
        started = time.perf_counter()
        message = constraint_break_message(value="a" * 40 + "!", facts={"pattern": "^(a|aa)+$"})
        elapsed = time.perf_counter() - started
        assert message is not None
        assert "could not be checked against the pattern" in message
        assert elapsed < 20 * PATTERN_SEARCH_TIMEOUT_SECONDS

    def test_a_pattern_overrunning_on_its_own_example_is_refused_as_malformed(self) -> None:
        """An example the pattern cannot be searched in within the limit refuses the pattern, the fact to rewrite."""
        findings = value_findings(facts={"pattern": "^(a|aa)+$", "examples": ["a" * 40 + "!"]}, site_type=FactSiteType.TEXT)
        assert [(finding.fact, finding.reason) for finding in findings] == [(ContractFactKey.PATTERN, ContractFactReason.MALFORMED)]

    @pytest.mark.parametrize(
        ("pattern", "positions"),
        [
            ("^PO-[0-9]{6}$", 11),
            ("[A-Za-z0-9+/]{4000}", 4000),
            ("(?:ab){50}", 100),
            ("((a{10}){10}){10}", 1000),
            ("x{0,1000000}", 1),
            (r"\{5000}", 6),
        ],
    )
    def test_expanded_positions(self, pattern: str, positions: int) -> None:
        """Counted repetitions are written out at their lower counts, nested ones multiplied; a group prefix holds none."""
        assert pattern_expanded_positions(pattern=pattern) == positions

    @pytest.mark.parametrize("pattern", ["a{100000000}", "(ab){1000000}", "((a{100}){100}){2}"])
    def test_a_pattern_writing_out_past_the_bound_is_malformed(self, pattern: str) -> None:
        """A pattern whose counted repetitions write out past the bound is refused before the search engine compiles it,
        which would hold memory and time in proportion to the counts.
        """
        started = time.perf_counter()
        message = malformed_fact_message(key=ContractFactKey.PATTERN, value=pattern)
        assert time.perf_counter() - started < 1.0
        assert message is not None
        assert str(MAX_PATTERN_EXPANDED_POSITIONS) in message

    @pytest.mark.parametrize(
        ("value", "facts"),
        [
            ("x" * 100_000, {"max_length": 3}),
            ("x" * 100_000, {"pattern": "^y"}),
            # No constraint: the long value is judged as an `examples` fact that is not an array.
            ("x" * 100_000, {}),
        ],
    )
    def test_a_refusal_quotes_a_long_value_cut_short(self, value: Any, facts: dict[str, Any]) -> None:
        """A refusal never carries a whole long value, which may be a stored text a caller would not see logged."""
        message = constraint_break_message(value=value, facts=facts) or malformed_fact_message(key=ContractFactKey.EXAMPLES, value=value)
        assert message is not None
        assert len(message) < 300
