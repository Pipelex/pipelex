from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.runtime_hub import get_inference_backend_registry, get_inference_manager, get_model_deck


class TestSetupInferenceWorkers:
    def test_setup_inference_workers(self):
        inference_manager = get_inference_manager()
        for model_handle, inference_model in get_model_deck().inference_models.items():
            match inference_model.model_type:
                case ModelType.LLM:
                    llm_worker = inference_manager.get_llm_worker(llm_handle=model_handle)
                    assert inference_model == llm_worker.inference_model
                case ModelType.TEXT_EXTRACTOR:
                    _ = inference_manager.get_extract_worker(extract_handle=model_handle)
                case ModelType.IMG_GEN:
                    _ = inference_manager.get_img_gen_worker(img_gen_handle=model_handle)
                case ModelType.SEARCH:
                    pass
                case ModelType.DOC_GEN:
                    # The plugin's engines are declared in the kit but have no worker here; the built-in one does.
                    if get_inference_backend_registry().has(family=InferenceFamily.DOC_GEN, sdk=inference_model.sdk):
                        doc_gen_worker = DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model)
                        assert doc_gen_worker.inference_model == inference_model
