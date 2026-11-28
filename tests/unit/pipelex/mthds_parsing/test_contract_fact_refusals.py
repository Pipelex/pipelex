from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.mthds_parsing.validation_error_categorizer import categorize_blueprint_validation_error
from pipelex.validation_error_types import PipeValidationErrorType


def _structure_bundle(*, field_name: str, field: dict[str, Any]) -> dict[str, Any]:
    return {"domain": "demo", "concept": {"Review": {"description": "A review", "structure": {field_name: field}}}}


class TestContractFactRefusals:
    @pytest.mark.parametrize(
        ("field_name", "field", "fact", "field_path"),
        [
            ("score", {"type": "integer", "description": "x", "maximum": "ten"}, "maximum", "concept.Review.structure.score"),
            ("maximum", {"type": "integer", "description": "x", "maximum": "ten"}, "maximum", "concept.Review.structure.maximum"),
            ("format", {"type": "text", "description": "x", "format": "telex"}, "format", "concept.Review.structure.format"),
            ("mail", {"type": "text", "description": "x", "format": ["email"]}, "format", "concept.Review.structure.mail"),
            ("amount", {"type": "number", "description": "x", "aggregate": ["sum"]}, "aggregate", "concept.Review.structure.amount"),
            (
                "choices",
                {"description": "x", "choices": [{"value": "a", "tone": ["positive"]}]},
                "choices",
                "concept.Review.structure.choices",
            ),
        ],
    )
    def test_a_malformed_fact_is_a_typed_refusal_at_its_site(self, field_name: str, field: dict[str, Any], fact: str, field_path: str) -> None:
        """A fact of the wrong shape, a list included, is `contract_fact_invalid` at its field, even a field named like a fact."""
        blueprint_dict = _structure_bundle(field_name=field_name, field=field)
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint.model_validate(blueprint_dict)
        typed = [
            data
            for data in (categorize_blueprint_validation_error(error, blueprint_dict=blueprint_dict) for error in exc_info.value.errors())
            if data is not None and data.error_type is not None
        ]
        assert [(data.error_type, (data.params or {}).get("fact"), data.field_path) for data in typed] == [
            (PipeValidationErrorType.CONTRACT_FACT_INVALID, fact, field_path)
        ]
