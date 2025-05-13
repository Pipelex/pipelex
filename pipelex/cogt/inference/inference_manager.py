# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, Optional

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceManagerWorkerSetupError
from pipelex.cogt.imgg.imgg_engine_factory import ImggEngineFactory
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.imgg.imgg_worker_factory import ImggWorkerFactory
from pipelex.cogt.inference.inference_manager_protocol import InferenceManagerProtocol
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_engine_factory import LLMEngineFactory
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.config import get_config
from pipelex.hub import get_llm_deck, get_report_delegate


class InferenceManager(InferenceManagerProtocol):
    def __init__(self):
        self.llm_worker_factory = LLMWorkerFactory()
        self.imgg_worker_factory = ImggWorkerFactory()
        self.llm_workers: Dict[str, LLMWorkerAbstract] = {}
        self.imgg_workers: Dict[str, ImggWorkerAbstract] = {}

    @override
    def reset(self):
        self.llm_worker_factory.clear()
        self.llm_worker_factory = LLMWorkerFactory()
        self.imgg_worker_factory = ImggWorkerFactory()
        self.llm_workers.clear()
        self.imgg_workers.clear()
        log.verbose("InferenceManagerAsync reset")

    def print_workers(self):
        log.debug("LLM Workers:")
        for handle, llm_worker_async in self.llm_workers.items():
            log.debug(f"  {handle}:")
            log.debug(llm_worker_async.desc)
        log.debug("Image Workers:")
        for handle, imgg_worker_async in self.imgg_workers.items():
            log.debug(f"  {handle}:")
            log.debug(imgg_worker_async.desc)

    ####################################################################################################
    # Config shorthands
    ####################################################################################################
    @property
    def _default_imgg_handle(self) -> ImggHandle:
        return get_config().cogt.imgg_config.default_imgg_handle

    ####################################################################################################
    # Setup LLM Workers
    ####################################################################################################

    @override
    def setup_llm_workers(self):
        log.verbose("Setting up LLM Workers...")
        llm_handle_to_llm_engine_blueprint = get_llm_deck().llm_handles
        log.verbose(f"{len(llm_handle_to_llm_engine_blueprint)} LLM engine_cards found")
        for llm_handle, llm_engine_blueprint in llm_handle_to_llm_engine_blueprint.items():
            self._setup_one_llm_worker(llm_engine_blueprint=llm_engine_blueprint, llm_handle=llm_handle)
            log.verbose(f"Setup LLM worker for '{llm_handle}' on {llm_engine_blueprint.llm_platform_choice}")
        log.debug("Done setting up LLM Workers (async)")

    def _setup_one_llm_worker(
        self,
        llm_engine_blueprint: LLMEngineBlueprint,
        llm_handle: str,
    ) -> LLMWorkerAbstract:
        llm_engine = LLMEngineFactory.make_llm_engine(llm_engine_blueprint=llm_engine_blueprint)
        llm_worker = self.llm_worker_factory.make_llm_worker(
            llm_engine=llm_engine,
            report_delegate=get_report_delegate(),
        )
        self.llm_workers[llm_handle] = llm_worker
        return llm_worker

    @override
    def get_llm_worker(
        self,
        llm_handle: str,
        specific_llm_engine_blueprint: Optional[LLMEngineBlueprint] = None,
    ) -> LLMWorkerAbstract:
        if llm_worker := self.llm_workers.get(llm_handle):
            return llm_worker
        if not get_config().cogt.inference_manager_config.is_auto_setup_preset_llm:
            raise InferenceManagerWorkerSetupError(
                f"No LLM worker for '{llm_handle}', set it up or enable cogt.inference_manager_config.is_auto_setup_preset_llm"
            )

        if not specific_llm_engine_blueprint:
            specific_llm_engine_blueprint = get_llm_deck().get_llm_engine_blueprint(llm_handle=llm_handle)
        llm_worker = self._setup_one_llm_worker(
            llm_engine_blueprint=specific_llm_engine_blueprint,
            llm_handle=llm_handle,
        )

        return llm_worker

    ####################################################################################################
    # Manage IMG Workers
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
        imgg_engine = ImggEngineFactory.make_imgg_engine_for_fal(imgg_name=imgg_handle)
        log.verbose(imgg_engine.desc, title=f"Setting up ImgEngine for '{imgg_handle}'")
        imgg_worker = self.imgg_worker_factory.make_imgg_worker(
            imgg_engine=imgg_engine,
            report_delegate=get_report_delegate(),
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
