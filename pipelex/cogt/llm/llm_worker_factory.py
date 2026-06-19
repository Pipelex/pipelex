from typing import cast

from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_inference_backend_registry, get_models_manager, get_sdk_client_manager
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol


class LLMWorkerFactory:
    @staticmethod
    def make_llm_worker(
        inference_model: InferenceModelSpec,
        *,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> LLMWorkerInternalAbstract:
        model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        make_worker = get_inference_backend_registry().lookup(family=InferenceFamily.LLM, sdk=model_handle.sdk)
        worker = make_worker(
            inference_model=inference_model,
            backend=backend,
            sdk_clients=get_sdk_client_manager().sdk_client_registry,
            reporting_delegate=reporting_delegate,
        )
        # The LLM family registry only ever holds LLM workers (the (family, sdk)
        # key guarantees it); the uniform MakeWorkerFn return type is widened to
        # InferenceWorkerAbstract, so narrow it back here.
        return cast("LLMWorkerInternalAbstract", worker)
