from typing import Literal

from pydantic import field_validator, model_validator
from typing_extensions import override

from pipelex.core.concepts.validation import is_concept_ref_or_code_valid
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.types import Self


class PipeParallelBlueprint(PipeBlueprint):
    type: Literal["PipeParallel"] = "PipeParallel"
    pipe_category: Literal["PipeController"] = "PipeController"
    parallels: list[SubPipeBlueprint]
    add_each_output: bool = False
    combined_output: str | None = None

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from the parallel branches."""
        return {parallel.pipe for parallel in self.parallels}

    @field_validator("combined_output", mode="before")
    @classmethod
    def validate_combined_output(cls, combined_output: str) -> str:
        if combined_output:
            if not is_concept_ref_or_code_valid(concept_ref_or_code=combined_output):
                msg = f"Combined output '{combined_output}' is not a valid concept string or code"
                raise ValueError(msg)
        return combined_output

    @model_validator(mode="after")
    def validate_output_options(self) -> Self:
        if not self.add_each_output and not self.combined_output:
            msg = (
                "PipeParallel requires either add_each_output to be True or combined_output to be set, "
                "or both, otherwise the pipe won't output anything"
            )
            raise ValueError(msg)
        return self

    @override
    def validate_inputs(self):
        pass

    @override
    def validate_output(self):
        pass
