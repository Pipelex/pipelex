from typing import Dict, List, Optional

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.cogt.exceptions import LLMDeckValidatonError, LLMHandleNotFoundError, LLMPresetNotFoundError, LLMSettingsValidationError
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingChoicesDefaults, LLMSettingOrPresetId
from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.config.config_model import ConfigModel
from pipelex.tools.exceptions import ConfigValidationError

LLM_PRESET_DISABLED = "disabled"

Waterfall = List[str]


class LLMDeckBlueprint(ConfigModel):
    aliases: Dict[str, str | Waterfall] = Field(default_factory=dict)
    llm_presets: Dict[str, LLMSetting] = Field(default_factory=dict)
    llm_choice_defaults: LLMSettingChoicesDefaults
    llm_choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )


class LLMDeck(ConfigModel):
    llm_handles: Dict[str, InferenceModelSpec] = Field(default_factory=dict)
    llm_presets: Dict[str, LLMSetting] = Field(default_factory=dict)
    llm_choice_defaults: LLMSettingChoicesDefaults
    llm_choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )

    def get_all_inference_models(self) -> Dict[str, InferenceModelSpec]:
        return self.llm_handles

    def check_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId, is_disabled_allowed: bool = False):
        if isinstance(llm_setting_or_preset_id, LLMSetting):
            return
        preset_id: str = llm_setting_or_preset_id
        if preset_id in self.llm_presets:
            return
        if preset_id == LLM_PRESET_DISABLED and is_disabled_allowed:
            return
        raise LLMPresetNotFoundError(f"llm preset id '{preset_id}' not found in deck")

    def get_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId) -> LLMSetting:
        if isinstance(llm_setting_or_preset_id, LLMSetting):
            return llm_setting_or_preset_id
        else:
            # it's a preset id
            the_llm_preset = self.llm_presets.get(llm_setting_or_preset_id)
            if not the_llm_preset:
                raise LLMPresetNotFoundError(f"LLM preset '{llm_setting_or_preset_id}' not found in deck")
            return the_llm_preset

    @classmethod
    def final_validate(cls, deck: Self):  # pyright: ignore[reportIncompatibleMethodOverride]
        for llm_preset_id, llm_setting in deck.llm_presets.items():
            inference_model = deck.get_inference_model(llm_handle=llm_setting.llm_handle)
            try:
                cls._validate_llm_setting(llm_setting=llm_setting, inference_model=inference_model)
            except ConfigValidationError as exc:
                raise LLMDeckValidatonError(f"LLM preset '{llm_preset_id}' is invalid: {exc}")

    ############################################################
    #### LLMDeck validations
    ############################################################

    @classmethod
    def _validate_llm_setting(cls, llm_setting: LLMSetting, inference_model: InferenceModelSpec):
        if inference_model.max_tokens is not None and (llm_setting_max_tokens := llm_setting.max_tokens):
            if llm_setting_max_tokens > inference_model.max_tokens:
                raise LLMSettingsValidationError(
                    (
                        f"LLM setting '{llm_setting.llm_handle}' has a max_tokens of {llm_setting_max_tokens}, "
                        f"which is greater than the model's max_tokens of {inference_model.max_tokens}"
                    )
                )
        if ModelConstraints.TEMPERATURE_MUST_BE_1 in inference_model.constraints and llm_setting.temperature != 1:
            raise LLMSettingsValidationError(
                f"LLM setting '{llm_setting.llm_handle}' has a temperature of {llm_setting.temperature}, "
                f"which is not allowed by the model's constraints: it must be 1"
            )

    # @field_validator("llm_handles", mode="before")
    # @classmethod
    # def validate_llm_handles(cls, value: Dict[str, Union[LLMEngineBlueprint, str]]) -> Dict[str, LLMEngineBlueprint]:
    #     the_dict: Dict[str, LLMEngineBlueprint] = {}
    #     for llm_handle, llm_engine_spec in value.items():
    #         if isinstance(llm_engine_spec, str):
    #             the_dict[llm_handle] = LLMEngineBlueprint(llm_name=llm_engine_spec)
    #         elif isinstance(llm_engine_spec, dict):
    #             the_dict[llm_handle] = LLMEngineBlueprint.model_validate(llm_engine_spec)
    #         else:
    #             raise ConfigValidationError(f"Invalid LLM engine blueprint for '{llm_handle}' is a {type(llm_engine_spec)}: {llm_engine_spec}")
    #     return the_dict

    @field_validator("llm_choice_defaults", mode="after")
    @classmethod
    def validate_llm_choice_defaults(cls, llm_choice_defaults: LLMSettingChoices) -> LLMSettingChoices:
        if llm_choice_defaults.for_text is None:
            raise ConfigValidationError("llm_choice_defaults.for_text cannot be None")
        if llm_choice_defaults.for_object is None:
            raise ConfigValidationError("llm_choice_defaults.for_object cannot be None")
        return llm_choice_defaults

    @field_validator("llm_choice_overrides", mode="after")
    @classmethod
    def validate_llm_choice_overrides(cls, value: LLMSettingChoices) -> LLMSettingChoices:
        if value.for_text == LLM_PRESET_DISABLED:
            value.for_text = None
        if value.for_object == LLM_PRESET_DISABLED:
            value.for_object = None
        return value

    # def add_llm_name_as_handle_with_defaults(self, llm_name: str):
    #     if llm_name in self.llm_handles:
    #         raise ConfigValidationError(f"LLM engine blueprint for '{llm_name}' is already defined in llm deck's llm_handles")
    #     # TODO: sort the defaults by llm family
    #     self.llm_handles[llm_name] = LLMEngineBlueprint(llm_name=llm_name)

    def validate_llm_presets(self) -> Self:
        for llm_preset_id, llm_setting in self.llm_presets.items():
            if llm_setting.llm_handle not in self.llm_handles:
                raise LLMHandleNotFoundError(f"llm_handle '{llm_setting.llm_handle}' for llm_preset '{llm_preset_id}' not found in deck")
        return self

    @model_validator(mode="after")
    def validate_llm_setting_overrides(self) -> Self:
        self._validate_llm_choices(llm_choices=self.llm_choice_overrides)
        return self

    def _validate_llm_choices(self, llm_choices: LLMSettingChoices):
        for llm_setting in llm_choices.list_used_presets():
            self.check_llm_setting(llm_setting_or_preset_id=llm_setting)
        return

    def get_optional_inference_model(self, llm_handle: str) -> Optional[InferenceModelSpec]:
        return self.llm_handles.get(llm_handle)

    def get_inference_model(self, llm_handle: str) -> InferenceModelSpec:
        if inference_model := self.get_optional_inference_model(llm_handle=llm_handle):
            return inference_model
        else:
            raise LLMHandleNotFoundError(f"LLM handle '{llm_handle}' not found in deck")
