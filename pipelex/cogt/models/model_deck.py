from pydantic import Field, PrivateAttr, field_validator, model_validator

from pipelex import log
from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import (
    ExtractHandleNotFoundError,
    ImgGenHandleNotFoundError,
    LLMHandleNotFoundError,
    LLMSettingsValidationError,
    ModelChoiceNotFoundError,
    ModelDeckPresetValidatonError,
    ModelDeckValidatonError,
    ModelNotFoundError,
    ModelWaterfallError,
)
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import (
    LLMModelChoice,
    LLMSetting,
    LLMSettingChoices,
    LLMSettingChoicesDefaults,
)
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.constraints import ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError
from pipelex.system.runtime import ProblemReaction
from pipelex.tools.misc.toml_utils import load_toml_from_path_if_exists
from pipelex.types import Self
from pipelex.urls import URLs

LLM_PRESET_DISABLED = "disabled"


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
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)

    llm: LLMDeckBlueprint
    extract: ExtractDeckBlueprint
    img_gen: ImgGenDeckBlueprint


class ModelDeck(ConfigModel):
    model_deck_config: ModelDeckConfig
    inference_models: dict[str, InferenceModelSpec] = Field(default_factory=dict)
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)

    # Track which model_handle fallback warnings have been logged to avoid duplicates
    _logged_fallback_warnings: set[str] = PrivateAttr(default_factory=set[str])

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
        all_handles: set[str] = set()
        all_handles.update(self.inference_models.keys())
        all_handles.update(self.aliases.keys())
        if self.model_deck_config.is_model_fallback_enabled:
            all_handles.update(self.waterfalls.keys())
        return model_handle in all_handles

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
        msg = f"LLM preset '{preset_id}' was not found in the model deck"
        raise ModelChoiceNotFoundError(message=msg, model_type=ModelType.LLM, model_choice=llm_choice)

    def get_llm_setting(self, llm_choice: LLMModelChoice) -> LLMSetting:
        if isinstance(llm_choice, LLMSetting):
            return llm_choice
        # it's a string, so either an llm preset id or an llm handle
        if llm_preset := self.llm_presets.get(llm_choice):
            return llm_preset
        if self.is_handle_defined(model_handle=llm_choice):
            return LLMSetting(model=llm_choice, temperature=0.7, max_tokens=None)
        msg = f"LLM choice '{llm_choice}' was not found in the model deck"
        raise ModelChoiceNotFoundError(message=msg, model_type=ModelType.LLM, model_choice=llm_choice)

    def get_extract_setting(self, extract_choice: ExtractModelChoice) -> ExtractSetting:
        if isinstance(extract_choice, ExtractSetting):
            return extract_choice
        # it's a string, so either an extract preset id or an extract handle
        if extract_preset := self.extract_presets.get(extract_choice):
            return extract_preset
        if self.is_handle_defined(model_handle=extract_choice):
            return ExtractSetting(model=extract_choice)
        msg = f"Extract choice '{extract_choice}' was not found in the model deck"
        raise ModelChoiceNotFoundError(message=msg, model_type=ModelType.TEXT_EXTRACTOR, model_choice=extract_choice)

    def get_img_gen_setting(self, img_gen_choice: ImgGenModelChoice) -> ImgGenSetting:
        if isinstance(img_gen_choice, ImgGenSetting):
            return img_gen_choice
        # it's a string, so either an img gen preset id or an img gen handle
        if img_gen_preset := self.img_gen_presets.get(img_gen_choice):
            return img_gen_preset
        if self.is_handle_defined(model_handle=img_gen_choice):
            return ImgGenSetting(model=img_gen_choice)
        msg = f"Image generation choice '{img_gen_choice}' was not found in the model deck"
        raise ModelChoiceNotFoundError(message=msg, model_type=ModelType.IMG_GEN, model_choice=img_gen_choice)

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
    # ModelDeck validations
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
        fixed_temperature = inference_model.valued_constraints.get(ValuedConstraint.FIXED_TEMPERATURE)
        if fixed_temperature is not None and llm_setting.temperature != fixed_temperature:
            msg = (
                f"LLM setting '{llm_setting.model}' has a temperature of {llm_setting.temperature}, "
                f"which is not allowed by the model's constraints: it must be {fixed_temperature}"
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
                enabled_backends = self._get_enabled_backends()
                msg = f"LLM handle '{llm_setting.model}' for llm preset '{llm_preset_id}' was not found in the model deck"
                raise LLMHandleNotFoundError(
                    message=msg,
                    preset_id=llm_preset_id,
                    model_handle=llm_setting.model,
                    enabled_backends=enabled_backends,
                )
        return self

    def validate_img_gen_presets(self) -> Self:
        for img_gen_preset_id, img_gen_setting in self.img_gen_presets.items():
            if not self.is_model_handle_defined(model_handle=img_gen_setting.model):
                msg = f"Image generation handle '{img_gen_setting.model}' for preset '{img_gen_preset_id}' was not found in the model deck"
                raise ImgGenHandleNotFoundError(
                    message=msg,
                    preset_id=img_gen_preset_id,
                    model_handle=img_gen_setting.model,
                )
        return self

    def validate_extract_presets(self) -> Self:
        for extract_preset_id, extract_setting in self.extract_presets.items():
            if not self.is_model_handle_defined(model_handle=extract_setting.model):
                msg = f"Extract handle '{extract_setting.model}' for extract preset '{extract_preset_id}' was not found in the model deck"
                raise ExtractHandleNotFoundError(
                    message=msg,
                    preset_id=extract_preset_id,
                    model_handle=extract_setting.model,
                )
        return self

    def validate_registered_models(self):
        self.validate_inference_models()
        try:
            self.validate_llm_presets()
        except LLMHandleNotFoundError as exc:
            match self.model_deck_config.missing_presets_reaction:
                case ProblemReaction.RAISE:
                    msg = f"Failed to validate all LLM presets: {exc}"
                    raise ModelDeckPresetValidatonError(
                        message=msg,
                        model_type=ModelType.LLM,
                        preset_id=exc.preset_id,
                        model_handle=exc.model_handle,
                        enabled_backends=exc.enabled_backends,
                    ) from exc
                case ProblemReaction.LOG:
                    log.warning(f"LLM handle not found: {exc}")
                case ProblemReaction.NONE:
                    pass
        try:
            self.validate_img_gen_presets()
        except ImgGenHandleNotFoundError as exc:
            match self.model_deck_config.missing_presets_reaction:
                case ProblemReaction.RAISE:
                    msg = f"Failed to validate all ImgGen presets: {exc}"
                    raise ModelDeckPresetValidatonError(
                        message=msg,
                        model_type=ModelType.IMG_GEN,
                        preset_id=exc.preset_id,
                        model_handle=exc.model_handle,
                    ) from exc
                case ProblemReaction.LOG:
                    log.warning(f"ImgGen handle not found: {exc}")
                case ProblemReaction.NONE:
                    pass
        try:
            self.validate_extract_presets()
        except ExtractHandleNotFoundError as exc:
            match self.model_deck_config.missing_presets_reaction:
                case ProblemReaction.RAISE:
                    msg = f"Failed to validate all Extract presets: {exc}"
                    raise ModelDeckPresetValidatonError(
                        message=msg,
                        model_type=ModelType.TEXT_EXTRACTOR,
                        preset_id=exc.preset_id,
                        model_handle=exc.model_handle,
                    ) from exc
                case ProblemReaction.LOG:
                    log.warning(f"Extract handle not found: {exc}")
                case ProblemReaction.NONE:
                    pass

    def validate_inference_models(self):
        for model_handle in self.inference_models:
            self.get_required_inference_model(model_handle=model_handle)

    def _get_enabled_backends(self) -> set[str]:
        """Return the set of backend names that have at least one model enabled."""
        return {model.backend_name for model in self.inference_models.values()}

    def _is_model_available_in_backend(self, model_handle: str, backend_name: str) -> bool | None:
        """Check if a model is available from a specific backend.

        This is a low-level check that reads the backend TOML file directly,
        so it works even if the backend is disabled. Best-effort: returns False
        if the file can't be read or parsed.

        Args:
            model_handle: The model handle/name to check for
            backend_name: The backend name (e.g., 'bedrock')

        Returns:
            True if the model is defined in the backend's TOML file, False otherwise
        """
        backend_file_path = f".pipelex/inference/backends/{backend_name}.toml"
        try:
            backend_toml = load_toml_from_path_if_exists(backend_file_path)
            if backend_toml is None:
                return None
            # Check if model_handle exists as a top-level key (section) in the TOML
            # Exclude special sections like 'defaults'
            return model_handle in backend_toml and model_handle != "defaults"
        except Exception:
            # Best-effort: if anything goes wrong, just return None
            return None

    def get_optional_inference_model(self, model_handle: str) -> InferenceModelSpec | None:
        if inference_model := self.inference_models.get(model_handle):
            return inference_model
        if alias := self.aliases.get(model_handle):
            log.verbose(f"Alias for '{model_handle}': {alias}")
            return self.get_optional_inference_model(model_handle=alias)
        if fallback_list := self.waterfalls.get(model_handle):
            ideal_model_handle = fallback_list[0]
            log.verbose(f"Fallback list for '{model_handle}': {fallback_list}")
            for fallback_index, fallback in enumerate(fallback_list):
                if fallback_index > 0 and not self.model_deck_config.is_model_fallback_enabled:
                    # Waterfall disabled, so we raise an error
                    fallback_list_str = " → ".join(fallback_list)
                    msg = (
                        f"Model handle '{model_handle}' is a waterfall (i.e. a list of models to try in order), which resolves to "
                        f"•[ {fallback_list_str} ]•, but model fallbacks are disabled "
                        f"so only the first item in the list, '{ideal_model_handle}', is acceptable but it was not found in the deck. "
                        f"You must enable model fallback in your .pipelex/pipelex.toml file to permit the following fallbacks, "
                        f"or enable a backend that supports '{ideal_model_handle}'. "
                    )
                    raise ModelNotFoundError(message=msg, model_handle=model_handle)
                if inference_model := self.get_optional_inference_model(model_handle=fallback):
                    if fallback_index > 0:
                        # Only log if we haven't logged for this model_handle before
                        if model_handle not in self._logged_fallback_warnings:
                            # Waterfall success: we explain what happened in the logs
                            msg = (
                                f"Inference model fallback: '{ideal_model_handle}' was not found in the model deck, "
                                f"so it was replaced by '{fallback}'. "
                                f"As a consequence, the results of the workflow may not have the expected quality, "
                                f"and the workflow might fail due to feature limitations such as context window size, etc. "
                                f"Consider getting access to '{ideal_model_handle}'."
                            )
                            enabled_backends = self._get_enabled_backends()
                            if PipelexBackend.GATEWAY not in enabled_backends and self._is_model_available_in_backend(
                                model_handle=ideal_model_handle, backend_name=PipelexBackend.GATEWAY
                            ):
                                msg += (
                                    f" Note that many high quality models such as '{ideal_model_handle}' are available "
                                    f"from the {PipelexBackend.GATEWAY.display_name} "
                                    f"and you can get free credits to try them out."
                                )
                                if PipelexBackend.LEGACY_INFERENCE in enabled_backends:
                                    msg += (
                                        f"\nAlso note that {PipelexBackend.LEGACY_INFERENCE.display_name} is deprecated "
                                        "and will be removed in the near future."
                                    )
                                msg += (
                                    f"\nPlease see our docs for more details about setting up "
                                    f"{PipelexBackend.GATEWAY.display_name} or other inference backends:\n{URLs.backend_provider_docs}"
                                )
                            else:
                                msg += f" Please see our docs for more details about setting up inference backends:\n{URLs.backend_provider_docs}"
                            log.info(msg)
                            # Mark this warning as logged for this model_handle
                            self._logged_fallback_warnings.add(model_handle)
                    return inference_model
            msg = (
                f"Model handle '{model_handle}' is a waterfall (i.e. a list of models to try in order) "
                "but none of the fallback models were found in the model deck"
            )
            raise ModelWaterfallError(message=msg, model_handle=model_handle, fallback_list=fallback_list)
        log.verbose(f"Skipping model handle '{model_handle}' because it's was not found in the model deck, it could be an external plugin.")
        return None

    def is_handle_defined(self, model_handle: str) -> bool:
        return model_handle in self.inference_models or model_handle in self.aliases or model_handle in self.waterfalls

    def get_required_inference_model(self, model_handle: str) -> InferenceModelSpec:
        inference_model = self.get_optional_inference_model(model_handle=model_handle)
        if inference_model is None:
            msg = (
                f"Model handle '{model_handle}' was not found in the model deck. "
                "Make sure it's defined in one of the model decks '.pipelex/inference/deck/*.toml'. "
                "If the model handle is indeed in the deck, make sure the required backend for this model to run is enabled in "
                "'.pipelex/inference/backends.toml' and that you have the necessary credentials. "
                "To find what backend is required for this model, look at the routing profile in '.pipelex/inference/routing_profiles.toml' "
                "Learn more about the inference backend system in the Pipelex documentation: "
                f"{URLs.backend_provider_docs}"
            )

            raise ModelNotFoundError(message=msg, model_handle=model_handle)
        if model_handle not in self.inference_models:
            log.verbose(f"Model handle '{model_handle}' is an alias which resolves to '{inference_model.name}'")
        return inference_model
