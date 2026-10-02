from typing import Any

import pytest

from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.validation_error_types import PipeValidationErrorType
from tests.unit.pipelex.pipe_operators.input_check_helpers import refused_input_error
from tests.unit.pipelex.pipe_operators.pipe_search.data import PipeSearchInputCheckTestCases


class TestPipeSearchBlueprintInputCheck:
    @pytest.mark.parametrize(
        ("test_id", "blueprint_kwargs", "expected_error_type", "expected_variable_names"),
        PipeSearchInputCheckTestCases.REFUSED_CASES,
    )
    def test_refused(
        self,
        test_id: str,
        blueprint_kwargs: dict[str, Any],
        expected_error_type: PipeValidationErrorType,
        expected_variable_names: list[str],
    ):
        error = refused_input_error(blueprint_class=PipeSearchBlueprint, blueprint_kwargs=blueprint_kwargs)
        assert error.error_type == expected_error_type, test_id
        assert error.variable_names == expected_variable_names, test_id

    @pytest.mark.parametrize(
        ("test_id", "blueprint_kwargs"),
        PipeSearchInputCheckTestCases.ACCEPTED_CASES,
    )
    def test_accepted(self, test_id: str, blueprint_kwargs: dict[str, Any]):
        blueprint = PipeSearchBlueprint.model_validate(blueprint_kwargs)
        assert set(blueprint.input_names) == set(blueprint_kwargs.get("inputs") or {}), test_id
