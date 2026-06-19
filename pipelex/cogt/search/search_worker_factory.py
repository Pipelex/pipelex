from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.hub import get_models_manager, get_report_delegate, get_sdk_client_manager
from pipelex.plugins.model_handle import ModelHandle


class SearchWorkerFactory:
    @classmethod
    def make_search_worker(
        cls,
        inference_model: InferenceModelSpec,
    ) -> SearchWorkerAbstract:
        """Create a search worker for the given inference model.

        Discriminates on model_handle.sdk to select the appropriate implementation.

        Args:
            inference_model: The model spec from the backend configuration.

        Returns:
            A SearchWorkerAbstract instance.
        """
        model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        sdk_client_registry = get_sdk_client_manager().sdk_client_registry
        search_worker: SearchWorkerAbstract
        match model_handle.sdk:
            case "linkup":
                from pipelex.plugins.linkup.linkup_search_worker import LinkupSearchWorker  # noqa: PLC0415

                search_worker = LinkupSearchWorker(inference_model=inference_model, reporting_delegate=get_report_delegate())
            case "gateway_search":
                from pipelex.plugins.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415
                from pipelex.plugins.gateway.gateway_search_worker import GatewaySearchWorker  # noqa: PLC0415

                sdk_instance = sdk_client_registry.get(model_handle=model_handle) or sdk_client_registry.set(
                    model_handle=model_handle,
                    sdk_instance=GatewayFactory.make_portkey_client(backend=backend),
                )
                search_worker = GatewaySearchWorker(
                    sdk_instance=sdk_instance, inference_model=inference_model, reporting_delegate=get_report_delegate()
                )
            case _:
                msg = f"ModelHandle '{model_handle}' is not supported for search"
                raise NotImplementedError(msg)

        return search_worker
