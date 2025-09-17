import pytest

from pipelex import log
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.config import get_config
from pipelex.hub import get_inference_manager, get_models_manager


@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
class TestSetupInferenceWorkers:
    def test_setup_inference_manager(self):
        inference_manager = get_inference_manager()
        llm_handle_to_inference_model = get_models_manager().get_llm_deck().inference_models
        log.verbose(f"{len(llm_handle_to_inference_model)} LLM engine_cards found")
        for llm_handle, inference_model in llm_handle_to_inference_model.items():
            llm_worker = inference_manager.get_llm_worker(llm_handle=llm_handle)
            if isinstance(llm_worker, LLMWorkerInternalAbstract):
                assert inference_model == llm_worker.inference_model
        log.debug("Done setting up LLM Workers (async)")

    def test_setup_imgg_workers(self):
        inference_manager = get_inference_manager()
        imgg_handles = get_config().cogt.imgg_config.imgg_handles
        log.verbose(f"{len(imgg_handles)} Imgg handles found")
        for imgg_handle in imgg_handles:
            imgg_worker = inference_manager.get_imgg_worker(imgg_handle=imgg_handle)
            assert imgg_worker is not None
            assert imgg_worker.imgg_engine is not None
        log.debug("Done setting up Imgg Workers (async)")

    def test_setup_ocr_workers(self):
        inference_manager = get_inference_manager()
        ocr_handles = get_config().cogt.ocr_config.ocr_handles
        log.verbose(f"{len(ocr_handles)} OCR handles found")
        for ocr_handle in ocr_handles:
            ocr_worker = inference_manager.get_ocr_worker(ocr_handle=ocr_handle)
            assert ocr_worker is not None
            assert ocr_worker.ocr_engine is not None
        log.debug("Done setting up OCR Workers (async)")
