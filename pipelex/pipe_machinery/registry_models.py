from typing import Any, ClassVar

from pipelex.core.pipes.pipe_abstract import PipeAbstractType
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
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
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_factory import PipeSearchFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_factory import PipeStructureFactory
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.pipe_signature.pipe_signature_factory import PipeSignatureFactory
from pipelex.system.registries.registry_base import RegistryModels


class PipeRegistryModels(RegistryModels):
    """Every pipe kind and its factory, as one boot-time registration manifest.

    Filed here rather than in ``core/`` because a pipe is the interpreter's own object: this manifest
    imports every ``pipe_operators`` / ``pipe_controllers`` / ``pipe_signature`` module by construction,
    so keeping it under ``core/`` made ``core`` read as a dependant of the pipe packages. Adding a pipe
    kind means adding it here — see ``docs/contribute/registration-surface.md`` for the full list of
    places one pipe kind touches.
    """

    PIPE_OPERATORS: ClassVar[list[PipeAbstractType]] = [
        PipeFunc,
        PipeImgGen,
        PipeCompose,
        PipeLLM,
        PipeExtract,
        PipeSearch,
        PipeStructure,
    ]

    PIPE_OPERATORS_FACTORY: ClassVar[list[PipeFactoryProtocol[Any, Any]]] = [
        PipeFuncFactory,
        PipeImgGenFactory,
        PipeComposeFactory,
        PipeLLMFactory,
        PipeExtractFactory,
        PipeSearchFactory,
        PipeStructureFactory,
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

    PIPE_SIGNATURES: ClassVar[list[PipeAbstractType]] = [
        PipeSignature,
    ]

    PIPE_SIGNATURES_FACTORY: ClassVar[list[PipeFactoryProtocol[Any, Any]]] = [
        PipeSignatureFactory,
    ]
