from typing import Optional

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.hub import get_models_manager, get_plugin_manager
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol


class LLMWorkerFactory:
    @staticmethod
    def make_llm_worker(
        inference_model: InferenceModelSpec,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> LLMWorkerInternalAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        llm_worker: LLMWorkerInternalAbstract
        match plugin.sdk:
            case "openai" | "azure_openai":
                from pipelex.plugins.openai.openai_factory import OpenAIFactory

                structure_method: Optional[StructureMethod] = None
                if get_config().cogt.llm_config.instructor_config.is_openai_structured_output_enabled:
                    structure_method = StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED

                from pipelex.plugins.openai.openai_llm_worker import OpenAILLMWorker

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                llm_worker = OpenAILLMWorker(
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    structure_method=structure_method,
                    reporting_delegate=reporting_delegate,
                )
            case "anthropic" | "bedrock_anthropic":
                try:
                    import anthropic  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "anthropic",
                        "anthropic",
                        (
                            "The anthropic SDK is required to use Anthropic models via the anthropic client. "
                            "However, you can use Anthropic models through bedrock directly "
                            "by using the 'bedrock-anthropic-claude' llm family. (eg: bedrock-anthropic-claude)"
                        ),
                    ) from exc

                from pipelex.plugins.anthropic.anthropic_factory import AnthropicFactory
                from pipelex.plugins.anthropic.anthropic_llm_worker import AnthropicLLMWorker

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=AnthropicFactory.make_anthropic_client(plugin=plugin, backend=backend),
                )

                llm_worker = AnthropicLLMWorker(
                    sdk_instance=sdk_instance,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS,
                    reporting_delegate=reporting_delegate,
                )
            case "mistral":
                try:
                    import mistralai  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "mistralai",
                        "mistral",
                        (
                            "The mistralai SDK is required to use Mistral models through the mistralai client. "
                            "However, you can use Mistral models through bedrock directly "
                            "by using the 'bedrock-mistral' llm family. (eg: bedrock-mistral-large)"
                        ),
                    ) from exc

                from pipelex.plugins.mistral.mistral_factory import MistralFactory
                from pipelex.plugins.mistral.mistral_llm_worker import MistralLLMWorker

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=MistralFactory.make_mistral_client(backend=backend),
                )

                llm_worker = MistralLLMWorker(
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    structure_method=StructureMethod.INSTRUCTOR_MISTRAL_TOOLS,
                    reporting_delegate=reporting_delegate,
                )
            case "bedrock_boto3" | "bedrock_aioboto3":
                try:
                    import aioboto3  # noqa: F401
                    import boto3  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "boto3,aioboto3", "bedrock", "The boto3 and aioboto3 SDKs are required to use Bedrock models."
                    ) from exc

                from pipelex.plugins.bedrock.bedrock_factory import BedrockFactory
                from pipelex.plugins.bedrock.bedrock_llm_worker import BedrockLLMWorker

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=BedrockFactory.make_bedrock_client(plugin=plugin, backend=backend),
                )

                llm_worker = BedrockLLMWorker(
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                raise NotImplementedError(f"Plugin '{plugin}' is not supported")
        return llm_worker
