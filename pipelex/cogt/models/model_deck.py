from typing import NoReturn

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
    SearchHandleNotFoundError,
)
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
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
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind, ModelReferenceParseError, ensure_model_reference
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError
from pipelex.system.runtime import ProblemReaction
from pipelex.tools.misc.toml_utils import load_toml_from_path_if_exists
from pipelex.types import Self
from pipelex.urls import URLs

LLM_PRESET_DISABLED = "disabled"


class LLMDeckBlueprint(ConfigModel):
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, LLMSetting] = Field(default_factory=dict)
    choice_defaults: LLMSettingChoicesDefaults
    choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )


class ExtractDeckBlueprint(ConfigModel):
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, ExtractSetting] = Field(default_factory=dict)
    choice_default: ExtractModelChoice


class ImgGenDeckBlueprint(ConfigModel):
    default_quality: Quality = Field(strict=False)
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, ImgGenSetting] = Field(default_factory=dict)
    choice_default: ImgGenModelChoice


class SearchDeckBlueprint(ConfigModel):
    default_depth: SearchDepth = Field(strict=False)
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, SearchSetting] = Field(default_factory=dict)
    choice_default: SearchModelChoice


class ModelDeckBlueprint(ConfigModel):
    llm: LLMDeckBlueprint
    extract: ExtractDeckBlueprint
    img_gen: ImgGenDeckBlueprint
    search: SearchDeckBlueprint


class ModelDeck(ConfigModel):
    model_deck_config: ModelDeckConfig
    inference_models: dict[str, InferenceModelSpec] = Field(default_factory=dict)

    # Track which model_handle fallback warnings have been logged to avoid duplicates
    _logged_fallback_warnings: set[str] = PrivateAttr(default_factory=set[str])

    # LLM-specific
    llm_default_temperature: float = Field(..., ge=0, le=1)
    llm_aliases: dict[str, str] = Field(default_factory=dict)
    llm_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    llm_presets: dict[str, LLMSetting] = Field(default_factory=dict)
    llm_choice_defaults: LLMSettingChoicesDefaults
    llm_choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )

    # Extract-specific
    extract_aliases: dict[str, str] = Field(default_factory=dict)
    extract_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    extract_presets: dict[str, ExtractSetting] = Field(default_factory=dict)
    extract_choice_default: ExtractModelChoice

    # ImgGen-specific
    img_gen_default_quality: Quality = Field(strict=False)
    img_gen_aliases: dict[str, str] = Field(default_factory=dict)
    img_gen_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    img_gen_presets: dict[str, ImgGenSetting] = Field(default_factory=dict)
    img_gen_choice_default: ImgGenModelChoice

    # Search-specific
    search_default_depth: SearchDepth = Field(strict=False)
    search_aliases: dict[str, str] = Field(default_factory=dict)
    search_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    search_presets: dict[str, SearchSetting] = Field(default_factory=dict)
    search_choice_default: SearchModelChoice

    def _get_aliases_and_waterfalls_for_type(self, model_type: ModelType) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Return the type-specific aliases and waterfalls dictionaries."""
        match model_type:
            case ModelType.LLM:
                return self.llm_aliases, self.llm_waterfalls
            case ModelType.TEXT_EXTRACTOR:
                return self.extract_aliases, self.extract_waterfalls
            case ModelType.IMG_GEN:
                return self.img_gen_aliases, self.img_gen_waterfalls
            case ModelType.SEARCH:
                return self.search_aliases, self.search_waterfalls

    def is_model_handle_defined(self, model_handle: str, model_type: ModelType) -> bool:
        """Check if a model handle is defined in the model deck.

        Handles prefixed references (e.g., @alias_name, ~waterfall_name) by parsing
        them and looking up the appropriate dictionary.
        """
        ref = ModelReference.parse(model_handle)
        aliases, waterfalls = self._get_aliases_and_waterfalls_for_type(model_type)

        match ref.kind:
            case ModelReferenceKind.ALIAS:
                return ref.name in aliases
            case ModelReferenceKind.WATERFALL:
                if self.model_deck_config.is_model_fallback_enabled:
                    return ref.name in waterfalls
                return False
            case ModelReferenceKind.PRESET:
                # Presets are handled separately, not as direct handles
                return False
            case ModelReferenceKind.HANDLE:
                # Direct handle lookup - check inference_models, aliases, and waterfalls
                all_handles: set[str] = set()
                all_handles.update(self.inference_models.keys())
                all_handles.update(aliases.keys())
                if self.model_deck_config.is_model_fallback_enabled:
                    all_handles.update(waterfalls.keys())
                return ref.name in all_handles

    def _warn_if_ambiguous_llm(self, name: str) -> None:
        """Log a warning if a bare string handle matches presets/aliases/waterfalls."""
        matches: list[str] = []
        if name in self.llm_presets:
            matches.append(f"LLM preset (use ${name} or preset:{name})")
        if name in self.llm_aliases:
            matches.append(f"alias (use @{name} or alias:{name})")
        if name in self.llm_waterfalls:
            matches.append(f"waterfall (use ~{name} or waterfall:{name})")
        if matches:
            log.warning(
                f"Bare string '{name}' matches: {', '.join(matches)}. Using it as a direct model handle. Add explicit prefix to avoid ambiguity."
            )

    def _warn_if_ambiguous_extract(self, name: str) -> None:
        """Log a warning if a bare string handle matches presets/aliases/waterfalls."""
        matches: list[str] = []
        if name in self.extract_presets:
            matches.append(f"extract preset (use ${name} or preset:{name})")
        if name in self.extract_aliases:
            matches.append(f"alias (use @{name} or alias:{name})")
        if name in self.extract_waterfalls:
            matches.append(f"waterfall (use ~{name} or waterfall:{name})")
        if matches:
            log.warning(
                f"Bare string '{name}' matches: {', '.join(matches)}. Using it as a direct model handle. Add explicit prefix to avoid ambiguity."
            )

    def _warn_if_ambiguous_img_gen(self, name: str) -> None:
        """Log a warning if a bare string handle matches presets/aliases/waterfalls."""
        matches: list[str] = []
        if name in self.img_gen_presets:
            matches.append(f"image generation preset (use ${name} or preset:{name})")
        if name in self.img_gen_aliases:
            matches.append(f"alias (use @{name} or alias:{name})")
        if name in self.img_gen_waterfalls:
            matches.append(f"waterfall (use ~{name} or waterfall:{name})")
        if matches:
            log.warning(
                f"Bare string '{name}' matches: {', '.join(matches)}. Using it as a direct model handle. Add explicit prefix to avoid ambiguity."
            )

    def _warn_if_ambiguous_search(self, name: str) -> None:
        """Log a warning if a bare string handle matches presets/aliases/waterfalls."""
        matches: list[str] = []
        if name in self.search_presets:
            matches.append(f"search preset (use ${name} or preset:{name})")
        if name in self.search_aliases:
            matches.append(f"alias (use @{name} or alias:{name})")
        if name in self.search_waterfalls:
            matches.append(f"waterfall (use ~{name} or waterfall:{name})")
        if matches:
            log.warning(
                f"Bare string '{name}' matches: {', '.join(matches)}. Using it as a direct model handle. Add explicit prefix to avoid ambiguity."
            )

    def _raise_handle_not_found_error(
        self,
        ref: ModelReference,
        model_type: ModelType,
        presets: dict[str, LLMSetting] | dict[str, ExtractSetting] | dict[str, ImgGenSetting] | dict[str, SearchSetting],
    ) -> NoReturn:
        """Raise ModelChoiceNotFoundError with migration hints if applicable."""
        msg = f"Model handle '{ref.name}' was not found in the model deck"

        # Add migration hints if the name matches a preset, alias, or waterfall
        aliases, waterfalls = self._get_aliases_and_waterfalls_for_type(model_type)
        hints: list[str] = []
        if ref.name in presets:
            hints.append(f"Did you mean preset '${ref.name}' or 'preset:{ref.name}'?")
        if ref.name in aliases:
            hints.append(f"Did you mean alias '@{ref.name}' or 'alias:{ref.name}'?")
        if ref.name in waterfalls:
            hints.append(f"Did you mean waterfall '~{ref.name}' or 'waterfall:{ref.name}'?")

        if hints:
            msg += "\n\nMigration hints:\n" + "\n".join(f"  - {hint}" for hint in hints)

        raise ModelChoiceNotFoundError(
            message=msg,
            model_type=model_type,
            model_choice=ref.raw,
            reference_kind=ModelReferenceKind.HANDLE,
            available_options=list(self.inference_models.keys()),
        )

    def check_llm_choice(
        self,
        llm_choice: LLMModelChoice,
        is_disabled_allowed: bool = False,
    ):
        if isinstance(llm_choice, LLMSetting):
            return

        ref = ensure_model_reference(llm_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if ref.name in self.llm_presets:
                    return
                if ref.name == LLM_PRESET_DISABLED and is_disabled_allowed:
                    return
                msg = f"LLM preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.llm_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if ref.name in self.llm_aliases:
                    return
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.llm_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.llm_waterfalls:
                    return
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.llm_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                self._warn_if_ambiguous_llm(ref.name)
                if self.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.LLM):
                    return
                msg = f"Model handle '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.HANDLE,
                    available_options=list(self.inference_models.keys()),
                )

    def get_llm_setting(self, llm_choice: LLMModelChoice) -> LLMSetting:
        if isinstance(llm_choice, LLMSetting):
            return llm_choice

        ref = ensure_model_reference(llm_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if preset := self.llm_presets.get(ref.name):
                    return preset
                msg = f"LLM preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.llm_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if alias_target := self.llm_aliases.get(ref.name):
                    # Resolve the alias to an LLM setting by using the target as a handle
                    return LLMSetting(model=alias_target, temperature=self.llm_default_temperature)
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.llm_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.llm_waterfalls:
                    # Use the waterfall name as the model handle (it will resolve via get_optional_inference_model)
                    return LLMSetting(model=ref.name, temperature=self.llm_default_temperature)
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.llm_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                # Strict: treat as direct model handle only
                self._warn_if_ambiguous_llm(ref.name)
                if self.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.LLM):
                    return LLMSetting(model=ref.name, temperature=self.llm_default_temperature)
                # Error includes migration hint if name matches preset/waterfall
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.LLM,
                    presets=self.llm_presets,
                )

    def get_extract_setting(self, extract_choice: ExtractModelChoice) -> ExtractSetting:
        if isinstance(extract_choice, ExtractSetting):
            return extract_choice

        ref = ensure_model_reference(extract_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if preset := self.extract_presets.get(ref.name):
                    return preset
                msg = f"Extract preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.TEXT_EXTRACTOR,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.extract_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if alias_target := self.extract_aliases.get(ref.name):
                    return ExtractSetting(model=alias_target)
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.TEXT_EXTRACTOR,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.extract_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.extract_waterfalls:
                    return ExtractSetting(model=ref.name)
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.TEXT_EXTRACTOR,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.extract_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                self._warn_if_ambiguous_extract(ref.name)
                if self.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.TEXT_EXTRACTOR):
                    return ExtractSetting(model=ref.name)
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.TEXT_EXTRACTOR,
                    presets=self.extract_presets,
                )

    def get_search_setting(self, search_choice: SearchModelChoice) -> SearchSetting:
        if isinstance(search_choice, SearchSetting):
            return search_choice

        ref = ensure_model_reference(search_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if preset := self.search_presets.get(ref.name):
                    return preset
                msg = f"Search preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.SEARCH,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.search_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if alias_target := self.search_aliases.get(ref.name):
                    return SearchSetting(model=alias_target, depth=self.search_default_depth)
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.SEARCH,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.search_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.search_waterfalls:
                    return SearchSetting(model=ref.name, depth=self.search_default_depth)
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.SEARCH,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.search_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                self._warn_if_ambiguous_search(ref.name)
                if self.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.SEARCH):
                    return SearchSetting(model=ref.name, depth=self.search_default_depth)
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.SEARCH,
                    presets=self.search_presets,
                )

    def get_img_gen_setting(self, img_gen_choice: ImgGenModelChoice) -> ImgGenSetting:
        if isinstance(img_gen_choice, ImgGenSetting):
            return img_gen_choice

        ref = ensure_model_reference(img_gen_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if preset := self.img_gen_presets.get(ref.name):
                    return preset
                msg = f"Image generation preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.IMG_GEN,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.img_gen_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if alias_target := self.img_gen_aliases.get(ref.name):
                    return ImgGenSetting(model=alias_target, quality=self.img_gen_default_quality)
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.IMG_GEN,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.img_gen_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.img_gen_waterfalls:
                    return ImgGenSetting(model=ref.name, quality=self.img_gen_default_quality)
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.IMG_GEN,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.img_gen_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                self._warn_if_ambiguous_img_gen(ref.name)
                if self.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.IMG_GEN):
                    return ImgGenSetting(model=ref.name, quality=self.img_gen_default_quality)
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.IMG_GEN,
                    presets=self.img_gen_presets,
                )

    @classmethod
    def final_validate(cls, deck: Self):
        for llm_preset_id, llm_setting in deck.llm_presets.items():
            inference_model = deck.get_required_inference_model(model_handle=llm_setting.model, model_type=ModelType.LLM)
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
        # Check if ModelReference has name "disabled" - this allows disabling the choice via explicit reference
        if isinstance(value.for_text, ModelReference) and value.for_text.name == LLM_PRESET_DISABLED:
            value = value.model_copy(update={"for_text": None})
        if isinstance(value.for_object, ModelReference) and value.for_object.name == LLM_PRESET_DISABLED:
            value = value.model_copy(update={"for_object": None})
        return value

    @model_validator(mode="after")
    def validate_llm_choice_overrides(self) -> Self:
        for llm_choice_ref in self.llm_choice_overrides.list_choice_references():
            self.check_llm_choice(llm_choice=llm_choice_ref)
        return self

    def validate_llm_presets(self) -> Self:
        for llm_preset_id, llm_setting in self.llm_presets.items():
            if not self.is_model_handle_defined(model_handle=llm_setting.model, model_type=ModelType.LLM):
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
            if not self.is_model_handle_defined(model_handle=img_gen_setting.model, model_type=ModelType.IMG_GEN):
                msg = f"Image generation handle '{img_gen_setting.model}' for preset '{img_gen_preset_id}' was not found in the model deck"
                raise ImgGenHandleNotFoundError(
                    message=msg,
                    preset_id=img_gen_preset_id,
                    model_handle=img_gen_setting.model,
                )
        return self

    def validate_extract_presets(self) -> Self:
        for extract_preset_id, extract_setting in self.extract_presets.items():
            if not self.is_model_handle_defined(model_handle=extract_setting.model, model_type=ModelType.TEXT_EXTRACTOR):
                msg = f"Extract handle '{extract_setting.model}' for extract preset '{extract_preset_id}' was not found in the model deck"
                raise ExtractHandleNotFoundError(
                    message=msg,
                    preset_id=extract_preset_id,
                    model_handle=extract_setting.model,
                )
        return self

    def validate_search_presets(self) -> Self:
        for search_preset_id, search_setting in self.search_presets.items():
            if not self.is_model_handle_defined(model_handle=search_setting.model, model_type=ModelType.SEARCH):
                msg = f"Search handle '{search_setting.model}' for search preset '{search_preset_id}' was not found in the model deck"
                raise SearchHandleNotFoundError(
                    message=msg,
                    preset_id=search_preset_id,
                    model_handle=search_setting.model,
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
        try:
            self.validate_search_presets()
        except SearchHandleNotFoundError as exc:
            match self.model_deck_config.missing_presets_reaction:
                case ProblemReaction.RAISE:
                    msg = f"Failed to validate all Search presets: {exc}"
                    raise ModelDeckPresetValidatonError(
                        message=msg,
                        model_type=ModelType.SEARCH,
                        preset_id=exc.preset_id,
                        model_handle=exc.model_handle,
                    ) from exc
                case ProblemReaction.LOG:
                    log.warning(f"Search handle not found: {exc}")
                case ProblemReaction.NONE:
                    pass

    def validate_inference_models(self):
        for model_handle, model_spec in self.inference_models.items():
            self.get_required_inference_model(model_handle=model_handle, model_type=model_spec.model_type)

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

    def _resolve_waterfall(
        self,
        waterfall_name: str,
        fallback_list: list[str],
        model_type: ModelType,
    ) -> InferenceModelSpec | None:
        """Resolve a waterfall to an inference model spec by trying each fallback in order."""
        ideal_model_handle = fallback_list[0]
        log.verbose(f"Fallback list for '{waterfall_name}': {fallback_list}")
        for fallback_index, fallback in enumerate(fallback_list):
            if fallback_index > 0 and not self.model_deck_config.is_model_fallback_enabled:
                # Waterfall disabled, so we raise an error
                fallback_list_str = " → ".join(fallback_list)
                msg = (
                    f"Model handle '{waterfall_name}' is a waterfall (i.e. a list of models to try in order), which resolves to "
                    f"•[ {fallback_list_str} ]•, but model fallbacks are disabled "
                    f"so only the first item in the list, '{ideal_model_handle}', is acceptable but it was not found in the deck. "
                    f"You must enable model fallback in your .pipelex/pipelex.toml file to permit the following fallbacks, "
                    f"or enable a backend that supports '{ideal_model_handle}'. "
                )
                raise ModelNotFoundError(message=msg, model_handle=waterfall_name)
            if inference_model := self.get_optional_inference_model(model_handle=fallback, model_type=model_type):
                if fallback_index > 0:
                    # Only log if we haven't logged for this waterfall_name before
                    if waterfall_name not in self._logged_fallback_warnings:
                        # Waterfall success: we explain what happened in the logs
                        msg = (
                            f"Inference model fallback: '{ideal_model_handle}' was not found in the model deck, "
                            f"so it was replaced by '{fallback}'. "
                            f"As a consequence, the results of the method may not have the expected quality, "
                            f"and the method might fail due to feature limitations such as context window size, etc. "
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
                        # Mark this warning as logged for this waterfall_name
                        self._logged_fallback_warnings.add(waterfall_name)
                return inference_model
        msg = (
            f"Model handle '{waterfall_name}' is a waterfall (i.e. a list of models to try in order) "
            "but none of the fallback models were found in the model deck"
        )
        raise ModelWaterfallError(message=msg, model_handle=waterfall_name, fallback_list=fallback_list)

    def get_optional_inference_model(self, model_handle: str, model_type: ModelType) -> InferenceModelSpec | None:
        """Get an inference model spec, resolving aliases and waterfalls as needed.

        Handles prefixed references (e.g., @alias_name, ~waterfall_name) by parsing
        them and looking up the appropriate dictionary.
        """
        return self._get_optional_inference_model(
            model_handle=model_handle,
            model_type=model_type,
            _visited=frozenset(),
        )

    def _get_optional_inference_model(
        self,
        model_handle: str,
        model_type: ModelType,
        _visited: frozenset[str],
    ) -> InferenceModelSpec | None:
        """Internal implementation with cycle detection for alias resolution."""
        # Parse the model_handle to handle prefixed references
        try:
            ref = ModelReference.parse(model_handle)
        except ModelReferenceParseError:
            # Invalid model handle (empty string, etc.)
            return None
        aliases, waterfalls = self._get_aliases_and_waterfalls_for_type(model_type)

        # Handle prefixed alias reference (e.g., @best-gpt)
        match ref.kind:
            case ModelReferenceKind.ALIAS:
                if alias_target := aliases.get(ref.name):
                    log.verbose(f"Prefixed alias '{model_handle}' -> '{alias_target}'")
                    if alias_target in _visited:
                        log.error(f"Circular alias detected: '{model_handle}' -> '{alias_target}'")
                        return None
                    return self._get_optional_inference_model(
                        model_handle=alias_target,
                        model_type=model_type,
                        _visited=_visited | {model_handle},
                    )
                log.verbose(f"Prefixed alias '{model_handle}' not found in aliases")
                return None
            case ModelReferenceKind.WATERFALL:
                if fallback_list := waterfalls.get(ref.name):
                    log.verbose(f"Prefixed waterfall '{model_handle}' -> {fallback_list}")
                    return self._resolve_waterfall(
                        waterfall_name=ref.name,
                        fallback_list=fallback_list,
                        model_type=model_type,
                    )
                log.verbose(f"Prefixed waterfall '{model_handle}' not found in waterfalls")
                return None
            case ModelReferenceKind.PRESET:
                # Presets should not be resolved here - they should be looked up in presets directly
                log.verbose(f"Preset reference '{model_handle}' cannot be resolved as an inference model")
                return None
            case ModelReferenceKind.HANDLE:
                # Direct handle - proceed with normal lookup
                pass

        # For direct handles (HANDLE kind), try inference_models first
        if inference_model := self.inference_models.get(ref.name):
            if inference_model.model_type != model_type:
                log.warning(f"Model handle '{ref.name}' has type '{inference_model.model_type}' but was requested as '{model_type}'. Skipping.")
                return None
            return inference_model
        # Then try aliases (without prefix)
        if alias := aliases.get(ref.name):
            log.verbose(f"Alias for '{model_handle}': {alias}")
            if alias in _visited:
                log.warning(f"Circular alias detected: '{model_handle}' -> '{alias}'")
                return None
            return self._get_optional_inference_model(
                model_handle=alias,
                model_type=model_type,
                _visited=_visited | {model_handle},
            )
        # Finally try waterfalls (without prefix)
        if fallback_list := waterfalls.get(ref.name):
            return self._resolve_waterfall(
                waterfall_name=ref.name,
                fallback_list=fallback_list,
                model_type=model_type,
            )
        log.verbose(f"Skipping model handle '{model_handle}' because it's was not found in the model deck, it could be an external plugin.")
        return None

    def is_handle_defined(self, model_handle: str, model_type: ModelType) -> bool:
        aliases, waterfalls = self._get_aliases_and_waterfalls_for_type(model_type)
        return model_handle in self.inference_models or model_handle in aliases or model_handle in waterfalls

    def get_required_inference_model(self, model_handle: str, model_type: ModelType) -> InferenceModelSpec:
        inference_model = self.get_optional_inference_model(model_handle=model_handle, model_type=model_type)
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
