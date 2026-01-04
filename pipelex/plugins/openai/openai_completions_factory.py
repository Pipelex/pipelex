from typing import Any

from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from openai.types.completion_usage import CompletionUsage
from typing_extensions import override

from pipelex.cogt.image.prepared_image import PreparedImageData, PreparedImageUrl
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.plugin_factory_abstract import PluginFactoryAbstract


class OpenAICompletionsFactory(PluginFactoryAbstract):
    def __init__(self, is_http_url_enabled: bool):
        super().__init__()
        self.is_http_url_enabled = is_http_url_enabled

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
                url: str
                match prepped_image:
                    case PreparedImageUrl():
                        url = prepped_image.url
                    case PreparedImageData():
                        url = prepped_image.as_data_url()

                image_url_obj = ImageURL(url=url, detail=detail.as_openai_detail)
                image_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    def make_nb_tokens_by_category(self, usage: CompletionUsage) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.prompt_tokens,
            TokenCategory.OUTPUT: usage.completion_tokens,
        }
        if prompt_tokens_details := usage.prompt_tokens_details:
            nb_tokens_by_category[TokenCategory.INPUT_AUDIO] = prompt_tokens_details.audio_tokens or 0
            nb_tokens_by_category[TokenCategory.INPUT_CACHED] = prompt_tokens_details.cached_tokens or 0
        if completion_tokens_details := usage.completion_tokens_details:
            nb_tokens_by_category[TokenCategory.OUTPUT_AUDIO] = completion_tokens_details.audio_tokens or 0
            nb_tokens_by_category[TokenCategory.OUTPUT_REASONING] = completion_tokens_details.reasoning_tokens or 0
            nb_tokens_by_category[TokenCategory.OUTPUT_ACCEPTED_PREDICTION] = completion_tokens_details.accepted_prediction_tokens or 0
            nb_tokens_by_category[TokenCategory.OUTPUT_REJECTED_PREDICTION] = completion_tokens_details.rejected_prediction_tokens or 0
        return nb_tokens_by_category

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return inference_model.extra_headers or {}, {}
