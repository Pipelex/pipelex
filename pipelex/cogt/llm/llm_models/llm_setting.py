from typing import Literal, Optional, Set, Union

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.cogt.exceptions import LLMSettingsValidationError
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_models.llm_prompting_target import LLMPromptingTarget
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.exceptions import ConfigValidationError


class LLMSetting(ConfigModel):
    llm_handle: str
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: Optional[int] = None
    prompting_target: Optional[LLMPromptingTarget] = Field(default=None, strict=False)

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

    @model_validator(mode="after")
    def validate_temperature(self) -> Self:
        if self.llm_handle.startswith("gemini") and self.temperature > 1:
            error_msg = f"Gemini LLMs such as '{self.llm_handle}' support temperatures up to 2 but we normalize between 0 and 1, \
                so you can't set a temperature of {self.temperature}"
            raise LLMSettingsValidationError(error_msg)
        return self

    def make_llm_job_params(self) -> LLMJobParams:
        return LLMJobParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=None,
        )


LLMSettingOrPresetId = Union[LLMSetting, str]


class LLMSettingChoices(ConfigModel):
    for_text: Optional[LLMSettingOrPresetId]
    for_object: Optional[LLMSettingOrPresetId]
    for_object_direct: Optional[LLMSettingOrPresetId]
    for_object_list: Optional[LLMSettingOrPresetId]
    for_object_list_direct: Optional[LLMSettingOrPresetId]

    def list_used_presets(self) -> Set[str]:
        return set(
            [
                setting
                for setting in [
                    self.for_text,
                    self.for_object,
                    self.for_object_direct,
                    self.for_object_list,
                    self.for_object_list_direct,
                ]
                if isinstance(setting, str)
            ]
        )

    @classmethod
    def make_completed_with_defaults(
        cls,
        for_text: Optional[LLMSettingOrPresetId] = None,
        for_object: Optional[LLMSettingOrPresetId] = None,
        for_object_direct: Optional[LLMSettingOrPresetId] = None,
        for_object_list: Optional[LLMSettingOrPresetId] = None,
        for_object_list_direct: Optional[LLMSettingOrPresetId] = None,
    ) -> Self:
        return cls(
            for_text=for_text,
            for_object=for_object,
            for_object_direct=for_object_direct,
            for_object_list=for_object_list,
            for_object_list_direct=for_object_list_direct,
        )
