import importlib.util

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
        reporting_delegate: ReportingProtocol | None = None,
    ) -> LLMWorkerInternalAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        llm_worker: LLMWorkerInternalAbstract
        match plugin.sdk:
            case "openai" | "azure_openai":
                from pipelex.plugins.openai.openai_factory import OpenAIFactory  # noqa: PLC0415

                structure_method: StructureMethod | None = None
                if get_config().cogt.llm_config.instructor_config.is_openai_structured_output_enabled:
                    structure_method = StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED

                from pipelex.plugins.openai.openai_llm_worker import OpenAILLMWorker  # noqa: PLC0415

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
                if importlib.util.find_spec("anthropic") is None:
                    lib_name = "anthropic"
                    lib_extra_name = "anthropic"
                    msg = (
                        "The anthropic SDK is required to use Anthropic models via the anthropic client. "
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
                    structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS,
                    reporting_delegate=reporting_delegate,
                )
            case "mistral":
                if importlib.util.find_spec("mistralai") is None:
                    lib_name = "mistralai"
                    lib_extra_name = "mistral"
                    msg = (
                        "The mistralai SDK is required to use Mistral models through the mistralai client. "
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
                    sdk_instance=sdk_instance,
                    inference_model=inference_model,
                    structure_method=StructureMethod.INSTRUCTOR_MISTRAL_TOOLS,
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
                    msg = "The google-genai SDK is required to use Google Gemini API directly. You can install it with 'pip install google-genai'."
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
                    structure_method=StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                msg = f"Plugin '{plugin}' is not supported"
                raise NotImplementedError(msg)
        return llm_worker
