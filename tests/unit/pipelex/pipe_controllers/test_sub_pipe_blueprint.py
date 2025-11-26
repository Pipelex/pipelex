import pytest
from pydantic import ValidationError

from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestSubPipeBlueprint:
    def test_validate_multiple_output_correct(self):
        blueprint = SubPipeBlueprint(pipe="process")
        assert blueprint.pipe == "process"
        assert blueprint.nb_output is None
        assert blueprint.multiple_output is None

        blueprint = SubPipeBlueprint(pipe="process", nb_output=3)
        assert blueprint.nb_output == 3
        assert blueprint.multiple_output is None

        blueprint = SubPipeBlueprint(pipe="process", multiple_output=True)
        assert blueprint.nb_output is None
        assert blueprint.multiple_output is True

    def test_validate_multiple_output_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                nb_output=3,
                multiple_output=True,
            )
        assert "PipeStepBlueprint should have no more than '1' of nb_output or multiple_output" in str(exc_info.value)

    def test_validate_batch_params_correct(self):
        blueprint = SubPipeBlueprint(pipe="process")
        assert blueprint.batch_over is None
        assert blueprint.batch_as is None

        blueprint = SubPipeBlueprint(
            pipe="process",
            batch_over="items",
            batch_as="item",
        )
        assert blueprint.batch_over == "items"
        assert blueprint.batch_as == "item"

    def test_validate_batch_params_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                batch_over="items",
            )
        assert "When 'batch_over' is specified, 'batch_as' must also be provided" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                batch_as="item",
            )
        assert "When 'batch_as' is specified, 'batch_over' must also be provided" in str(exc_info.value)
