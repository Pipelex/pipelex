from typing import Protocol

from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract


class InferenceManagerProtocol(Protocol):
    """This is the protocol for the inference manager.
    Its point is only to avoid a circular import.
    """

    def teardown(self): ...

    ####################################################################################################
    # LLM Workers
    ####################################################################################################

    def get_llm_worker(self, llm_handle: str) -> LLMWorkerAbstract: ...

    def set_llm_worker_from_external_plugin(
        self,
        llm_handle: str,
        llm_worker_class: type[LLMWorkerAbstract],
        should_warn_if_already_registered: bool = True,
    ): ...

    ####################################################################################################
    # IMG Generation Workers
    ####################################################################################################

    def get_img_gen_worker(self, img_gen_handle: str) -> ImgGenWorkerAbstract: ...

    ####################################################################################################
    # OCR Workers
    ####################################################################################################

    def get_ocr_worker(self, model_handle: str) -> OcrWorkerAbstract: ...
