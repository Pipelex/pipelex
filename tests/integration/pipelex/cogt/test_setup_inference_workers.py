from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.runtime_hub import get_inference_manager, get_model_deck


class TestSetupInferenceWorkers:
    def test_setup_inference_workers(self):
        inference_manager = get_inference_manager()
        for inference_model in get_model_deck().inference_models.all_specs():
            model_handle = inference_model.name
            match inference_model.model_type:
                case ModelType.LLM:
                    llm_worker = inference_manager.get_llm_worker(llm_handle=model_handle)
                    assert inference_model == llm_worker.inference_model
                case ModelType.TEXT_EXTRACTOR:
                    _ = inference_manager.get_extract_worker(extract_handle=model_handle)
                case ModelType.IMG_GEN:
                    _ = inference_manager.get_img_gen_worker(img_gen_handle=model_handle)
                case ModelType.SEARCH | ModelType.JUDGMENT:
                    pass
                case ModelType.DOC_GEN:
                    # Every document engine the deck serves has a worker: the kit declares only the built-in one, and a
                    # plugin that declares an engine also registers its worker.
                    doc_gen_worker = DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model)
                    assert doc_gen_worker.inference_model == inference_model
