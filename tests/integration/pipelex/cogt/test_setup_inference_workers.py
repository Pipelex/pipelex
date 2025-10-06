from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.hub import get_inference_manager, get_model_deck


class TestSetupInferenceWorkers:
    def test_setup_inference_workers(self):
        inference_manager = get_inference_manager()
        for model_handle, inference_model in get_model_deck().inference_models.items():
            match inference_model.model_type:
                case ModelType.LLM:
                    llm_worker = inference_manager.get_llm_worker(llm_handle=model_handle)
                    if isinstance(llm_worker, LLMWorkerInternalAbstract):
                        assert inference_model == llm_worker.inference_model
                case ModelType.TEXT_EXTRACTOR:
                    _ = inference_manager.get_extract_worker(extract_handle=model_handle)
                case ModelType.IMG_GEN:
                    _ = inference_manager.get_img_gen_worker(img_gen_handle=model_handle)
