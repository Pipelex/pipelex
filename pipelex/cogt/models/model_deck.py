from typing import Union

from pydantic import Field, field_validator, model_validator

from pipelex import log
from pipelex.cogt.exceptions import (
    ExtractChoiceNotFoundError,
    ExtractHandleNotFoundError,
    ImgGenChoiceNotFoundError,
    ImgGenHandleNotFoundError,
    LLMChoiceNotFoundError,
    LLMHandleNotFoundError,
    LLMSettingsValidationError,
    ModelDeckValidatonError,
    ModelNotFoundError,
)
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import (
    LLMModelChoice,
    LLMSetting,
    LLMSettingChoices,
    LLMSettingChoicesDefaults,
)
from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError
from pipelex.types import Self

LLM_PRESET_DISABLED = "disabled"

Waterfall = Union[str, list[str]]


class LLMDeckBlueprint(ConfigModel):
    presets: dict[str, LLMSetting] = Field(default_factory=dict)
    choice_defaults: LLMSettingChoicesDefaults
    choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )


class ExtractDeckBlueprint(ConfigModel):
    presets: dict[str, ExtractSetting] = Field(default_factory=dict)
    choice_default: ExtractModelChoice


class ImgGenDeckBlueprint(ConfigModel):
    presets: dict[str, ImgGenSetting] = Field(default_factory=dict)
    choice_default: ImgGenModelChoice


class ModelDeckBlueprint(ConfigModel):
    aliases: dict[str, Waterfall] = Field(default_factory=dict)

    llm: LLMDeckBlueprint
    extract: ExtractDeckBlueprint
    img_gen: ImgGenDeckBlueprint


class ModelDeck(ConfigModel):
    inference_models: dict[str, InferenceModelSpec] = Field(default_factory=dict)
    aliases: dict[str, Waterfall] = Field(default_factory=dict)

    llm_presets: dict[str, LLMSetting] = Field(default_factory=dict)
    llm_choice_defaults: LLMSettingChoicesDefaults
    llm_choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )

    extract_presets: dict[str, ExtractSetting] = Field(default_factory=dict)
    extract_choice_default: ExtractModelChoice

    img_gen_presets: dict[str, ImgGenSetting] = Field(default_factory=dict)
    img_gen_choice_default: ImgGenModelChoice

    def is_model_handle_defined(self, model_handle: str) -> bool:
        return model_handle in self.inference_models or model_handle in self.aliases

    def check_llm_choice(
        self,
        llm_choice: LLMModelChoice,
        is_disabled_allowed: bool = False,
    ):
        if isinstance(llm_choice, LLMSetting):
            return
        preset_id: str = llm_choice
        if preset_id in self.llm_presets:
            return
        if preset_id == LLM_PRESET_DISABLED and is_disabled_allowed:
            return
        msg = f"llm preset id '{preset_id}' not found in deck"
        raise LLMChoiceNotFoundError(msg)

    def get_llm_setting(self, llm_choice: LLMModelChoice) -> LLMSetting:
        if isinstance(llm_choice, LLMSetting):
            return llm_choice
        # it's a string, so either an llm preset id or an llm handle
        if llm_preset := self.llm_presets.get(llm_choice):
            return llm_preset
        if self.is_handle_defined(model_handle=llm_choice):
            return LLMSetting(model=llm_choice, temperature=0.7, max_tokens=None)
        msg = f"LLM choice '{llm_choice}' not found in deck"
        raise LLMChoiceNotFoundError(msg)

    def get_extract_setting(self, extract_choice: ExtractModelChoice) -> ExtractSetting:
        if isinstance(extract_choice, ExtractSetting):
            return extract_choice
        # it's a string, so either an extract preset id or an extract handle
        if extract_preset := self.extract_presets.get(extract_choice):
            return extract_preset
        if self.is_handle_defined(model_handle=extract_choice):
            return ExtractSetting(model=extract_choice)
        msg = f"Extract choice '{extract_choice}' not found in deck"
        raise ExtractChoiceNotFoundError(msg)

    def get_img_gen_setting(self, img_gen_choice: ImgGenModelChoice) -> ImgGenSetting:
        if isinstance(img_gen_choice, ImgGenSetting):
            return img_gen_choice
        # it's a string, so either an img gen preset id or an img gen handle
        if img_gen_preset := self.img_gen_presets.get(img_gen_choice):
            return img_gen_preset
        if self.is_handle_defined(model_handle=img_gen_choice):
            return ImgGenSetting(model=img_gen_choice)
        msg = f"Image generation choice '{img_gen_choice}' not found in deck"
        raise ImgGenChoiceNotFoundError(msg)

    @classmethod
    def final_validate(cls, deck: Self):
        for llm_preset_id, llm_setting in deck.llm_presets.items():
            inference_model = deck.get_required_inference_model(model_handle=llm_setting.model)
            try:
                cls._validate_llm_setting(llm_setting=llm_setting, inference_model=inference_model)
            except ConfigValidationError as exc:
                msg = f"LLM preset '{llm_preset_id}' is invalid: {exc}"
                raise ModelDeckValidatonError(msg) from exc

    ############################################################
    #### ModelDeck validations
    ############################################################

    @classmethod
    def _validate_llm_setting(cls, llm_setting: LLMSetting, inference_model: InferenceModelSpec):
        if inference_model.max_tokens is not None and (llm_setting_max_tokens := llm_setting.max_tokens):
            if llm_setting_max_tokens > inference_model.max_tokens:
                msg = (
                    f"LLM setting '{llm_setting.model}' has a max_tokens of {llm_setting_max_tokens}, "
                    f"which is greater than the model's max_tokens of {inference_model.max_tokens}"
                )
                raise LLMSettingsValidationError(msg)
        if ModelConstraints.TEMPERATURE_MUST_BE_1 in inference_model.constraints and llm_setting.temperature != 1:
            msg = (
                f"LLM setting '{llm_setting.model}' has a temperature of {llm_setting.temperature}, "
                f"which is not allowed by the model's constraints: it must be 1"
            )
            raise LLMSettingsValidationError(msg)

    @field_validator("llm_choice_defaults", mode="after")
    @classmethod
    def validate_llm_choice_defaults(cls, llm_choice_defaults: LLMSettingChoices) -> LLMSettingChoices:
        if llm_choice_defaults.for_text is None:
            msg = "llm_choice_defaults.for_text cannot be None"
            raise ConfigValidationError(msg)
        if llm_choice_defaults.for_object is None:
            msg = "llm_choice_defaults.for_object cannot be None"
            raise ConfigValidationError(msg)
        return llm_choice_defaults

    @field_validator("llm_choice_overrides", mode="after")
    @classmethod
    def validate_llm_choice_disabled_overrides(cls, value: LLMSettingChoices) -> LLMSettingChoices:
        if value.for_text == LLM_PRESET_DISABLED:
            value.for_text = None
        if value.for_object == LLM_PRESET_DISABLED:
            value.for_object = None
        return value

    @model_validator(mode="after")
    def validate_llm_choice_overrides(self) -> Self:
        for llm_preset_id in self.llm_choice_overrides.list_choice_strings():
            self.check_llm_choice(llm_choice=llm_preset_id)
        return self

    def validate_llm_presets(self) -> Self:
        for llm_preset_id, llm_setting in self.llm_presets.items():
            if not self.is_model_handle_defined(model_handle=llm_setting.model):
                enabled_backends = {model.backend_name for model in self.inference_models.values()}
                msg = (
                    f"llm_handle '{llm_setting.model}' for llm_preset '{llm_preset_id}' not found in deck. "
                    f"The enabled backends are {enabled_backends}. "
                    f"And the llm_handle '{llm_setting.model}' is not found in any of the enabled backends. Here are the solutions:\n "
                    "1 - Add it to your enabled backends if possible\n "
                    "2 - Enable a backend that supports this llm_handle "
                )
                raise LLMHandleNotFoundError(msg)
        return self

    def validate_img_gen_presets(self) -> Self:
        for img_gen_preset_id, img_gen_setting in self.img_gen_presets.items():
            if not self.is_model_handle_defined(model_handle=img_gen_setting.model):
                msg = f"img_gen_handle '{img_gen_setting.model}' for img_gen_preset '{img_gen_preset_id}' not found in deck"
                raise ImgGenHandleNotFoundError(msg)
        return self

    def validate_extract_presets(self) -> Self:
        for extract_preset_id, extract_setting in self.extract_presets.items():
            if not self.is_model_handle_defined(model_handle=extract_setting.model):
                msg = f"extract_handle '{extract_setting.model}' for extract_preset '{extract_preset_id}' not found in deck"
                raise ExtractHandleNotFoundError(msg)
        return self

    def validate_registered_models(self):
        self.validate_inference_models()
        self.validate_llm_presets()
        self.validate_img_gen_presets()
        self.validate_extract_presets()

    def validate_inference_models(self):
        for model_handle in self.inference_models:
            self.get_required_inference_model(model_handle=model_handle)

    def get_optional_inference_model(self, model_handle: str) -> InferenceModelSpec | None:
        if inference_model := self.inference_models.get(model_handle):
            return inference_model
        if redirection := self.aliases.get(model_handle):
            log.verbose(f"Redirection for '{model_handle}': {redirection}")
            if isinstance(redirection, str):
                alias_list = [redirection]
            else:
                alias_list = redirection
            for alias in alias_list:
                if inference_model := self.get_optional_inference_model(model_handle=alias):
                    return inference_model
        log.warning(f"Skipping model handle '{model_handle}' because it's not found in deck, it could be an external plugin.")
        return None

    def is_handle_defined(self, model_handle: str) -> bool:
        return model_handle in self.inference_models or model_handle in self.aliases

    def get_required_inference_model(self, model_handle: str) -> InferenceModelSpec:
        inference_model = self.get_optional_inference_model(model_handle=model_handle)
        if inference_model is None:
            msg = (
                f"Model handle '{model_handle}' not found in deck. "
                "Make sure its defined in the model decks '.pipelex/inference/deck/base_deck.toml' or '.pipelex/inference/deck/overrides.toml'. "
                "If the model handle is indeed in the deck, make sure the required backend for this model to run is enabled in "
                "'.pipelex/inference/backends.toml' and that you have the necessary credentials."
                "To find what backend is required for this model, look at the routing profile in .pipelex/inference/routing_profiles.toml. "
                "Learn more about the inference backend system in the Pipelex documentation: "
                "https://docs.pipelex.com/pages/configuration/config-technical/inference-backend-config/"
            )

            raise ModelNotFoundError(msg)
        if model_handle not in self.inference_models:
            log.verbose(f"Model handle '{model_handle}' is an alias which resolves to '{inference_model.name}'")
        return inference_model
