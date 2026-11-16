"""What an LLM content-generation leaf returns: what it generated, and the trace of the prompt it rendered to generate it.

The prompt is rendered in the leaf (`pipelex.cogt.llm.unrendered_llm_prompt`), so the operator, which records the rendered
prompt in the trace, receives it back from the leaf beside the generated value rather than rendering it itself. It comes
back as an `LLMPromptTrace` (`pipelex.cogt.llm.llm_prompt_trace`), each large text cut to a preview, so the stored texts
the prompt read never travel back whole.
"""

from typing import Generic

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.llm.llm_prompt_trace import LLMPromptTrace
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class LLMTextGeneration(BaseModel):
    """A generated text and the trace of the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    text: str
    rendered_prompt: LLMPromptTrace


class LLMObjectGeneration(BaseModel, Generic[BaseModelTypeVar]):
    """A generated object and the trace of the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    generated_object: BaseModelTypeVar
    rendered_prompt: LLMPromptTrace


class LLMObjectListGeneration(BaseModel, Generic[BaseModelTypeVar]):
    """A generated list of objects and the trace of the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    generated_objects: list[BaseModelTypeVar]
    rendered_prompt: LLMPromptTrace
