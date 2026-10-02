from typing import Any

import pytest

from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.validation_error_types import PipeValidationErrorType
from tests.unit.pipelex.pipe_operators.input_check_helpers import refused_input_error
from tests.unit.pipelex.pipe_operators.pipe_compose.data import PipeComposeInputCheckTestCases


class TestPipeComposeBlueprintInputCheck:
    @pytest.mark.parametrize(
        ("test_id", "blueprint_kwargs", "expected_error_type", "expected_variable_names"),
        PipeComposeInputCheckTestCases.REFUSED_CASES,
    )
    def test_refused(
        self,
        test_id: str,
        blueprint_kwargs: dict[str, Any],
        expected_error_type: PipeValidationErrorType,
        expected_variable_names: list[str],
    ):
        error = refused_input_error(blueprint_class=PipeComposeBlueprint, blueprint_kwargs=blueprint_kwargs)
        assert error.error_type == expected_error_type, test_id
        assert error.variable_names == expected_variable_names, test_id

    @pytest.mark.parametrize(
        ("test_id", "blueprint_kwargs"),
        PipeComposeInputCheckTestCases.ACCEPTED_CASES,
    )
    def test_accepted(self, test_id: str, blueprint_kwargs: dict[str, Any]):
        blueprint = PipeComposeBlueprint.model_validate(blueprint_kwargs)
        assert set(blueprint.input_names) == set(blueprint_kwargs["inputs"]), test_id

    def test_unread_input_message_names_both_remedies(self):
        error = refused_input_error(
            blueprint_class=PipeComposeBlueprint,
            blueprint_kwargs=PipeComposeInputCheckTestCases.REFUSED_TEMPLATE_ONE_UNREAD[1],
        )
        message = str(error)
        assert "'unused'" in message
        assert "Reference it in the template" in message
        assert "remove it from `inputs`" in message
