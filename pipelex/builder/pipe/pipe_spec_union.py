from typing import Annotated

from pydantic import Field

from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_search_spec import PipeSearchSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_signature_spec import PipeSignatureSpec
from pipelex.builder.pipe.pipe_structure_spec import PipeStructureSpec

PipeSpecUnion = Annotated[
    PipeFuncSpec
    | PipeImgGenSpec
    | PipeComposeSpec
    | PipeLLMSpec
    | PipeExtractSpec
    | PipeSearchSpec
    | PipeStructureSpec
    | PipeBatchSpec
    | PipeConditionSpec
    | PipeParallelSpec
    | PipeSequenceSpec
    | PipeSignatureSpec,
    Field(discriminator="type"),
]
