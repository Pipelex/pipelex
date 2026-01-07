import importlib.util

from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_models_manager, get_plugin_manager
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol


class LLMWorkerFactory:
    @staticmethod
    def make_llm_worker(
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> LLMWorkerInternalAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        llm_worker: LLMWorkerInternalAbstract
        match plugin.sdk:
            case "gateway_completions":
                from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GatewayCompletionsFactory.make_portkey_openai_client_for_completions(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                gateway_completions_factory = GatewayCompletionsFactory(is_http_url_enabled=False)

                llm_worker = OpenAICompletionsLLMWorker(
                    openai_completions_factory=gateway_completions_factory,
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "gateway_responses":
                from pipelex.plugins.gateway.gateway_responses_factory import GatewayResponsesFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GatewayResponsesFactory.make_portkey_openai_client_for_responses(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                gateway_responses_factory = GatewayResponsesFactory(is_http_url_enabled=False)

                llm_worker = OpenAIResponsesLLMWorker(
                    openai_responses_factory=gateway_responses_factory,
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "portkey_completions":
                from pipelex.plugins.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # noqa: PLC0415
                from pipelex.plugins.portkey.portkey_completions_factory import PortkeyCompletionsFactory  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=PortkeyCompletionsFactory.make_portkey_openai_client_for_completions(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                portkey_completions_factory = PortkeyCompletionsFactory(is_http_url_enabled=False)

                llm_worker = OpenAICompletionsLLMWorker(
                    openai_completions_factory=portkey_completions_factory,
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "portkey_responses":
                from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # noqa: PLC0415
                from pipelex.plugins.portkey.portkey_responses_factory import PortkeyResponsesFactory  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=PortkeyResponsesFactory.make_portkey_openai_client_for_responses(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                portkey_responses_factory = PortkeyResponsesFactory(is_http_url_enabled=False)

                llm_worker = OpenAIResponsesLLMWorker(
                    openai_responses_factory=portkey_responses_factory,
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "openai_responses" | "azure_openai_responses":
                from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIClientFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                openai_responses_factory = OpenAIResponsesFactory(is_http_url_enabled=True)

                llm_worker = OpenAIResponsesLLMWorker(
                    openai_responses_factory=openai_responses_factory,
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "openai" | "azure_openai":
                from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIClientFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                openai_completions_factory = OpenAICompletionsFactory(is_http_url_enabled=True)

                llm_worker = OpenAICompletionsLLMWorker(
                    openai_completions_factory=openai_completions_factory,
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "anthropic" | "bedrock_anthropic":
                if importlib.util.find_spec("anthropic") is None:
                    lib_name = "anthropic"
                    lib_extra_name = "anthropic"
                    msg = (
                        "The anthropic SDK is required in order to use Anthropic models via the anthropic client. "
                        "However, you can use Anthropic models through bedrock directly "
                        "by using the 'bedrock-anthropic-claude' llm family. (eg: bedrock-anthropic-claude)"
                    )
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.anthropic.anthropic_factory import AnthropicFactory  # noqa: PLC0415
                from pipelex.plugins.anthropic.anthropic_llm_worker import AnthropicLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=AnthropicFactory.make_anthropic_client(plugin=plugin, backend=backend),
                )

                llm_worker = AnthropicLLMWorker(
                    sdk_instance=sdk_instance,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "mistral":
                if importlib.util.find_spec("mistralai") is None:
                    lib_name = "mistralai"
                    lib_extra_name = "mistral"
                    msg = (
                        "The mistralai SDK is required in order to use Mistral models through the mistralai client. "
                        "However, you can use Mistral models through bedrock directly "
                        "by using the 'bedrock-mistral' llm family. (eg: bedrock-mistral-large)"
                    )
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.mistral.mistral_factory import MistralFactory  # noqa: PLC0415
                from pipelex.plugins.mistral.mistral_llm_worker import MistralLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=MistralFactory.make_mistral_client(backend=backend),
                )

                llm_worker = MistralLLMWorker(
                    mistral_factory=MistralFactory(),
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "bedrock_boto3" | "bedrock_aioboto3":
                if importlib.util.find_spec("boto3") is None or importlib.util.find_spec("aioboto3") is None:
                    lib_name = "boto3,aioboto3"
                    lib_extra_name = "bedrock"
                    msg = "The boto3 and aioboto3 SDKs are required to use Bedrock models."
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.bedrock.bedrock_factory import BedrockFactory  # noqa: PLC0415
                from pipelex.plugins.bedrock.bedrock_llm_worker import BedrockLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=BedrockFactory.make_bedrock_client(plugin=plugin, backend=backend),
                )

                llm_worker = BedrockLLMWorker(
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "google":
                if importlib.util.find_spec("google.genai") is None:
                    lib_name = "google-genai"
                    lib_extra_name = "google"
                    msg = (
                        "The google-genai SDK is required in order to use Google Gemini API directly. "
                        "You can install it with 'pip install google-genai'."
                    )
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.google.google_factory import GoogleFactory  # noqa: PLC0415
                from pipelex.plugins.google.google_llm_worker import GoogleLLMWorker  # noqa: PLC0415

                sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GoogleFactory.make_google_client(backend=backend),
                )

                llm_worker = GoogleLLMWorker(
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                msg = f"Plugin '{plugin}' is not supported"
                raise NotImplementedError(msg)
        return llm_worker
