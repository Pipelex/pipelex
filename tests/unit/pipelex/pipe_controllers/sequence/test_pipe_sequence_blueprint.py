import pytest
from pydantic import ValidationError

from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestPipeSequenceBlueprint:
    def test_pipe_dependencies_correct(self):
        blueprint = PipeSequenceBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
            ],
        )
        assert blueprint.pipe_dependencies == {"step1", "step2"}

        blueprint = PipeSequenceBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="process_a", result="result_a"),
                SubPipeBlueprint(pipe="process_b", result="result_b"),
                SubPipeBlueprint(pipe="process_c", result="result_c"),
            ],
        )
        assert blueprint.pipe_dependencies == {"process_a", "process_b", "process_c"}

    def test_ordered_pipe_dependencies_correct(self):
        blueprint = PipeSequenceBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="result3"),
            ],
        )
        assert blueprint.ordered_pipe_dependencies == ["step1", "step2", "step3"]

        blueprint = PipeSequenceBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="first", result="first_result"),
                SubPipeBlueprint(pipe="second", result="second_result"),
            ],
        )
        assert blueprint.ordered_pipe_dependencies == ["first", "second"]

    def test_validate_steps_correct(self):
        blueprint = PipeSequenceBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            steps=[SubPipeBlueprint(pipe="step1", result="result1")],
        )
        assert len(blueprint.steps) == 1

        blueprint = PipeSequenceBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
            ],
        )
        assert len(blueprint.steps) == 2

    def test_validate_steps_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeSequenceBlueprint(
                description="lorem ipsum",
                inputs={"data": "Text"},
                output="Text",
                steps=[],
            )
        assert "PipeSequence must have at least 1 step" in str(exc_info.value)
