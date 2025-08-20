from typing import Any, ClassVar, List

from pipelex.core.pipes.pipe_abstract import PipeAbstractType
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import (
    DynamicContent,
    HtmlContent,
    ImageContent,
    ListContent,
    LLMPromptContent,
    NumberContent,
    PageContent,
    PDFContent,
    StructuredContent,
    StuffContent,
    TextAndImagesContent,
    TextContent,
)
from pipelex.libraries.pipelines.meta.pipeline_draft import PipelexBundleBlueprint, PipelineDraft
from pipelex.pipe_controllers.pipe_batch import PipeBatch
from pipelex.pipe_controllers.pipe_batch_factory import PipeBatchFactory
from pipelex.pipe_controllers.pipe_condition import PipeCondition
from pipelex.pipe_controllers.pipe_condition_factory import PipeConditionFactory
from pipelex.pipe_controllers.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.pipe_parallel_factory import PipeParallelFactory
from pipelex.pipe_controllers.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.pipe_sequence_factory import PipeSequenceFactory
from pipelex.pipe_operators.pipe_func import PipeFunc
from pipelex.pipe_operators.pipe_func_factory import PipeFuncFactory
from pipelex.pipe_operators.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.pipe_img_gen_factory import PipeImgGenFactory
from pipelex.pipe_operators.pipe_jinja2 import PipeJinja2
from pipelex.pipe_operators.pipe_jinja2_factory import PipeJinja2Factory
from pipelex.pipe_operators.pipe_llm import PipeLLM
from pipelex.pipe_operators.pipe_llm_factory import PipeLLMFactory
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
from pipelex.pipe_operators.pipe_ocr import PipeOcr
from pipelex.pipe_operators.pipe_ocr_factory import PipeOcrFactory
from pipelex.tools.registry_models import ModelType, RegistryModels


class PipelexRegistryModels(RegistryModels):
    FIELD_EXTRACTION: ClassVar[List[ModelType]] = []

    PIPE_OPERATORS: ClassVar[List[PipeAbstractType]] = [
        PipeFunc,
        PipeImgGen,
        PipeJinja2,
        PipeLLM,
        PipeLLMPrompt,
        PipeOcr,
    ]

    PIPE_OPERATORS_FACTORY: ClassVar[List[PipeFactoryProtocol[Any, Any]]] = [
        PipeFuncFactory,
        PipeImgGenFactory,
        PipeJinja2Factory,
        PipeLLMFactory,
        PipeOcrFactory,
    ]

    PIPE_CONTROLLERS: ClassVar[List[PipeAbstractType]] = [
        PipeBatch,
        PipeCondition,
        PipeParallel,
        PipeSequence,
    ]

    PIPE_CONTROLLERS_FACTORY: ClassVar[List[PipeFactoryProtocol[Any, Any]]] = [
        PipeBatchFactory,
        PipeConditionFactory,
        PipeParallelFactory,
        PipeSequenceFactory,
    ]

    STUFF: ClassVar[List[ModelType]] = [
        TextContent,
        NumberContent,
        ImageContent,
        LLMPromptContent,
        Stuff,
        StuffContent,
        HtmlContent,
        ListContent,
        StructuredContent,
        PDFContent,
        TextAndImagesContent,
        PageContent,
        PipelexBundleBlueprint,
        PipelineDraft,
    ]

    EXPERIMENTAL: ClassVar[List[ModelType]] = [
        DynamicContent,
    ]
