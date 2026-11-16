"""The rendered prompt an LLM leaf hands back for the trace: each text whole, or cut to a preview when it is large.

A prompt renders in its content-generation leaf (`pipelex.cogt.llm.unrendered_llm_prompt`), and the operator records
the rendered prompt in the trace, so the leaf hands it back with what it generated. On a host runtime that result is
the leaf activity's, which enters the workflow's history, and a rendered prompt holds every stored text its templates
read, loaded in full: handing it back whole would carry those texts through the history the stored form exists to keep
them out of. So the leaf hands back an `LLMPromptTrace`: a text up to `TRACED_PROMPT_TEXT_MAX_BYTES` as it is, and a
larger one as a `PromptTextPreview`, its start with the size and the SHA-256 of the whole, which identify the text the
model saw without carrying it. The prompt the model was sent is the full one; only what comes back is cut.
"""

import hashlib
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.llm.llm_prompt import LLMPrompt

# The largest rendered prompt text a leaf hands back whole, in bytes of its UTF-8 encoding. Four times the default
# inline-text threshold (`[runtime.storage] inline_text_max_bytes`): a prompt of instructions and short inputs comes
# back whole, while one that read a stored page, or several, comes back as a preview of this many bytes. It is not that
# threshold itself, which the unit tests set to 0 and which says what a value is, not what a trace keeps.
TRACED_PROMPT_TEXT_MAX_BYTES: Final[int] = 16_384


class PromptTextPreview(BaseModel):
    """A rendered prompt text too large to hand back whole: its start, and what identifies the whole.

    Attributes:
        preview: The text's start, the longest prefix whose UTF-8 encoding fits the bound, never a cut character.
        size: The whole text's size, in bytes of its UTF-8 encoding.
        sha256: The SHA-256 of the whole text's UTF-8 encoding, in hex.
    """

    model_config = ConfigDict(frozen=True)

    preview: str
    size: int = Field(ge=0)
    sha256: str

    @classmethod
    def make_from_text(cls, *, text: str, max_bytes: int) -> Self:
        encoded = text.encode("utf-8")
        return cls(
            preview=encoded[:max_bytes].decode("utf-8", errors="ignore"),
            size=len(encoded),
            sha256=hashlib.sha256(encoded).hexdigest(),
        )

    def as_trace_text(self) -> str:
        """The preview followed by what was left out, as the trace shows it."""
        return f"{self.preview}… [cut for the trace: {self.size} bytes, sha256 {self.sha256}]"


class LLMPromptTrace(BaseModel):
    """A rendered LLM prompt as its leaf hands it back: what the trace records of the prompt the model was sent.

    Attributes:
        system_text: The system text, whole, or its preview when it is larger than the bound.
        user_text: The user text, whole, or its preview when it is larger than the bound.
        user_images: The images the prompt sent, by reference, in the order its text numbers them.
        user_documents: The documents the prompt sent, by reference, in the order its text numbers them.
    """

    model_config = ConfigDict(frozen=True)

    system_text: str | PromptTextPreview | None = None
    user_text: str | PromptTextPreview | None = None
    user_images: list[PromptImage] = []
    user_documents: list[PromptDocument] = []

    @classmethod
    def make_from_prompt(cls, *, llm_prompt: LLMPrompt, max_text_bytes: int = TRACED_PROMPT_TEXT_MAX_BYTES) -> Self:
        """The trace of a rendered prompt, each text larger than `max_text_bytes` cut to its preview."""
        return cls(
            system_text=_traced_text(text=llm_prompt.system_text, max_bytes=max_text_bytes),
            user_text=_traced_text(text=llm_prompt.user_text, max_bytes=max_text_bytes),
            user_images=list(llm_prompt.user_images),
            user_documents=list(llm_prompt.user_documents),
        )

    @property
    def traced_system_text(self) -> str | None:
        """The system text as the trace shows it: whole, or its preview followed by what was left out."""
        return _trace_text(traced=self.system_text)

    @property
    def traced_user_text(self) -> str | None:
        """The user text as the trace shows it: whole, or its preview followed by what was left out."""
        return _trace_text(traced=self.user_text)


def _traced_text(*, text: str | None, max_bytes: int) -> str | PromptTextPreview | None:
    if text is None or len(text.encode("utf-8")) <= max_bytes:
        return text
    return PromptTextPreview.make_from_text(text=text, max_bytes=max_bytes)


def _trace_text(*, traced: str | PromptTextPreview | None) -> str | None:
    if isinstance(traced, PromptTextPreview):
        return traced.as_trace_text()
    return traced
