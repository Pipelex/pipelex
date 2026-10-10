from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.document.prompt_document import PromptDocument, PromptDocumentUri
from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.system.runtime import ProblemReaction, runtime_manager
from pipelex.tools.misc.string_utils import is_none_or_has_text, is_not_none_and_has_text
from pipelex.tools.uri.uri_read_scope import UriReference
from pipelex.tools.log.log_fields import USER_ACTION_FIELD


class LLMPrompt(BaseModel):
    system_text: str | None = None
    user_text: str | None = None
    user_images: list[PromptImage] = []
    user_documents: list[PromptDocument] = []

    def referenced_uris(self) -> list[UriReference]:
        """The URLs a worker will read to send this prompt: its images and documents given by URI."""
        uri_references = [
            UriReference(uri=image.uri, position=f"image {index} of the prompt")
            for index, image in enumerate(self.user_images, start=1)
            if isinstance(image, PromptImageUri)
        ]
        uri_references.extend(
            UriReference(uri=document.uri, position=f"document {index} of the prompt")
            for index, document in enumerate(self.user_documents, start=1)
            if isinstance(document, PromptDocumentUri)
        )
        return uri_references

    def validate_before_execution(self):
        reaction = runtime_manager.problem_reactions.job
        match reaction:
            case ProblemReaction.NONE:
                pass
            case ProblemReaction.RAISE:
                if not is_none_or_has_text(text=self.system_text):
                    if self.system_text == "":
                        log.debug("The prompt's system text is empty, so it is treated as absent")
                    else:
                        msg = "system_text should be None or contain text"
                        raise LLMPromptParameterError(msg)
                if not is_not_none_and_has_text(text=self.user_text):
                    msg = "user_text should contain text"
                    raise LLMPromptParameterError(msg)
            case ProblemReaction.LOG:
                if not is_none_or_has_text(text=self.system_text):
                    if self.system_text == "":
                        log.debug("The prompt's system text is empty, so it is treated as absent")
                    else:
                        log.error("The system text of a prompt has no letter or digit in it", fields={USER_ACTION_FIELD: "Leave the system text out or give it some text"})
                if not is_not_none_and_has_text(text=self.user_text):
                    log.error("The user text of a prompt has no letter or digit in it")

    @override
    def __str__(self) -> str:
        return self.desc()

    @override
    def __repr__(self) -> str:
        return self.desc()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.desc()

    def desc(self, *, truncate_text_length: int | None = None) -> str:
        description = "LLM Prompt:"
        if truncate_text_length:
            if self.system_text:
                description += f"""
    system_text:
    {self.system_text[:truncate_text_length]}
    """
            if self.user_text:
                description += f"""
    user_text:
    {self.user_text[:truncate_text_length]}
    """
        else:
            if self.system_text:
                description += f"""
    system_text:
    {self.system_text}
    """
            if self.user_text:
                description += f"""
    user_text:
    {self.user_text}
    """
        if self.user_images:
            user_images_desc: str = "\n".join([f"  {image}" for image in self.user_images])

            description += f"""
user_images:
{user_images_desc}
"""
        if self.user_documents:
            user_documents_desc: str = "\n".join([f"  {document}" for document in self.user_documents])

            description += f"""
user_documents:
{user_documents_desc}
"""
        return description
