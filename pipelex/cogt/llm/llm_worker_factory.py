# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Any, Dict, Optional

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.config import get_config


class LLMSDKHandle(StrEnum):
    OPENAI_ASYNC = "openai_async"
    AZURE_OPENAI_ASYNC = "azure_openai_async"
    ANTHROPIC_ASYNC = "anthropic_async"
    BEDROCK_ANTHROPIC_ASYNC = "bedrock_anthropic_async"
    MISTRAL_ASYNC = "mistral_async"
    BEDROCK_ASYNC = "bedrock_async"
    PERPLEXITY_ASYNC = "perplexity_async"
    VERTEXAI_OPENAI_ASYNC = "vertexai_openai_async"

    @staticmethod
    def get_for(llm_platform: LLMPlatform) -> "LLMSDKHandle":
        match llm_platform:
            case LLMPlatform.OPENAI:
                return LLMSDKHandle.OPENAI_ASYNC
            case LLMPlatform.AZURE_OPENAI:
                return LLMSDKHandle.AZURE_OPENAI_ASYNC
            case LLMPlatform.ANTHROPIC:
                return LLMSDKHandle.ANTHROPIC_ASYNC
            case LLMPlatform.MISTRAL:
                return LLMSDKHandle.MISTRAL_ASYNC
            case LLMPlatform.BEDROCK:
                return LLMSDKHandle.BEDROCK_ASYNC
            case LLMPlatform.BEDROCK_ANTHROPIC:
                return LLMSDKHandle.BEDROCK_ANTHROPIC_ASYNC
            case LLMPlatform.PERPLEXITY:
                return LLMSDKHandle.PERPLEXITY_ASYNC
            case LLMPlatform.VERTEXAI_OPENAI:
                return LLMSDKHandle.VERTEXAI_OPENAI_ASYNC


class LLMWorkerFactory:
    def __init__(self):
        self.llm_sdk_instances: Dict[LLMSDKHandle, Any] = {}

    def clear(self):
        self.llm_sdk_instances.clear()

    def get_llm_sdk_instance(self, llm_sdk_handle: LLMSDKHandle) -> Optional[Any]:
        llm_sdk_instance = self.llm_sdk_instances.get(llm_sdk_handle)
        return llm_sdk_instance

    def set_llm_sdk_instance(self, llm_sdk_handle: LLMSDKHandle, llm_sdk_instance: Any) -> Any:
        self.llm_sdk_instances[llm_sdk_handle] = llm_sdk_instance
        return llm_sdk_instance

    def make_llm_worker(
        self,
        llm_engine: LLMEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ) -> LLMWorkerAbstract:
        llm_worker: LLMWorkerAbstract

        llm_sdk_handle = LLMSDKHandle.get_for(llm_platform=llm_engine.llm_platform)
        match llm_engine.llm_platform:
            case LLMPlatform.OPENAI | LLMPlatform.AZURE_OPENAI | LLMPlatform.PERPLEXITY:
                from pipelex.cogt.openai.openai_factory import OpenAIFactory

                structure_method: Optional[StructureMethod] = None
                if get_config().cogt.llm_config.instructor_config.is_openai_structured_output_enabled:
                    structure_method = StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED

                from pipelex.cogt.openai.openai_worker import OpenAIWorker

                llm_sdk_instance = self.get_llm_sdk_instance(llm_sdk_handle=llm_sdk_handle) or self.set_llm_sdk_instance(
                    llm_sdk_handle=llm_sdk_handle,
                    llm_sdk_instance=OpenAIFactory.make_openai_client(llm_platform=llm_engine.llm_platform),
                )

                llm_worker = OpenAIWorker(
                    sdk_instance=llm_sdk_instance,
                    llm_engine=llm_engine,
                    structure_method=structure_method,
                    report_delegate=report_delegate,
                )
            case LLMPlatform.VERTEXAI_OPENAI:
                try:
                    import google.auth  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError("google-auth-oauthlib", "google", "This dependency is required to connect to google.") from exc

                from pipelex.cogt.openai.openai_factory import OpenAIFactory
                from pipelex.cogt.openai.openai_worker import OpenAIWorker

                llm_sdk_instance = self.get_llm_sdk_instance(llm_sdk_handle=llm_sdk_handle) or self.set_llm_sdk_instance(
                    llm_sdk_handle=llm_sdk_handle,
                    llm_sdk_instance=OpenAIFactory.make_openai_client(llm_platform=llm_engine.llm_platform),
                )

                llm_worker = OpenAIWorker(
                    sdk_instance=llm_sdk_instance,
                    llm_engine=llm_engine,
                    structure_method=StructureMethod.INSTRUCTOR_VERTEX_JSON,
                    report_delegate=report_delegate,
                )

            case LLMPlatform.ANTHROPIC | LLMPlatform.BEDROCK_ANTHROPIC:
                try:
                    import anthropic  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "anthropic",
                        "anthropic",
                        "The anthropic SDK is required to use Anthropic models via the anthropic client. \
                        However, you can use Anthropic models through bedrock directly by using the 'bedrock-anthropic-claude' llm family.\
                        (eg: bedrock-anthropic-claude)",
                    ) from exc

                from pipelex.cogt.anthropic.anthropic_factory import AnthropicFactory
                from pipelex.cogt.anthropic.anthropic_worker import AnthropicWorker

                llm_sdk_instance = self.get_llm_sdk_instance(llm_sdk_handle=llm_sdk_handle) or self.set_llm_sdk_instance(
                    llm_sdk_handle=llm_sdk_handle,
                    llm_sdk_instance=AnthropicFactory.make_anthropic_client(llm_platform=llm_engine.llm_platform),
                )

                llm_worker = AnthropicWorker(
                    sdk_instance=llm_sdk_instance,
                    llm_engine=llm_engine,
                    structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS,
                    report_delegate=report_delegate,
                )
            case LLMPlatform.MISTRAL:
                try:
                    import mistralai  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "mistralai",
                        "mistral",
                        "The mistralai SDK is required to use Mistral models through the mistralai client. \
                        However, you can use Mistral models through bedrock directly by using the 'bedrock-mistral' llm family. \
                        (eg: bedrock-mistral-large)",
                    ) from exc

                from pipelex.cogt.mistral.mistral_factory import MistralFactory
                from pipelex.cogt.mistral.mistral_worker import MistralWorker

                llm_sdk_instance = self.get_llm_sdk_instance(llm_sdk_handle=llm_sdk_handle) or self.set_llm_sdk_instance(
                    llm_sdk_handle=llm_sdk_handle,
                    llm_sdk_instance=MistralFactory.make_mistral_client(),
                )

                llm_worker = MistralWorker(
                    sdk_instance=llm_sdk_instance,
                    llm_engine=llm_engine,
                    structure_method=StructureMethod.INSTRUCTOR_MISTRAL_TOOLS,
                    report_delegate=report_delegate,
                )
            case LLMPlatform.BEDROCK:
                try:
                    import aioboto3  # noqa: F401
                    import boto3  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "boto3,aioboto3", "bedrock", "The boto3 and aioboto3 SDKs are required to use Bedrock models."
                    ) from exc

                from pipelex.cogt.bedrock.bedrock_factory import BedrockFactory
                from pipelex.cogt.bedrock.bedrock_worker import BedrockWorker

                llm_sdk_instance = self.get_llm_sdk_instance(llm_sdk_handle=llm_sdk_handle) or self.set_llm_sdk_instance(
                    llm_sdk_handle=llm_sdk_handle,
                    llm_sdk_instance=BedrockFactory.make_bedrock_client(),
                )

                llm_worker = BedrockWorker(
                    sdk_instance=llm_sdk_instance,
                    llm_engine=llm_engine,
                    report_delegate=report_delegate,
                )
        return llm_worker
