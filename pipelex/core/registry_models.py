from typing import Any, ClassVar

from pipelex.core.pipes.pipe_abstract import PipeAbstractType
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import (
    DynamicContent,
    HtmlContent,
    ImageContent,
    ListContent,
    NumberContent,
    PageContent,
    PDFContent,
    StructuredContent,
    StuffContent,
    TextAndImagesContent,
    TextContent,
)
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_factory import PipeBatchFactory
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_factory import PipeConditionFactory
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_factory import PipeParallelFactory
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_factory import PipeSequenceFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_factory import PipeComposeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_factory import PipeFuncFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_factory import PipeImgGenFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from pipelex.pipe_operators.ocr.pipe_ocr import PipeOcr
from pipelex.pipe_operators.ocr.pipe_ocr_factory import PipeOcrFactory
from pipelex.tools.registry_models import ModelType, RegistryModels


class PipelexRegistryModels(RegistryModels):
    FIELD_EXTRACTION: ClassVar[list[ModelType]] = []

    PIPE_OPERATORS: ClassVar[list[PipeAbstractType]] = [
        PipeFunc,
        PipeImgGen,
        PipeCompose,
        PipeLLM,
        PipeOcr,
    ]

    PIPE_OPERATORS_FACTORY: ClassVar[list[PipeFactoryProtocol[Any, Any]]] = [
        PipeFuncFactory,
        PipeImgGenFactory,
        PipeComposeFactory,
        PipeLLMFactory,
        PipeOcrFactory,
    ]

    PIPE_CONTROLLERS: ClassVar[list[PipeAbstractType]] = [
        PipeBatch,
        PipeCondition,
        PipeParallel,
        PipeSequence,
    ]

    PIPE_CONTROLLERS_FACTORY: ClassVar[list[PipeFactoryProtocol[Any, Any]]] = [
        PipeBatchFactory,
        PipeConditionFactory,
        PipeParallelFactory,
        PipeSequenceFactory,
    ]

    STUFF: ClassVar[list[ModelType]] = [
        TextContent,
        NumberContent,
        ImageContent,
        Stuff,
        StuffContent,
        HtmlContent,
        ListContent,
        StructuredContent,
        PDFContent,
        TextAndImagesContent,
        PageContent,
    ]

    EXPERIMENTAL: ClassVar[list[ModelType]] = [
        DynamicContent,
    ]
