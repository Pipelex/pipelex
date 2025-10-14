from typing import Literal, Union

from pydantic import Field, field_validator

from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import Self


class LLMSetting(ConfigModel):
    model: str
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: int | None = None
    prompting_target: PromptingTarget | None = Field(default=None, strict=False)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def validate_max_tokens(cls, value: int | Literal["auto"] | None) -> int | None:
        if value is None or (isinstance(value, str) and value == "auto"):
            return None
        if isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            return value

    def make_llm_job_params(self) -> LLMJobParams:
        return LLMJobParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=None,
        )

    def desc(self) -> str:
        return (
            f"LLMSetting(llm_handle={self.model}, temperature={self.temperature}, "
            f"max_tokens={self.max_tokens}, prompting_target={self.prompting_target})"
        )


LLMModelChoice = Union[LLMSetting, str]


class LLMSettingChoicesDefaults(ConfigModel):
    for_text: LLMModelChoice
    for_object: LLMModelChoice


class LLMSettingChoices(ConfigModel):
    for_text: LLMModelChoice | None
    for_object: LLMModelChoice | None

    def list_choices(self) -> set[str]:
        return {c for c in (self.for_text, self.for_object) if isinstance(c, str)}

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
