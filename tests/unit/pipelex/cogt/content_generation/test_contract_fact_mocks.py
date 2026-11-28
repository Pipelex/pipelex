from typing import Any

import pytest
from pydantic import create_model

from pipelex.cogt.content_generation.contract_fact_mocks import MAX_MOCK_TEXT_LENGTH, mock_text
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.core.concepts.contract_fact_projection import constrained_annotation
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.language.contract_facts import constraint_break_message

_BUILDS = 40


class TestContractFactMocks:
    @pytest.mark.parametrize(
        ("annotation", "facts", "states_schema", "optional"),
        [
            pytest.param(NumberContent, {"minimum": 0, "maximum": 10}, False, False, id="concept-number-range"),
            pytest.param(NumberContent, {"exclusive_minimum": 0, "exclusive_maximum": 1}, False, False, id="concept-number-open-range"),
            pytest.param(NumberContent, {"minimum": 1000}, False, True, id="concept-number-lower-bound-optional"),
            pytest.param(TextContent, {"pattern": "^PO-[0-9]{3}$"}, False, False, id="concept-text-pattern"),
            pytest.param(TextContent, {"format": "email", "max_length": 12}, False, False, id="concept-text-email-short"),
            pytest.param(str, {"format": "email"}, True, False, id="text-email"),
            pytest.param(str, {"format": "email", "max_length": 10}, True, False, id="text-email-max-length"),
            pytest.param(str, {"format": "email", "pattern": "@corp\\.com$"}, True, True, id="text-email-pattern-optional"),
            pytest.param(str, {"format": "uri", "max_length": 14}, True, False, id="text-uri-max-length"),
            pytest.param(TextContent, {"max_length": 3}, False, False, id="concept-text-max-length-below-the-plain-mock"),
            pytest.param(TextContent, {"pattern": "^[A-Z]", "min_length": 10}, False, False, id="concept-text-pattern-min-length"),
            pytest.param(str, {"pattern": "[0-9]$", "min_length": 12, "max_length": 12}, True, False, id="text-pattern-exact-length"),
            pytest.param(str, {"min_length": 50_000}, True, False, id="text-long-min-length"),
            pytest.param(
                NumberContent,
                {"minimum": 9007199254740993, "examples": [9007199254740993]},
                False,
                False,
                id="concept-number-integer-example-past-float-precision",
            ),
            pytest.param(
                NumberContent,
                {"minimum": 9007199254740993, "maximum": 9007199254740993},
                False,
                False,
                id="concept-number-one-integer-past-float-precision",
            ),
            pytest.param(NumberContent, {"exclusive_minimum": 9007199254740993}, False, False, id="concept-number-exclusive-integer-bound"),
            pytest.param(TextContent, {"pattern": "^(?>a|ab)c$"}, False, False, id="concept-text-atomic-group"),
            pytest.param(str, {"pattern": "^a++b$"}, True, False, id="text-possessive-repeat"),
            pytest.param(str, {"pattern": "^x(?>[0-9]{2})*+y$"}, True, False, id="text-atomic-and-possessive"),
            pytest.param(str, {"pattern": "^(a)?(?(1)b|c)$", "examples": ["ab"]}, True, False, id="text-conditional-with-example"),
        ],
    )
    def test_every_mock_honours_the_facts(self, annotation: Any, facts: dict[str, Any], states_schema: bool, optional: bool) -> None:
        """A dry-run mock of a concept-typed or format-asserting field satisfies every fact, build after build."""
        constrained = constrained_annotation(annotation=annotation, facts=facts, states_schema=states_schema)
        field_type: Any = constrained | None if optional else constrained
        model = create_model("FactsMockModel", __base__=StructuredContent, value=(field_type, ...))
        factory = DryRunFactory.make_dry_run_factory(model)
        for _ in range(_BUILDS):
            built = factory.build().model_dump()["value"]
            plain = built["number"] if annotation is NumberContent else built["text"] if annotation is TextContent else built
            assert constraint_break_message(value=plain, facts=facts) is None, plain

    @pytest.mark.parametrize(
        ("annotation", "states_schema"),
        [pytest.param(str, True, id="text"), pytest.param(TextContent, False, id="concept-text")],
    )
    def test_a_mock_never_passes_the_size_bound(self, annotation: Any, states_schema: bool) -> None:
        """A `min_length` past the bound leaves the site without an honouring mock rather than allocating its size: the
        mock holds at most `MAX_MOCK_TEXT_LENGTH` characters, and validation refuses it as for any site no mock satisfies.
        """
        facts = {"min_length": 10**9}
        assert len(mock_text(facts=facts)) == MAX_MOCK_TEXT_LENGTH
        constrained = constrained_annotation(annotation=annotation, facts=facts, states_schema=states_schema)
        model = create_model("FactsMockModel", __base__=StructuredContent, value=(constrained, ...))
        with pytest.raises(ValueError, match=r"fewer than|at least"):
            DryRunFactory.make_dry_run_factory(model).build()

    @pytest.mark.parametrize(
        "pattern",
        [
            pytest.param("(a)?(?(1)b|c)", id="conditional"),
            pytest.param("^(?>a|ab)c$", id="atomic-group"),
            pytest.param("^a++b$", id="possessive-repeat"),
        ],
    )
    def test_a_pattern_the_generator_cannot_read_never_crashes_the_mock(self, pattern: str) -> None:
        """The runtime searches patterns the regex generator cannot draw from: the mock still comes back, as a text."""
        assert isinstance(mock_text(facts={"pattern": pattern}), str)
