"""What an LLM content-generation leaf returns: what it generated, and the prompt it rendered to generate it.

The prompt is rendered in the leaf (`pipelex.cogt.llm.unrendered_llm_prompt`), so the operator, which records the rendered
prompt in the trace, receives it back from the leaf beside the generated value rather than rendering it itself.
"""

from typing import Generic

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class LLMTextGeneration(BaseModel):
    """A generated text and the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    text: str
    rendered_prompt: LLMPrompt


class LLMObjectGeneration(BaseModel, Generic[BaseModelTypeVar]):
    """A generated object and the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    generated_object: BaseModelTypeVar
    rendered_prompt: LLMPrompt


class LLMObjectListGeneration(BaseModel, Generic[BaseModelTypeVar]):
    """A generated list of objects and the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    generated_objects: list[BaseModelTypeVar]
    rendered_prompt: LLMPrompt
