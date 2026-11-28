from typing import Any

import pytest
from pydantic import create_model

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
