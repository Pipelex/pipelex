# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, ClassVar, List

from pipelex.core.pipe import PipeAbstractType
from pipelex.core.pipe_blueprint import PipeSpecificFactoryProtocol
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import (
    DynamicContent,
    HtmlContent,
    ImageContent,
    ListContent,
    LLMPromptContent,
    NumberContent,
    StructuredContent,
    StuffContent,
    TextContent,
)
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
from pipelex.tools.registry_models import ModelType, RegistryModels


class PipelexRegistryModels(RegistryModels):
    FIELD_EXTRACTION: ClassVar[List[ModelType]] = []

    PIPE_OPERATORS: ClassVar[List[PipeAbstractType]] = [
        PipeFunc,
        PipeImgGen,
        PipeJinja2,
        PipeLLM,
        PipeLLMPrompt,
    ]

    PIPE_OPERATORS_FACTORY: ClassVar[List[PipeSpecificFactoryProtocol[Any, Any]]] = [
        PipeFuncFactory,
        PipeImgGenFactory,
        PipeJinja2Factory,
        PipeLLMFactory,
    ]

    PIPE_CONTROLLERS: ClassVar[List[PipeAbstractType]] = [
        PipeBatch,
        PipeCondition,
        PipeParallel,
        PipeSequence,
    ]

    PIPE_CONTROLLERS_FACTORY: ClassVar[List[PipeSpecificFactoryProtocol[Any, Any]]] = [
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
    ]

    EXPERIMENTAL: ClassVar[List[ModelType]] = [
        DynamicContent,
    ]
