import pytest

from pipelex import log
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
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

        get_inference_manager().setup_imgg_workers()
