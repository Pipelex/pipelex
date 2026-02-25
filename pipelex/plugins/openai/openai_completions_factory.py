from typing import Any

from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL as OpenAIImageURL
from openai.types.chat.chat_completion_content_part_param import File as ChatCompletionContentPartFileParam
from openai.types.completion_usage import CompletionUsage
from typing_extensions import override

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_utils import prep_prompt_documents
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.plugin_factory_abstract import PluginFactoryAbstract
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath


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
                    case PreparedFileHttpUrl():
                        url = prepped_image.url
                    case PreparedFileBase64():
                        url = prepped_image.as_data_url()
                    case PreparedFileLocalPath():
                        msg = "PreparedFileLocalPath is not supported for images - should be converted to base64"
                        raise TypeError(msg)

                image_url_obj = OpenAIImageURL(url=url, detail=detail.as_openai_detail)
                image_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                user_contents.append(image_param)

        # Handle documents (PDF support via Chat Completions API)
        # Documents must always be base64 encoded since Chat Completions API doesn't support file_url directly
        if llm_prompt.user_documents:
            prepped_documents = await prep_prompt_documents(prompt_documents=llm_prompt.user_documents, is_http_url_enabled=False)
            for doc_index, prepped_document in enumerate(prepped_documents):
                match prepped_document:
                    case PreparedFileBase64():
                        filename = self._get_document_filename(llm_prompt.user_documents[doc_index])
                        file_data = f"data:{prepped_document.mime_type};base64,{prepped_document.base64_data}"
                        file_param = ChatCompletionContentPartFileParam(
                            type="file",
                            file={"file_data": file_data, "filename": filename},
                        )
                        user_contents.append(file_param)
                    case PreparedFileHttpUrl() | PreparedFileLocalPath():
                        msg = f"{type(prepped_document).__name__} is not supported for documents - should be converted to base64"
                        raise TypeError(msg)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    @staticmethod
    def _get_document_filename(prompt_document: PromptDocument) -> str:
        """Generate a filename from a PromptDocument for OpenAI Chat Completions API."""
        # Note: we hardocde the extension to pdf because OpenAI Chat Completions API only supports PDF files at this stage
        return f"document_{prompt_document.get_content_hash(length=12)}.pdf"

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
