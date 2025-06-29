from typing import Optional, Protocol

from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract


class InferenceManagerProtocol(Protocol):
    """
    This is the protocol for the inference manager.
    Its point is only to avoid a circular import.
    """

    def teardown(self): ...

    ####################################################################################################
    # LLM Workers
    ####################################################################################################

    def setup_llm_workers(self): ...

    def get_llm_worker(
        self,
        llm_handle: str,
        specific_llm_engine_blueprint: Optional[LLMEngineBlueprint] = None,
    ) -> LLMWorkerAbstract: ...

    def set_llm_worker(
        self,
        llm_handle: str,
        llm_worker: LLMWorkerAbstract,
        should_warn_if_already_registered: bool = True,
    ): ...

    ####################################################################################################
    # IMG Generation Workers
    ####################################################################################################

    def setup_imgg_workers(self): ...

    def get_imgg_worker(self, imgg_handle: str) -> ImggWorkerAbstract: ...

    ####################################################################################################
    # OCR Workers
    ####################################################################################################

    def setup_ocr_workers(self): ...

    def get_ocr_worker(self, ocr_handle: str) -> OcrWorkerAbstract: ...
