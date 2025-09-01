from typing import Dict, Union

from pydantic import Field

from pipelex.core.pipes.pipe_blueprint import AllowedPipeTypes
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint as PipeBlueprintBaseModel
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.concept.concept import ConceptSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint as PipeBatchBlueprintBaseModel
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint as PipeConditionBlueprintBaseModel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint as PipeParallelBlueprintBaseModel
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint as PipeSequenceBlueprintBaseModel
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint as PipeFuncBlueprintBaseModel
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint as PipeImgGenBlueprintBaseModel
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint as PipeJinja2BlueprintBaseModel
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint as PipeLLMBlueprintBaseModel
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint as PipeOcrBlueprintBaseModel


class PipeSignature(StructuredContent):
    code: str = Field(description="Pipe code. Must be snake_case.")
    type: AllowedPipeTypes = Field(description="Pipe type.")
    definition: str = Field(description="What the pipe does")
    inputs: Dict[str, ConceptSpec] = Field(description="Pipe inputs: key is the concept code in pascal Case.")
    output: ConceptSpec = Field(description="Concept as output")


class PipeBlueprint(PipeBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeBatchBlueprint(PipeBatchBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeConditionBlueprint(PipeConditionBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeParallelBlueprint(PipeParallelBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeSequenceBlueprint(PipeSequenceBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeFuncBlueprint(PipeFuncBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeLLMBlueprint(PipeLLMBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeOcrBlueprint(PipeOcrBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeImgGenBlueprint(PipeImgGenBlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


class PipeJinja2Blueprint(PipeJinja2BlueprintBaseModel, StructuredContent):
    pipe_code: str = Field(description="Pipe code. Must be snake_case.")


PipeBlueprintUnion = Union[
    PipeBatchBlueprint,
    PipeConditionBlueprint,
    PipeParallelBlueprint,
    PipeSequenceBlueprint,
    PipeFuncBlueprint,
    PipeLLMBlueprint,
    PipeOcrBlueprint,
    PipeImgGenBlueprint,
    PipeJinja2Blueprint,
]
