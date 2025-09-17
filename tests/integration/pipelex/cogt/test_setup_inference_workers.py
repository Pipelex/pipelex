import pytest

from pipelex import log
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.config import get_config
from pipelex.hub import get_inference_manager, get_models_manager


@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
class TestSetupInferenceWorkers:
    def test_setup_inference_workers(self):
        inference_manager = get_inference_manager()
        inference_models = get_models_manager().get_model_deck().inference_models
        log.verbose(f"{len(inference_models)} LLM engine_cards found")
        for model_handle, inference_model in inference_models.items():
            match inference_model.model_type:
                case ModelType.LLM:
                    llm_worker = inference_manager.get_llm_worker(llm_handle=model_handle)
                    if isinstance(llm_worker, LLMWorkerInternalAbstract):
                        assert inference_model == llm_worker.inference_model
                case ModelType.TEXT_EXTRACTOR:
                    _ = inference_manager.get_ocr_worker(model_handle=model_handle)

    def test_setup_imgg_workers(self):
        inference_manager = get_inference_manager()
        imgg_handles = get_config().cogt.imgg_config.imgg_handles
        log.verbose(f"{len(imgg_handles)} Imgg handles found")
        for imgg_handle in imgg_handles:
            imgg_worker = inference_manager.get_imgg_worker(imgg_handle=imgg_handle)
            assert imgg_worker is not None
            assert imgg_worker.imgg_engine is not None
        log.debug("Done setting up Imgg Workers (async)")
