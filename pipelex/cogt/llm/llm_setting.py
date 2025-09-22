from typing import Literal, Optional, Set, Union

from pydantic import Field, field_validator
from typing_extensions import Self

from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.tools.config.config_model import ConfigModel
from pipelex.tools.exceptions import ConfigValidationError


class LLMSetting(ConfigModel):
    llm_handle: str
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: Optional[int] = None
    prompting_target: Optional[PromptingTarget] = Field(default=None, strict=False)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def validate_max_tokens(cls, value: Union[int, Literal["auto"], None]) -> Optional[int]:
        if value is None:
            return None
        elif isinstance(value, str) and value == "auto":
            return None
        elif isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            return value
        else:
            raise ConfigValidationError(f'Invalid max_tokens shoubd be an int or "auto" but it is a {type(value)}: {value}')

    def make_llm_job_params(self) -> LLMJobParams:
        return LLMJobParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=None,
        )

    def desc(self) -> str:
        return (
            f"LLMSetting(llm_handle={self.llm_handle}, temperature={self.temperature}, "
            f"max_tokens={self.max_tokens}, prompting_target={self.prompting_target})"
        )


LLMChoice = Union[LLMSetting, str]


class LLMSettingChoicesDefaults(ConfigModel):
    for_text: LLMChoice
    for_object: LLMChoice


class LLMSettingChoices(ConfigModel):
    for_text: Optional[LLMChoice]
    for_object: Optional[LLMChoice]

    def list_choices(self) -> Set[str]:
        return set(
            [
                choice
                for choice in [
                    self.for_text,
                    self.for_object,
                ]
                if isinstance(choice, str)
            ]
        )

    @classmethod
    def make_completed_with_defaults(
        cls,
        for_text: Optional[LLMChoice] = None,
        for_object: Optional[LLMChoice] = None,
    ) -> Self:
        return cls(
            for_text=for_text,
            for_object=for_object,
        )
