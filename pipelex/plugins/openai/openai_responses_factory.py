from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openai.types.responses import ResponseInputImageParam
from typing_extensions import override

from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.plugin_factory_abstract import PluginFactoryAbstract
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from openai.types.responses import (
        ResponseInputItemParam,
        ResponseInputMessageContentListParam,
        ResponseInputTextParam,
        ResponseUsage,
    )

    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class OpenAIResponsesFactory(PluginFactoryAbstract):
    def __init__(self, is_http_url_enabled: bool):
        super().__init__()
        self.is_http_url_enabled = is_http_url_enabled

    async def make_input_items(self, llm_job: LLMJob) -> list[ResponseInputItemParam]:
        """Build Response API input items from a standard LLM job prompt."""
        llm_prompt = llm_job.llm_prompt
        input_items: list[ResponseInputItemParam] = []

        user_contents: ResponseInputMessageContentListParam = []
        if llm_prompt.user_text:
            text_content: ResponseInputTextParam = {"type": "input_text", "text": llm_prompt.user_text}
            user_contents.append(text_content)

        detail = llm_job.job_params.image_detail or PromptImageDetail.AUTO
        prepped_images = await prep_prompt_images(prompt_images=llm_prompt.user_images, is_http_url_enabled=self.is_http_url_enabled)
        for prepped_image in prepped_images:
            url: str
            match prepped_image:
                case PreparedFileHttpUrl():
                    url = prepped_image.url
                case PreparedFileBase64():
                    url = prepped_image.as_data_url()
                case PreparedFileLocalPath():
                    msg = "PreparedFileLocalPath is not supported for images - should be converted to base64"
                    raise TypeError(msg)

            image_param = ResponseInputImageParam(type="input_image", image_url=url, detail=detail.as_openai_detail)
            user_contents.append(image_param)

        if not user_contents:
            msg = "LLM prompt must include text or images for the user input when using the OpenAI Responses API"
            raise LLMPromptParameterError(msg)

        input_items.append(
            {
                "role": "user",
                "content": user_contents,
            }
        )
        return input_items

    def make_nb_tokens_by_category(self, usage: ResponseUsage) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.input_tokens,
            TokenCategory.OUTPUT: usage.output_tokens,
        }
        if usage.input_tokens_details:
            nb_tokens_by_category[TokenCategory.INPUT_CACHED] = usage.input_tokens_details.cached_tokens
        if usage.output_tokens_details:
            nb_tokens_by_category[TokenCategory.OUTPUT_REASONING] = usage.output_tokens_details.reasoning_tokens
        return nb_tokens_by_category

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return inference_model.extra_headers or {}, {}
