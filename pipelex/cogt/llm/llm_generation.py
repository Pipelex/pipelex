"""What an LLM content-generation leaf returns: what it generated, and the trace of the prompt it rendered to generate it.

The prompt is rendered in the leaf (`pipelex.cogt.llm.unrendered_llm_prompt`), so the operator, which records the rendered
prompt in the trace, receives it back from the leaf beside the generated value rather than rendering it itself. It comes
back as an `LLMPromptTrace` (`pipelex.cogt.llm.llm_prompt_trace`), each large text cut to a preview, so the stored texts
the prompt read never travel back whole.

On a host runtime these results cross an activity boundary back into workflow code, and a generated object is an instance
of the output's class, which the run's library built and which the far side may not be able to decode. So an object
generation crosses as plain JSON data (`__json_encode__`, the hook kajson encodes a value through), and decodes on the far
side, where its class is not parametrized, into `GeneratedObjectData`, which keeps every field; the caller then validates
it into its own class (`revalidate_object_generation` in `pipelex.cogt.content_generation.object_revalidation`).
"""

from typing import Any, Generic, cast

from pydantic import BaseModel, ConfigDict, field_validator

from pipelex.cogt.llm.llm_prompt_trace import LLMPromptTrace
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class GeneratedObjectData(BaseModel):
    """A generated object that crossed a process boundary as plain data, its fields kept until the caller validates it."""

    model_config = ConfigDict(frozen=True, extra="allow")


def _names_no_object_class(*, model_class: type[BaseModel]) -> bool:
    """Whether a generic generation class names no class for its objects: the bare one a decoder resolves, or one over `Any`."""
    generic_args: tuple[Any, ...] = model_class.__pydantic_generic_metadata__["args"]
    return not any(isinstance(generic_arg, type) and issubclass(generic_arg, BaseModel) for generic_arg in generic_args)


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

    @field_validator("generated_object", mode="before")
    @classmethod
    def decode_object_data(cls, value: Any) -> Any:
        """An object decoded as data into the bare class, which names no class for it, keeps its fields as data."""
        if not isinstance(value, dict) or not _names_no_object_class(model_class=cls):
            return cast("Any", value)
        return GeneratedObjectData.model_validate(value)

    def __json_encode__(self) -> dict[str, Any]:  # ruff: ignore[bad-dunder-method-name] — kajson encoder hook, name fixed by kajson's protocol
        """The generation as plain JSON data, the object by its fields' aliases, so it decodes wherever its class is unknown."""
        return self.model_dump(mode="json", serialize_as_any=True, by_alias=True)


class LLMObjectListGeneration(BaseModel, Generic[BaseModelTypeVar]):
    """A generated list of objects and the trace of the prompt it was generated from."""

    model_config = ConfigDict(frozen=True)

    generated_objects: list[BaseModelTypeVar]
    rendered_prompt: LLMPromptTrace

    @field_validator("generated_objects", mode="before")
    @classmethod
    def decode_objects_data(cls, value: Any) -> Any:
        """Objects decoded as data into the bare class, which names no class for them, keep their fields as data."""
        if not isinstance(value, list) or not _names_no_object_class(model_class=cls):
            return cast("Any", value)
        items = cast("list[Any]", value)
        return [GeneratedObjectData.model_validate(item) if isinstance(item, dict) else item for item in items]

    def __json_encode__(self) -> dict[str, Any]:  # ruff: ignore[bad-dunder-method-name] — kajson encoder hook, name fixed by kajson's protocol
        """The generation as plain JSON data, each object by its fields' aliases, so it decodes wherever its class is unknown."""
        return self.model_dump(mode="json", serialize_as_any=True, by_alias=True)
