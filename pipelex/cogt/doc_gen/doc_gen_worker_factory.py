from typing import cast

from pipelex.cogt.doc_gen.doc_gen_worker_abstract import DocGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import get_inference_backend_registry, get_models_manager, get_sdk_client_manager


class DocGenWorkerFactory:
    @classmethod
    def make_doc_gen_worker(
        cls,
        *,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> DocGenWorkerAbstract:
        model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        make_worker = get_inference_backend_registry().lookup(family=InferenceFamily.DOC_GEN, sdk=model_handle.sdk)
        worker = make_worker(
            inference_model=inference_model,
            backend=backend,
            sdk_clients=get_sdk_client_manager().sdk_client_registry,
            reporting_delegate=reporting_delegate,
        )
        # The DOC_GEN family registry only ever holds doc gen workers, which the (family, sdk) key guarantees; the
        # uniform MakeWorkerFn return type is widened to InferenceWorkerAbstract, so narrow it back here.
        return cast("DocGenWorkerAbstract", worker)
