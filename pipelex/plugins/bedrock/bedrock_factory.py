from pipelex import log
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.hub import get_plugin_manager, get_secrets_provider
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_config import BedrockClientMethod
from pipelex.plugins.bedrock.bedrock_message import BedrockContentItem, BedrockMessage


class BedrockFactory:
    #########################################################
    # Client
    #########################################################

    @classmethod
    def make_bedrock_client(cls) -> BedrockClientProtocol:
        bedrock_config = get_plugin_manager().plugin_configs.bedrock_config
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
        return message
