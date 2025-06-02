from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageBytes
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.config import get_config
from pipelex.hub import get_secrets_provider
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_config import BedrockClientMethod
from pipelex.plugins.bedrock.bedrock_message import BedrockContentItem, BedrockImage, BedrockMessage, BedrockSource, ImageFormat


class BedrockFactory:
    #########################################################
    # Client
    #########################################################

    @classmethod
    def make_bedrock_client(cls) -> BedrockClientProtocol:
        bedrock_config = get_config().plugins.bedrock_config
        aws_region = bedrock_config.configure(secrets_provider=get_secrets_provider())
        client_method = bedrock_config.client_method
        bedrock_async_client: BedrockClientProtocol
        log.verbose(f"Using '{client_method}' for BedrockClient")
        match client_method:
            case BedrockClientMethod.AIBOTO3:
                from pipelex.plugins.bedrock.bedrock_client_aioboto3 import BedrockClientAioboto3

                bedrock_async_client = BedrockClientAioboto3(aws_region=aws_region)
            case BedrockClientMethod.BOTO3:
                from pipelex.plugins.bedrock.bedrock_client_boto3 import BedrockClientBoto3

                bedrock_async_client = BedrockClientBoto3(aws_region=aws_region)

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
