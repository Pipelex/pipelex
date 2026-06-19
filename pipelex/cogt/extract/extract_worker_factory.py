import importlib.util

from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_models_manager, get_sdk_client_manager
from pipelex.plugins.model_handle import ModelHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol


class ExtractWorkerFactory:
    @classmethod
    def make_extract_worker(
        cls,
        inference_model: InferenceModelSpec,
        *,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> ExtractWorkerAbstract:
        model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        sdk_client_registry = get_sdk_client_manager().sdk_client_registry
        extract_worker: ExtractWorkerAbstract
        match model_handle.sdk:
            case "gateway_extract":
                from pipelex.plugins.gateway.gateway_extract_worker import GatewayExtractWorker  # noqa: PLC0415
                from pipelex.plugins.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415

                extract_sdk_instance = sdk_client_registry.get(model_handle=model_handle) or sdk_client_registry.set(
                    model_handle=model_handle,
                    sdk_instance=GatewayFactory.make_portkey_client(backend=backend),
                )

                extract_worker = GatewayExtractWorker(
                    sdk_instance=extract_sdk_instance,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "mistral":
                if importlib.util.find_spec("mistralai") is None:
                    lib_name = "mistralai"
                    lib_extra_name = "mistral"
                    msg = "The mistralai SDK is required in order to use Mistral OCR models through the mistralai client."
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.mistral.mistral_extract_worker import MistralExtractWorker  # noqa: PLC0415
                from pipelex.plugins.mistral.mistral_factory import MistralFactory  # noqa: PLC0415

                extract_sdk_instance = sdk_client_registry.get(model_handle=model_handle) or sdk_client_registry.set(
                    model_handle=model_handle,
                    sdk_instance=MistralFactory.make_mistral_client(backend=backend),
                )

                extract_worker = MistralExtractWorker(
                    sdk_instance=extract_sdk_instance,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "pypdfium2":
                from pipelex.plugins.pypdfium2.pypdfium2_worker import Pypdfium2Worker  # noqa: PLC0415

                extract_worker = Pypdfium2Worker(
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "docling_sdk":
                if importlib.util.find_spec("docling") is None:
                    lib_name = "docling"
                    lib_extra_name = "docling"
                    msg = "The docling library is required in order to use Docling for PDF and image text extraction."
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.docling.docling_extract_worker import DoclingExtractWorker  # noqa: PLC0415
                from pipelex.plugins.docling.docling_factory import DoclingFactory  # noqa: PLC0415

                extract_sdk_instance = sdk_client_registry.get(model_handle=model_handle) or sdk_client_registry.set(
                    model_handle=model_handle,
                    sdk_instance=DoclingFactory.make_docling_sdk(),
                )

                extract_worker = DoclingExtractWorker(
                    sdk_instance=extract_sdk_instance,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "linkup_fetch":
                if importlib.util.find_spec("linkup") is None:
                    lib_name = "linkup"
                    lib_extra_name = "linkup"
                    msg = "The linkup SDK is required in order to use Linkup Fetch extraction models."
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.linkup.linkup_extract_worker import LinkupExtractWorker  # noqa: PLC0415

                extract_worker = LinkupExtractWorker(
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                msg = f"ModelHandle '{model_handle}' is not supported"
                raise NotImplementedError(msg)

        return extract_worker
