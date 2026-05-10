from typing import Callable

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestPipeStructureValidateInputs:
    def test_non_text_input_raises_input_stuff_spec_mismatch(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """The single input is present but its concept is not Text-compatible.

        The error must be classified as INPUT_STUFF_SPEC_MISMATCH (the spec doesn't match),
        not MISSING_INPUT_VARIABLE (which would lie — the variable IS there).
        """
        load_empty_library()
        blueprint = PipeStructureBlueprint(
            description="Structure draft text",
            inputs={"draft_text": "native.Image"},
            output="native.Number",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="struct_with_image_input",
            blueprint=blueprint,
        )

        with pytest.raises(PipeValidationError) as exc_info:
            pipe_structure.validate_inputs_with_library()
        assert exc_info.value.error_type == PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
        assert exc_info.value.provided_concept_code == "native.Image"
