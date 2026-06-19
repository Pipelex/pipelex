from typing import cast

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.hub import get_inference_backend_registry, get_models_manager, get_sdk_client_manager
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol


class SearchWorkerFactory:
    @classmethod
    def make_search_worker(
        cls,
        inference_model: InferenceModelSpec,
        *,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> SearchWorkerAbstract:
        """Create a search worker for the given inference model via the inference-backend registry.

        Args:
            inference_model: The model spec from the backend configuration.
            reporting_delegate: The reporting delegate passed through to the worker
                (supplied by the caller — the factory no longer reaches into the hub).

        Returns:
            A SearchWorkerAbstract instance.
        """
        model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        make_worker = get_inference_backend_registry().lookup(family=InferenceFamily.SEARCH, sdk=model_handle.sdk)
        worker = make_worker(
            inference_model=inference_model,
            backend=backend,
            sdk_clients=get_sdk_client_manager().sdk_client_registry,
            reporting_delegate=reporting_delegate,
        )
        # The SEARCH family registry only ever holds search workers (the
        # (family, sdk) key guarantees it); the uniform MakeWorkerFn return type is
        # widened to InferenceWorkerAbstract, so narrow it back here.
        return cast("SearchWorkerAbstract", worker)
