from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint


class TestConceptUnit:
    @pytest.mark.parametrize(
        ("blueprint", "allowed"),
        [
            ({"refines": "Number"}, True),
            ({"refines": "native.Number"}, True),
            ({"structure": "NumberContent"}, True),
            ({"refines": "Amount"}, True),
            ({"refines": "Text"}, False),
            ({"structure": "TextContent"}, False),
            ({"structure": "SomeRegisteredClass"}, False),
            ({}, False),
        ],
    )
    def test_unit_needs_a_number_valued_concept(self, blueprint: dict[str, Any], allowed: bool) -> None:
        """`unit` is allowed on a concept refining Number or backed by its class, and on one refining a concept judged later."""
        authored = {"description": "An amount", "unit": "EUR", **blueprint}
        if allowed:
            assert ConceptBlueprint.model_validate(authored).unit == "EUR"
        else:
            with pytest.raises(ValidationError, match="'unit' is allowed only"):
                ConceptBlueprint.model_validate(authored)
