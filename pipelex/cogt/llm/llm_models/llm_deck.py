from typing import Dict, Optional, Union

from pydantic import field_validator, model_validator
from typing_extensions import Self, override

from pipelex.cogt.exceptions import LLMDeckValidatonError, LLMHandleNotFoundError, LLMPresetNotFoundError, LLMSettingsValidationError
from pipelex.cogt.llm.llm_models.llm_deck_abstract import LLMDeckAbstract
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.llm.llm_models.llm_model import LLMModel
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingOrPresetId
from pipelex.hub import get_llm_models_provider
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.exceptions import ConfigValidationError

LLM_PRESET_DISABLED = "disabled"


class LLMDeck(LLMDeckAbstract, ConfigModel):
    ############################################################
    # LLMDeckAbstract overrides
    ############################################################

    @override
    def check_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId, is_disabled_allowed: bool = False):
        if isinstance(llm_setting_or_preset_id, LLMSetting):
            return
        preset_id: str = llm_setting_or_preset_id
        if preset_id in self.llm_presets:
            return
        if preset_id == LLM_PRESET_DISABLED and is_disabled_allowed:
            return
        raise LLMPresetNotFoundError(f"llm preset id '{preset_id}' not found in deck")

    @override
    def get_llm_engine_blueprint(self, llm_handle: str) -> LLMEngineBlueprint:
        the_engine_blueprint = self.llm_handles.get(llm_handle)
        if not the_engine_blueprint:
            raise LLMHandleNotFoundError(f"LLM Engine blueprint for llm_handle '{llm_handle}' not found in deck's engine blueprints")
        return the_engine_blueprint

    @override
    def get_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId) -> LLMSetting:
        if isinstance(llm_setting_or_preset_id, LLMSetting):
            return llm_setting_or_preset_id
        else:
            # it's a preset id
            the_llm_preset = self.llm_presets.get(llm_setting_or_preset_id)
            if not the_llm_preset:
                raise LLMPresetNotFoundError(f"LLM preset '{llm_setting_or_preset_id}' not found in deck")
            return the_llm_preset

    @override
    def find_llm_model(self, llm_handle: str) -> LLMModel:
        llm_models_provider = get_llm_models_provider()
        llm_engine_blueprint = self.llm_handles[llm_handle]
        llm_model = llm_models_provider.get_llm_model(
            llm_name=llm_engine_blueprint.llm_name,
            llm_version=llm_engine_blueprint.llm_version,
            llm_platform_choice=llm_engine_blueprint.llm_platform_choice,
        )
        return llm_model

    @override
    def find_optional_llm_model(self, llm_handle: str) -> Optional[LLMModel]:
        llm_models_provider = get_llm_models_provider()
        llm_engine_blueprint = self.llm_handles.get(llm_handle)
        if not llm_engine_blueprint:
            return None
        llm_model = llm_models_provider.get_optional_llm_model(
            llm_name=llm_engine_blueprint.llm_name,
            llm_version=llm_engine_blueprint.llm_version,
            llm_platform_choice=llm_engine_blueprint.llm_platform_choice,
        )
        return llm_model

    @override
    @classmethod
    def final_validate(cls, deck: Self):
        for llm_preset_id, llm_setting in deck.llm_presets.items():
            llm_model = deck.find_llm_model(llm_handle=llm_setting.llm_handle)
            try:
                cls._validate_llm_setting(llm_setting=llm_setting, llm_model=llm_model)
            except ConfigValidationError as exc:
                raise LLMDeckValidatonError(f"LLM preset '{llm_preset_id}' is invalid: {exc}")

    ############################################################
    #### LLMDeck concrete validations
    ############################################################

    @classmethod
    def _validate_llm_setting(cls, llm_setting: LLMSetting, llm_model: LLMModel):
        if llm_model.max_tokens is not None and (llm_setting_max_tokens := llm_setting.max_tokens):
            if llm_setting_max_tokens > llm_model.max_tokens:
                raise LLMSettingsValidationError(
                    (
                        f"LLM setting '{llm_setting.llm_handle}' has a max_tokens of {llm_setting_max_tokens}, "
                        f"which is greater than the model's max_tokens of {llm_model.max_tokens}"
                    )
                )
        match llm_model.llm_family:
            case LLMFamily.O_SERIES:
                if llm_setting.temperature != 1:
                    raise LLMSettingsValidationError(
                        f"O-series LLMs like '{llm_setting.llm_handle}' must have a temperature of 1, not {llm_setting.temperature}"
                    )
            case _:
                pass

    @field_validator("llm_handles", mode="before")
    @classmethod
    def validate_llm_handles(cls, value: Dict[str, Union[LLMEngineBlueprint, str]]) -> Dict[str, LLMEngineBlueprint]:
        the_dict: Dict[str, LLMEngineBlueprint] = {}
        for llm_handle, llm_engine_spec in value.items():
            if isinstance(llm_engine_spec, str):
                the_dict[llm_handle] = LLMEngineBlueprint(llm_name=llm_engine_spec)
            elif isinstance(llm_engine_spec, dict):
                the_dict[llm_handle] = LLMEngineBlueprint.model_validate(llm_engine_spec)
            else:
                raise ConfigValidationError(f"Invalid LLM engine blueprint for '{llm_handle}' is a {type(llm_engine_spec)}: {llm_engine_spec}")
        return the_dict

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

    def add_llm_name_as_handle_with_defaults(self, llm_name: str):
        if llm_name in self.llm_handles:
            raise ConfigValidationError(f"LLM engine blueprint for '{llm_name}' is already defined in llm deck's llm_handles")
        # TODO: sort the defaults by llm family
        self.llm_handles[llm_name] = LLMEngineBlueprint(llm_name=llm_name)

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
