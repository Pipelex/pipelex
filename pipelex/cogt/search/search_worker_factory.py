from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.fetch_worker_abstract import FetchWorkerAbstract
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.hub import get_models_manager, get_plugin_manager, get_report_delegate
from pipelex.plugins.plugin import Plugin


class SearchWorkerFactory:
    @classmethod
    def make_search_worker(
        cls,
        inference_model: InferenceModelSpec,
    ) -> SearchWorkerAbstract:
        """Create a search worker for the given inference model.

        Discriminates on plugin.sdk to select the appropriate implementation.

        Args:
            inference_model: The model spec from the backend configuration.

        Returns:
            A SearchWorkerAbstract instance.
        """
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        search_worker: SearchWorkerAbstract
        match plugin.sdk:
            case "linkup":
                from pipelex.plugins.linkup.linkup_worker import LinkupWorker  # noqa: PLC0415

                search_worker = LinkupWorker(inference_model=inference_model, reporting_delegate=get_report_delegate())
            case "gateway_search":
                from pipelex.plugins.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415
                from pipelex.plugins.gateway.gateway_search_worker import GatewaySearchWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GatewayFactory.make_portkey_client(backend=backend),
                )
                search_worker = GatewaySearchWorker(
                    sdk_instance=sdk_instance, inference_model=inference_model, reporting_delegate=get_report_delegate()
                )
            case _:
                msg = f"Plugin '{plugin}' is not supported for search"
                raise NotImplementedError(msg)

        return search_worker

    @classmethod
    def make_fetch_worker(
        cls,
        inference_model: InferenceModelSpec,
    ) -> FetchWorkerAbstract:
        """Create a fetch worker for the given inference model.

        Discriminates on plugin.sdk to select the appropriate implementation.

        Args:
            inference_model: The model spec from the backend configuration.

        Returns:
            A FetchWorkerAbstract instance.
        """
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        fetch_worker: FetchWorkerAbstract
        match plugin.sdk:
            case "linkup":
                from pipelex.plugins.linkup.linkup_worker import LinkupWorker  # noqa: PLC0415

                fetch_worker = LinkupWorker(inference_model=inference_model, reporting_delegate=get_report_delegate())
            case "gateway_search":
                from pipelex.plugins.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415
                from pipelex.plugins.gateway.gateway_fetch_worker import GatewayFetchWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GatewayFactory.make_portkey_client(backend=backend),
                )
                fetch_worker = GatewayFetchWorker(
                    sdk_instance=sdk_instance, inference_model=inference_model, reporting_delegate=get_report_delegate()
                )
            case _:
                msg = f"Plugin '{plugin}' is not supported for fetch"
                raise NotImplementedError(msg)

        return fetch_worker
