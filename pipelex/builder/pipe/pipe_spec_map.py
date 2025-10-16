from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec

pipe_type_to_spec_class: dict[str, type] = {
    "PipeFunc": PipeFuncSpec,
    "PipeImgGen": PipeImgGenSpec,
    "PipeCompose": PipeComposeSpec,
    "PipeLLM": PipeLLMSpec,
    "PipeExtract": PipeExtractSpec,
    "PipeBatch": PipeBatchSpec,
    "PipeCondition": PipeConditionSpec,
    "PipeParallel": PipeParallelSpec,
    "PipeSequence": PipeSequenceSpec,
}
