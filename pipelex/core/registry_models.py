from typing import Any, ClassVar

from pipelex.core.pipes.pipe_abstract import PipeAbstractType
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.stuffs.dynamic_content import DynamicContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.pdf_content import PDFContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
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
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipe_operators.extract.pipe_extract_factory import PipeExtractFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_factory import PipeFuncFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_factory import PipeImgGenFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from pipelex.system.registries.registry_base import ModelType, RegistryModels


class CoreRegistryModels(RegistryModels):
    FIELD_EXTRACTION: ClassVar[list[ModelType]] = []

    PIPE_OPERATORS: ClassVar[list[PipeAbstractType]] = [
        PipeFunc,
        PipeImgGen,
        PipeCompose,
        PipeLLM,
        PipeExtract,
    ]

    PIPE_OPERATORS_FACTORY: ClassVar[list[PipeFactoryProtocol[Any, Any]]] = [
        PipeFuncFactory,
        PipeImgGenFactory,
        PipeComposeFactory,
        PipeLLMFactory,
        PipeExtractFactory,
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
