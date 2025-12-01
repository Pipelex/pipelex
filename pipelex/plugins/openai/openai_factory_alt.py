from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from typing_extensions import override

from pipelex.cogt.image.prompt_image import PromptImageDetail, PromptImageTypedBase64
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.plugins.openai.openai_factory import OpenAIFactory


class OpenAIFactoryAlt(OpenAIFactory):
    def __init__(self, is_http_url_enabled: bool):
        super().__init__()
        self.is_http_url_enabled = is_http_url_enabled

    @override
    @override
    async def make_simple_messages(
        self,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        llm_prompt = llm_job.llm_prompt
        messages: list[ChatCompletionMessageParam] = []
        user_contents: list[ChatCompletionContentPartParam] = []
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))
        # TODO: confirm that we can prompt without user_contents, for instance if we have only images,
        # otherwise consider using a default user_content
        if user_prompt_text := llm_prompt.user_text:
            user_part_text = ChatCompletionContentPartTextParam(text=user_prompt_text, type="text")
            user_contents.append(user_part_text)
        if llm_prompt.user_images:
            detail = llm_job.job_params.image_detail or PromptImageDetail.AUTO
            prepped_images = await prep_prompt_images(prompt_images=llm_prompt.user_images, is_http_url_enabled=self.is_http_url_enabled)
            for prepped_image in prepped_images:
                if isinstance(prepped_image, str):
                    url = prepped_image
                else:
                    assert isinstance(prepped_image, PromptImageTypedBase64)
                    url = PromptImageFactory.make_base_64_url_from_prompt_image_typed_base64(prompt_image=prepped_image)

                image_url_obj = ImageURL(url=url, detail=detail.as_openai_detail)
                image_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages
