from enum import StrEnum

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.providers.bedrock.bedrock_exceptions import BedrockFactoryError
from pipelex.providers.bedrock.bedrock_message import BedrockContentItem, BedrockMessage


class BedrockSdkVariant(StrEnum):
    BOTO3 = "bedrock_boto3"
    AIBOTO3 = "bedrock_aioboto3"


class BedrockExtraField(StrEnum):
    AWS_REGION = "aws_region"


class BedrockFactory:
    #########################################################
    # Client
    #########################################################

    @classmethod
    def make_bedrock_client(
        cls,
        model_handle: ModelHandle,
        *,
        backend: InferenceBackend,
    ) -> BedrockClientProtocol:
        try:
            sdk_variant = BedrockSdkVariant(model_handle.sdk)
        except ValueError as exc:
            msg = f"ModelHandle '{model_handle}' is not supported by BedrockFactory"
            raise BedrockFactoryError(msg) from exc

        bedrock_async_client: BedrockClientProtocol
        log.verbose(f"Using '{sdk_variant}' for BedrockClient")
        match sdk_variant:
            case BedrockSdkVariant.AIBOTO3:
                from pipelex.providers.bedrock.bedrock_client_aioboto3 import BedrockClientAioboto3  # ruff: ignore[import-outside-top-level]

                bedrock_async_client = BedrockClientAioboto3(
                    aws_region=backend.extra_config[BedrockExtraField.AWS_REGION],
                )
            case BedrockSdkVariant.BOTO3:
                from pipelex.providers.bedrock.bedrock_client_boto3 import BedrockClientBoto3  # ruff: ignore[import-outside-top-level]

                bedrock_async_client = BedrockClientBoto3(
                    aws_region=backend.extra_config[BedrockExtraField.AWS_REGION],
                )

        return bedrock_async_client

    #########################################################
    # Message
    #########################################################

    @classmethod
    def make_simple_message(cls, llm_job: LLMJob) -> BedrockMessage:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        message = BedrockMessage(role="user", content=[])
        if user_text := llm_job.llm_prompt.user_text:
            message.content.append(BedrockContentItem(text=user_text))
        if llm_job.llm_prompt.user_images:
            msg = "BedrockFactory does not support images. Skipping images."
            raise LLMCapabilityError(msg)

        return message
