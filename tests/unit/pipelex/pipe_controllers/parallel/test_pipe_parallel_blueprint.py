import pytest
from pydantic import ValidationError

from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestPipeParallelBlueprint:
    def test_pipe_dependencies_correct(self):
        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[
                SubPipeBlueprint(pipe="process_a", result="result_a"),
                SubPipeBlueprint(pipe="process_b", result="result_b"),
            ],
            add_each_output=True,
        )
        assert blueprint.pipe_dependencies == {"process_a", "process_b"}

        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="result3"),
            ],
            add_each_output=True,
        )
        assert blueprint.pipe_dependencies == {"step1", "step2", "step3"}

    def test_validate_combined_output_correct(self):
        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[SubPipeBlueprint(pipe="process", result="result")],
            combined_output="Text",
        )
        assert blueprint.combined_output == "Text"

        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[SubPipeBlueprint(pipe="process", result="result")],
            combined_output="Number",
        )
        assert blueprint.combined_output == "Number"

    def test_validate_combined_output_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeParallelBlueprint(
                description="lorem ipsum",
                inputs={"data": "Text"},
                output="Text",
                branches=[SubPipeBlueprint(pipe="process", result="result")],
                combined_output="InvalidConcept!",
            )
        assert "Combined output 'InvalidConcept!' is not a valid concept string or code" in str(exc_info.value)

    def test_validate_output_options_correct(self):
        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[SubPipeBlueprint(pipe="process", result="result")],
            add_each_output=True,
        )
        assert blueprint.add_each_output is True

        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[SubPipeBlueprint(pipe="process", result="result")],
            combined_output="Text",
        )
        assert blueprint.combined_output == "Text"

        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Text",
            branches=[SubPipeBlueprint(pipe="process", result="result")],
            add_each_output=True,
            combined_output="Text",
        )
        assert blueprint.add_each_output is True
        assert blueprint.combined_output == "Text"

    def test_validate_output_options_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeParallelBlueprint(
                description="lorem ipsum",
                inputs={"data": "Text"},
                output="Text",
                branches=[SubPipeBlueprint(pipe="process", result="result")],
                add_each_output=False,
                combined_output=None,
            )
        assert "PipeParallel requires either add_each_output to be True or combined_output to be set" in str(exc_info.value)
