from pipelex import log
from pipelex.cogt.exceptions import CogtError, LLMCapabilityError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageBytes
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_message import BedrockContentItem, BedrockImage, BedrockMessage, BedrockSource, ImageFormat
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.types import StrEnum


class BedrockFactoryError(CogtError):
    pass


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
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> BedrockClientProtocol:
        try:
            sdk_variant = BedrockSdkVariant(plugin.sdk)
        except ValueError:
            raise BedrockFactoryError(f"Plugin '{plugin}' is not supported by BedrockFactory")

        bedrock_async_client: BedrockClientProtocol
        log.verbose(f"Using '{sdk_variant}' for BedrockClient")
        match sdk_variant:
            case BedrockSdkVariant.AIBOTO3:
                from pipelex.plugins.bedrock.bedrock_client_aioboto3 import BedrockClientAioboto3

                bedrock_async_client = BedrockClientAioboto3(
                    aws_region=backend.extra_config[BedrockExtraField.AWS_REGION],
                )
            case BedrockSdkVariant.BOTO3:
                from pipelex.plugins.bedrock.bedrock_client_boto3 import BedrockClientBoto3

                bedrock_async_client = BedrockClientBoto3(
                    aws_region=backend.extra_config[BedrockExtraField.AWS_REGION],
                )

        return bedrock_async_client

    #########################################################
    # Message
    #########################################################

    @classmethod
    def make_simple_message(cls, llm_job: LLMJob) -> BedrockMessage:
        """
        Makes a list of messages with a system message (if provided) and followed by a user message.
        """
        message = BedrockMessage(role="user", content=[])
        if user_text := llm_job.llm_prompt.user_text:
            message.content.append(BedrockContentItem(text=user_text))
        if user_images := llm_job.llm_prompt.user_images:
            raise LLMCapabilityError("BedrockFactory does not support images. Skipping images.")
            for user_image in user_images:
                if isinstance(user_image, PromptImageBytes):
                    image_bytes = user_image.image_bytes
                    image = BedrockImage(
                        format=ImageFormat.JPEG,
                        source=BedrockSource(bytes=image_bytes),
                    )
                    message.content.append(BedrockContentItem(image=image))
                else:
                    raise PromptImageFormatError("Only PromptImageBytes is supported for BedrockFactory.")

        return message
