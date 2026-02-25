from typing import Annotated, Literal, Union

from pydantic import BeforeValidator, Field, WithJsonSchema, field_validator, model_validator

from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.models.model_reference import ModelReference, parse_model_reference
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import Self


class LLMSettingValueError(ValueError):
    pass


class LLMSetting(ConfigModel):
    model: str
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: Annotated[
        int | None,
        WithJsonSchema({"anyOf": [{"type": "integer"}, {"enum": ["auto"]}, {"type": "null"}], "default": None}),
    ] = None
    image_detail: PromptImageDetail | None = Field(default=None, strict=False)
    prompting_target: PromptingTarget | None = Field(default=None, strict=False)
    reasoning_effort: ReasoningEffort | None = Field(default=None, strict=False)
    reasoning_budget: int | None = Field(default=None, gt=0)
    description: str | None = None

    @field_validator("max_tokens", mode="before")
    @classmethod
    def validate_max_tokens(cls, value: int | Literal["auto"] | None) -> int | None:
        if value is None or (isinstance(value, str) and value == "auto"):
            return None
        if isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            return value

    @model_validator(mode="after")
    def validate_reasoning_effort_or_budget(self) -> Self:
        if self.reasoning_effort is not None and self.reasoning_budget is not None:
            msg = (
                "LLMSetting cannot have both 'reasoning_effort' and 'reasoning_budget' specified. "
                f"Use one or the other. reasoning_effort: {self.reasoning_effort}, reasoning_budget: {self.reasoning_budget}"
            )
            raise LLMSettingValueError(msg)
        return self

    def make_llm_job_params(self) -> LLMJobParams:
        return LLMJobParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            image_detail=self.image_detail,
            seed=None,
            reasoning_effort=self.reasoning_effort,
            reasoning_budget=self.reasoning_budget,
        )

    def desc(self) -> str:
        parts = [
            f"LLMSetting(llm_handle={self.model}",
            f"temperature={self.temperature}",
            f"max_tokens={self.max_tokens}",
            f"prompting_target={self.prompting_target}",
        ]
        if self.reasoning_effort is not None:
            parts.append(f"reasoning_effort={self.reasoning_effort}")
        if self.reasoning_budget is not None:
            parts.append(f"reasoning_budget={self.reasoning_budget}")
        return ", ".join(parts) + ")"


# LLMModelChoice accepts LLMSetting, ModelReference, or a string (which gets parsed to ModelReference)
# The BeforeValidator ensures that strings are automatically converted to ModelReference during validation
# ModelReference.model_serializer handles serialization back to the raw string value
LLMModelChoice = Union[
    LLMSetting,
    Annotated[str | ModelReference, BeforeValidator(parse_model_reference)],
]


class LLMSettingChoicesDefaults(ConfigModel):
    default_temperature: float = Field(..., ge=0, le=1)
    for_text: LLMModelChoice
    for_object: LLMModelChoice


class LLMSettingChoices(ConfigModel):
    for_text: LLMModelChoice | None
    for_object: LLMModelChoice | None

    def list_choice_references(self) -> set[ModelReference]:
        return {item for item in (self.for_text, self.for_object) if isinstance(item, ModelReference)}

    @classmethod
    def make_completed_with_defaults(
        cls,
        for_text: LLMModelChoice | None = None,
        for_object: LLMModelChoice | None = None,
    ) -> Self:
        return cls(
            for_text=for_text,
            for_object=for_object,
        )
