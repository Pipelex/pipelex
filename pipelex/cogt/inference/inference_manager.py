from typing import Dict, Type

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceManagerWorkerSetupError
from pipelex.cogt.imgg.imgg_engine_factory import ImggEngineFactory
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.imgg.imgg_worker_factory import ImggWorkerFactory
from pipelex.cogt.inference.inference_manager_protocol import InferenceManagerProtocol
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_engine_factory import LLMEngineFactory
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.ocr.ocr_engine_factory import OcrEngineFactory
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.cogt.ocr.ocr_worker_factory import OcrWorkerFactory
from pipelex.config import get_config
from pipelex.hub import get_llm_deck, get_report_delegate


class InferenceManager(InferenceManagerProtocol):
    def __init__(self):
        self.imgg_worker_factory = ImggWorkerFactory()
        self.ocr_worker_factory = OcrWorkerFactory()
        self.llm_workers: Dict[str, LLMWorkerAbstract] = {}
        self.imgg_workers: Dict[str, ImggWorkerAbstract] = {}
        self.ocr_workers: Dict[str, OcrWorkerAbstract] = {}

    @override
    def teardown(self):
        self.imgg_worker_factory = ImggWorkerFactory()
        self.ocr_worker_factory = OcrWorkerFactory()
        for llm_worker in self.llm_workers.values():
            llm_worker.teardown()
        self.llm_workers = {}
        for imgg_worker in self.imgg_workers.values():
            imgg_worker.teardown()
        self.imgg_workers = {}
        for ocr_worker in self.ocr_workers.values():
            ocr_worker.teardown()
        self.ocr_workers = {}
        log.verbose("InferenceManager teardown done")

    def print_workers(self):
        log.debug("LLM Workers:")
        for handle, llm_worker in self.llm_workers.items():
            log.debug(f"  {handle}:")
            log.debug(llm_worker.desc)
        log.debug("Image Workers:")
        for handle, imgg_worker_async in self.imgg_workers.items():
            log.debug(f"  {handle}:")
            log.debug(imgg_worker_async.desc)
        log.debug("OCR Workers:")
        for handle, ocr_worker_async in self.ocr_workers.items():
            log.debug(f"  {handle}:")
            log.debug(ocr_worker_async.desc)

    ####################################################################################################
    # Setup LLM Workers
    ####################################################################################################

    @override
    def setup_llm_workers(self):
        log.verbose("Setting up LLM Workers...")
        llm_handle_to_llm_engine_blueprint = get_llm_deck().llm_handles
        log.verbose(f"{len(llm_handle_to_llm_engine_blueprint)} LLM engine_cards found")
        for llm_handle, llm_engine_blueprint in llm_handle_to_llm_engine_blueprint.items():
            self._setup_one_internal_llm_worker(llm_engine_blueprint=llm_engine_blueprint, llm_handle=llm_handle)
            log.verbose(f"Setup LLM worker for '{llm_handle}' on {llm_engine_blueprint.llm_platform_choice}")
        log.debug("Done setting up LLM Workers (async)")

    def _setup_one_internal_llm_worker(
        self,
        llm_engine_blueprint: LLMEngineBlueprint,
        llm_handle: str,
    ) -> LLMWorkerInternalAbstract:
        llm_engine = LLMEngineFactory.make_llm_engine(llm_engine_blueprint=llm_engine_blueprint)
        llm_worker = LLMWorkerFactory.make_llm_worker(
            llm_engine=llm_engine,
            reporting_delegate=get_report_delegate(),
        )
        self.llm_workers[llm_handle] = llm_worker
        return llm_worker

    @override
    def get_llm_worker(self, llm_handle: str) -> LLMWorkerAbstract:
        if llm_worker := self.llm_workers.get(llm_handle):
            return llm_worker
        if not get_config().cogt.inference_manager_config.is_auto_setup_preset_llm:
            raise InferenceManagerWorkerSetupError(
                f"No LLM worker for '{llm_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_llm"
            )

        llm_engine_blueprint = get_llm_deck().get_llm_engine_blueprint(llm_handle=llm_handle)
        llm_worker = self._setup_one_internal_llm_worker(
            llm_engine_blueprint=llm_engine_blueprint,
            llm_handle=llm_handle,
        )

        return llm_worker

    @override
    def set_llm_worker_from_external_plugin(
        self,
        llm_handle: str,
        llm_worker_class: Type[LLMWorkerAbstract],
        should_warn_if_already_registered: bool = True,
    ):
        if llm_handle in self.llm_workers:
            if should_warn_if_already_registered:
                log.warning(f"LLM worker for '{llm_handle}' already registered, skipping")
        self.llm_workers[llm_handle] = llm_worker_class(reporting_delegate=get_report_delegate())

    ####################################################################################################
    # Manage IMGG Workers
    ####################################################################################################

    @override
    def setup_imgg_workers(self):
        log.verbose("Setting up Imgg Workers...")
        imgg_handles = get_config().cogt.imgg_config.imgg_handles
        log.verbose(f"{len(imgg_handles)} Imgg handles found")
        for imgg_handle in imgg_handles:
            self._setup_one_imgg_worker(imgg_handle=imgg_handle)

        log.debug("Done setting up Imgg Workers (async)")

    def _setup_one_imgg_worker(self, imgg_handle: str) -> ImggWorkerAbstract:
        imgg_engine = ImggEngineFactory.make_imgg_engine(imgg_handle=imgg_handle)
        log.verbose(imgg_engine.desc, title=f"Setting up ImgEngine for '{imgg_handle}'")
        imgg_worker = self.imgg_worker_factory.make_imgg_worker(
            imgg_engine=imgg_engine,
            reporting_delegate=get_report_delegate(),
        )
        self.imgg_workers[imgg_handle] = imgg_worker
        return imgg_worker

    @override
    def get_imgg_worker(self, imgg_handle: str) -> ImggWorkerAbstract:
        imgg_worker = self.imgg_workers.get(imgg_handle)
        if imgg_worker is None:
            if not get_config().cogt.inference_manager_config.is_auto_setup_preset_imgg:
                raise InferenceManagerWorkerSetupError(
                    f"Found no Imgg worker for '{imgg_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_imgg"
                )

            imgg_worker = self._setup_one_imgg_worker(imgg_handle=imgg_handle)
        return imgg_worker

    ####################################################################################################
    # Manage OCR Workers
    ####################################################################################################

    @override
    def setup_ocr_workers(self):
        log.verbose("Setting up OCR Workers...")
        ocr_handles = get_config().cogt.ocr_config.ocr_handles
        log.verbose(f"{len(ocr_handles)} OCR handles found")
        for ocr_handle in ocr_handles:
            self._setup_one_ocr_worker(ocr_handle=ocr_handle)

        log.debug("Done setting up OCR Workers (async)")

    def _setup_one_ocr_worker(self, ocr_handle: str) -> OcrWorkerAbstract:
        ocr_engine = OcrEngineFactory.make_ocr_engine(ocr_handle=ocr_handle)
        log.verbose(ocr_engine.desc, title=f"Setting up OcrEngine for '{ocr_handle}'")
        ocr_worker = self.ocr_worker_factory.make_ocr_worker(
            ocr_engine=ocr_engine,
            reporting_delegate=get_report_delegate(),
        )
        self.ocr_workers[ocr_handle] = ocr_worker
        return ocr_worker

    @override
    def get_ocr_worker(self, ocr_handle: str) -> OcrWorkerAbstract:
        ocr_worker = self.ocr_workers.get(ocr_handle)
        if ocr_worker is None:
            if not get_config().cogt.inference_manager_config.is_auto_setup_preset_ocr:
                raise InferenceManagerWorkerSetupError(
                    f"Found no OCR worker for '{ocr_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_ocr"
                )

            ocr_worker = self._setup_one_ocr_worker(ocr_handle=ocr_handle)
        return ocr_worker
