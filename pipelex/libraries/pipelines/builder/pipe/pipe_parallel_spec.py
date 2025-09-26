from typing import Literal

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint


class PipeParallelSpec(PipeSpec):
    """Spec for parallel pipe execution in the Pipelex framework.

    PipeParallel enables concurrent execution of multiple pipes, improving performance
    for independent operations. All parallel pipes receive the same input context
    and their outputs can be combined or kept separate.

    Attributes:
        the_pipe_code: Pipe code. Must be snake_case.
        type: Fixed to "PipeParallel" for this pipe type.
        parallels: List of SubPipeSpec instances to execute concurrently.
                  All pipes run simultaneously with access to the same input context.
        add_each_output: Whether to include individual pipe outputs in the combined
                        result. Default is True. When False, only combined_output is used.
        combined_output: Optional concept string/code for the combined output structure.
                        When specified, all parallel outputs are merged into this concept.

    Validation Rules:
        1. Parallels list must not be empty.
        2. Each parallel step must be a valid SubPipeSpec.
        3. combined_output, when specified, must be a valid concept string or code.
        4. Pipe codes in parallels must reference existing pipes.

    """

    type: Literal["PipeParallel"] = "PipeParallel"
    category: Literal["PipeController"] = "PipeController"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    parallels: list[SubPipeSpec]
    add_each_output: bool = True
    combined_output: str | None = None

    @field_validator("combined_output", mode="before")
    @staticmethod
    def validate_combined_output(combined_output: str) -> str:
        if combined_output:
            ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=combined_output)
        return combined_output

    @override
    def to_blueprint(self) -> PipeParallelBlueprint:
        base_blueprint = super().to_blueprint()
        core_parallels = [parallel.to_blueprint() for parallel in self.parallels]
        return PipeParallelBlueprint(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            parallels=core_parallels,
            add_each_output=self.add_each_output,
            combined_output=self.combined_output,
        )
