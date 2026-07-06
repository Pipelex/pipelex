import pytest
from pydantic import ValidationError

from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestPipeParallelBlueprint:
    def test_pipe_dependencies_correct(self):
        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Composite",
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
            output="Composite",
            branches=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="result3"),
            ],
            add_each_output=True,
        )
        assert blueprint.pipe_dependencies == {"step1", "step2", "step3"}

    @pytest.mark.parametrize("output", ["Composite", "native.Composite", "MergedData", "some_domain.MergedData"])
    def test_valid_outputs_accepted(self, output: str):
        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output=output,
            branches=[SubPipeBlueprint(pipe="process", result="result")],
        )
        assert blueprint.output == output

    @pytest.mark.parametrize("output", ["Text", "native.Text", "Image", "Number", "Dynamic", "Anything"])
    def test_native_non_composite_output_rejected(self, output: str):
        with pytest.raises(ValidationError, match="must be 'Composite' or a structured concept"):
            PipeParallelBlueprint(
                description="lorem ipsum",
                inputs={"data": "Text"},
                output=output,
                branches=[SubPipeBlueprint(pipe="process", result="result")],
            )

    @pytest.mark.parametrize("output", ["Composite[]", "MergedData[]", "MergedData[3]"])
    def test_multiplicity_output_rejected(self, output: str):
        with pytest.raises(ValidationError, match="must not declare a multiplicity"):
            PipeParallelBlueprint(
                description="lorem ipsum",
                inputs={"data": "Text"},
                output=output,
                branches=[SubPipeBlueprint(pipe="process", result="result")],
            )

    def test_add_each_output_defaults_to_false_and_is_valid_alone(self):
        """The one-of-two (add_each_output/combined_output) validator is gone: a parallel
        always combines into its declared output, so no extra flag is required.
        """
        blueprint = PipeParallelBlueprint(
            description="lorem ipsum",
            inputs={"data": "Text"},
            output="Composite",
            branches=[SubPipeBlueprint(pipe="process", result="result")],
        )
        assert blueprint.add_each_output is False

    def test_combined_output_field_is_gone(self):
        """combined_output was deleted from the language: passing it must be rejected."""
        with pytest.raises(ValidationError):
            PipeParallelBlueprint.model_validate(
                {
                    "description": "lorem ipsum",
                    "inputs": {"data": "Text"},
                    "output": "Composite",
                    "branches": [{"pipe": "process", "result": "result"}],
                    "combined_output": "Composite",
                }
            )
