from typing import Optional

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.hub import get_plugin_manager, get_secret
from pipelex.plugins.openai.openai_imgg_worker import OpenAIImggWorker
from pipelex.plugins.plugin_sdk_registry import PluginSdkHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError


class FalCredentialsError(CogtError):
    pass


class ImggWorkerFactory:
    def make_imgg_worker(
        self,
        imgg_engine: ImggEngine,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> ImggWorkerAbstract:
        imgg_sdk_handle = PluginSdkHandle.get_for_imgg_engine(imgg_platform=imgg_engine.imgg_platform)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        imgg_worker: ImggWorkerAbstract
        match imgg_engine.imgg_platform:
            case ImggPlatform.FAL_AI:
                try:
                    fal_api_key = get_secret(secret_id="FAL_API_KEY")
                except SecretNotFoundError as exc:
                    raise FalCredentialsError("FAL_API_KEY not found") from exc

                try:
                    from fal_client import AsyncClient as FalAsyncClient
                except ImportError as exc:
                    raise MissingDependencyError(
                        "fal-client", "fal", "The fal-client SDK is required to use FAL models (generation of images)."
                    ) from exc

                from pipelex.plugins.fal.fal_imgg_worker import FalImggWorker

                imgg_sdk_instance = plugin_sdk_registry.get_imgg_sdk_instance(
                    imgg_sdk_handle=imgg_sdk_handle
                ) or plugin_sdk_registry.set_imgg_sdk_instance(
                    imgg_sdk_handle=imgg_sdk_handle,
                    imgg_sdk_instance=FalAsyncClient(key=fal_api_key),
                )

                imgg_worker = FalImggWorker(
                    sdk_instance=imgg_sdk_instance,
                    imgg_engine=imgg_engine,
                    reporting_delegate=reporting_delegate,
                )
            case ImggPlatform.OPENAI:
                from pipelex.plugins.openai.openai_factory import OpenAIFactory

                imgg_sdk_instance = plugin_sdk_registry.get_llm_sdk_instance(
                    llm_sdk_handle=imgg_sdk_handle
                ) or plugin_sdk_registry.set_llm_sdk_instance(
                    llm_sdk_handle=imgg_sdk_handle,
                    llm_sdk_instance=OpenAIFactory.make_openai_client(llm_platform=LLMPlatform.OPENAI),
                )

                imgg_worker = OpenAIImggWorker(
                    sdk_instance=imgg_sdk_instance,
                    imgg_engine=imgg_engine,
                    reporting_delegate=reporting_delegate,
                )

        return imgg_worker
