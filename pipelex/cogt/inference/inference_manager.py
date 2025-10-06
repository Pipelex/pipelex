from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceManagerWorkerSetupError
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.extract.extract_worker_factory import ExtractWorkerFactory
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.img_gen.img_gen_worker_factory import ImgGenWorkerFactory
from pipelex.cogt.inference.inference_manager_protocol import InferenceManagerProtocol
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.hub import get_models_manager, get_report_delegate


class InferenceManager(InferenceManagerProtocol):
    def __init__(self):
        # TODO: we don't need instances of the factories, we can just use them via class methods
        self.img_gen_worker_factory = ImgGenWorkerFactory()
        self.extract_worker_factory = ExtractWorkerFactory()
        self.llm_workers: dict[str, LLMWorkerAbstract] = {}
        self.img_gen_workers: dict[str, ImgGenWorkerAbstract] = {}
        self.extract_workers: dict[str, ExtractWorkerAbstract] = {}

    @override
    def teardown(self):
        self.img_gen_worker_factory = ImgGenWorkerFactory()
        self.extract_worker_factory = ExtractWorkerFactory()
        for llm_worker in self.llm_workers.values():
            llm_worker.teardown()
        self.llm_workers = {}
        for img_gen_worker in self.img_gen_workers.values():
            img_gen_worker.teardown()
        self.img_gen_workers = {}
        for extract_worker in self.extract_workers.values():
            extract_worker.teardown()
        self.extract_workers = {}
        log.verbose("InferenceManager teardown done")

    def print_workers(self):
        log.debug("LLM Workers:")
        for handle, llm_worker in self.llm_workers.items():
            log.debug(f"  {handle}:")
            log.debug(llm_worker.desc)
        log.debug("Image Workers:")
        for handle, img_gen_worker_async in self.img_gen_workers.items():
            log.debug(f"  {handle}:")
            log.debug(img_gen_worker_async.desc)
        log.debug("OCR Workers:")
        for handle, extract_worker_async in self.extract_workers.items():
            log.debug(f"  {handle}:")
            log.debug(extract_worker_async.desc)

    ####################################################################################################
    # Setup LLM Workers
    ####################################################################################################

    def _setup_one_internal_llm_worker(
        self,
        inference_model: InferenceModelSpec,
        llm_handle: str,
    ) -> LLMWorkerInternalAbstract:
        llm_worker = LLMWorkerFactory.make_llm_worker(
            inference_model=inference_model,
            reporting_delegate=get_report_delegate(),
        )
        self.llm_workers[llm_handle] = llm_worker
        return llm_worker

    @override
    def get_llm_worker(self, llm_handle: str) -> LLMWorkerAbstract:
        if llm_worker := self.llm_workers.get(llm_handle):
            return llm_worker
        if not get_config().cogt.inference_manager_config.is_auto_setup_preset_llm:
            msg = f"No LLM worker for '{llm_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_llm"
            raise InferenceManagerWorkerSetupError(msg)

        inference_model = get_models_manager().get_inference_model(model_handle=llm_handle)
        return self._setup_one_internal_llm_worker(
            inference_model=inference_model,
            llm_handle=llm_handle,
        )

    @override
    def set_llm_worker_from_external_plugin(
        self,
        llm_handle: str,
        llm_worker_class: type[LLMWorkerAbstract],
        should_warn_if_already_registered: bool = True,
    ):
        if llm_handle in self.llm_workers and should_warn_if_already_registered:
            log.warning(f"LLM worker for '{llm_handle}' already registered, skipping")
        self.llm_workers[llm_handle] = llm_worker_class(reporting_delegate=get_report_delegate())

    ####################################################################################################
    # Manage ImageGen Workers
    ####################################################################################################

    def _setup_one_img_gen_worker(self, img_gen_handle: str) -> ImgGenWorkerAbstract:
        inference_model = get_models_manager().get_inference_model(model_handle=img_gen_handle)
        log.verbose(f"Setting up Image Generation Worker for '{img_gen_handle}'")
        img_gen_worker = self.img_gen_worker_factory.make_img_gen_worker(
            inference_model=inference_model,
            reporting_delegate=get_report_delegate(),
        )
        self.img_gen_workers[img_gen_handle] = img_gen_worker
        return img_gen_worker

    @override
    def get_img_gen_worker(self, img_gen_handle: str) -> ImgGenWorkerAbstract:
        img_gen_worker = self.img_gen_workers.get(img_gen_handle)
        if img_gen_worker is None:
            if not get_config().cogt.inference_manager_config.is_auto_setup_preset_img_gen:
                msg = f"Found no ImgGen worker for '{img_gen_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_img_gen"
                raise InferenceManagerWorkerSetupError(msg)

            img_gen_worker = self._setup_one_img_gen_worker(img_gen_handle=img_gen_handle)
        return img_gen_worker

    ####################################################################################################
    # Manage Extract Workers
    ####################################################################################################

    def _setup_one_extract_worker(
        self,
        inference_model: InferenceModelSpec,
        extract_handle: str,
    ) -> ExtractWorkerAbstract:
        extract_worker = self.extract_worker_factory.make_extract_worker(
            inference_model=inference_model,
            reporting_delegate=get_report_delegate(),
        )
        self.extract_workers[extract_handle] = extract_worker
        return extract_worker

    @override
    def get_extract_worker(self, extract_handle: str) -> ExtractWorkerAbstract:
        if extract_worker := self.extract_workers.get(extract_handle):
            return extract_worker
        if not get_config().cogt.inference_manager_config.is_auto_setup_preset_extract:
            msg = f"Found no Extract worker for '{extract_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_extract"
            raise InferenceManagerWorkerSetupError(msg)

        inference_model = get_models_manager().get_inference_model(model_handle=extract_handle)
        return self._setup_one_extract_worker(
            inference_model=inference_model,
            extract_handle=extract_handle,
        )
