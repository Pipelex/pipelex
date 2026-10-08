from collections.abc import Mapping
from typing import NoReturn, Self

from pydantic import Field, PrivateAttr, field_validator, model_validator

from pipelex import log
from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key, parse_doc_gen_choice_key
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice, DocGenSetting
from pipelex.cogt.exceptions import (
    DocGenHandleNotFoundError,
    ExtractHandleNotFoundError,
    ImgGenHandleNotFoundError,
    JudgmentHandleNotFoundError,
    LLMHandleNotFoundError,
    ModelChoiceNotFoundError,
    ModelDeckPresetValidatonError,
    ModelNotFoundError,
    ModelWaterfallError,
    SearchHandleNotFoundError,
)
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice, JudgmentSetting
from pipelex.cogt.llm.llm_setting import (
    LLMModelChoice,
    LLMSetting,
    LLMSettingChoices,
    LLMSettingChoicesDefaults,
)
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_reference import (
    NAMESPACE_ALIAS,
    NAMESPACE_WATERFALL,
    SIGIL_WATERFALL,
    ModelReference,
    ModelReferenceKind,
    ensure_model_reference,
    write_model_handle,
)
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError
from pipelex.system.runtime import ProblemReaction
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
    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, SearchSetting] = Field(default_factory=dict)
    choice_default: SearchModelChoice


class DocGenDeckBlueprint(ConfigModel):
    """The document engines' deck: one default engine per format and source, keyed '<format>.<source>' ('pdf.layout')."""

    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, DocGenSetting] = Field(default_factory=dict)
    choice_defaults: dict[str, DocGenModelChoice] = Field(default_factory=dict)

    @field_validator("choice_defaults", mode="after")
    @classmethod
    def validate_choice_default_keys(cls, choice_defaults: dict[str, DocGenModelChoice]) -> dict[str, DocGenModelChoice]:
        for key in choice_defaults:
            parse_doc_gen_choice_key(key)
        return choice_defaults


class JudgmentDeckBlueprint(ConfigModel):
    """The judgment family's half of the deck.

    ``choice_default`` is optional here where every other family requires one, and the reason is
    that no judgment model is served by default: the judgment backend is one the user brings. A
    default that nothing serves boots cleanly and fails the first judgment that relies on it, and
    ``tests/unit/pipelex/kit/test_shipped_deck_defaults.py`` refuses a shipped default no kit
    backend declares. Absent says the honest thing: no model is the default, so a judgment names
    its own until one is served.
    """

    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    presets: dict[str, JudgmentSetting] = Field(default_factory=dict)
    choice_default: JudgmentModelChoice | None = None


class ModelDeckBlueprint(ConfigModel):
    llm: LLMDeckBlueprint
    extract: ExtractDeckBlueprint
    img_gen: ImgGenDeckBlueprint
    search: SearchDeckBlueprint
    # Optional, unlike the other families: a project whose deck predates it still boots, and only its
    # `PipeDocGen` steps are refused, naming the missing default, until `pipelex update` adds the deck file.
    doc_gen: DocGenDeckBlueprint = Field(default_factory=DocGenDeckBlueprint)
    # Defaulted where the other families are required: a deck installed before this family
    # existed has no judgment file, only `pipelex update` installs one, and its absence means
    # exactly what the kit's own empty section means — no judgment model.
    judgment: JudgmentDeckBlueprint = Field(default_factory=JudgmentDeckBlueprint)


class ModelDeck(ConfigModel):
    model_deck_config: ModelDeckConfig
    # The models the deck serves, by model type and handle: a handle names one model per model type.
    inference_models: ModelSpecIndex = Field(default_factory=ModelSpecIndex.make_empty)

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
    search_aliases: dict[str, str] = Field(default_factory=dict)
    search_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    search_presets: dict[str, SearchSetting] = Field(default_factory=dict)
    search_choice_default: SearchModelChoice

    # DocGen-specific
    doc_gen_aliases: dict[str, str] = Field(default_factory=dict)
    doc_gen_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    doc_gen_presets: dict[str, DocGenSetting] = Field(default_factory=dict)
    doc_gen_choice_defaults: dict[str, DocGenModelChoice] = Field(default_factory=dict)

    # Judgment-specific
    judgment_aliases: dict[str, str] = Field(default_factory=dict)
    judgment_waterfalls: dict[str, list[str]] = Field(default_factory=dict)
    judgment_presets: dict[str, JudgmentSetting] = Field(default_factory=dict)
    # Optional, unlike every other family's — see JudgmentDeckBlueprint for why.
    judgment_choice_default: JudgmentModelChoice | None = None

    def get_aliases_and_waterfalls_for_type(self, model_type: ModelType) -> tuple[dict[str, str], dict[str, list[str]]]:
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
            case ModelType.DOC_GEN:
                return self.doc_gen_aliases, self.doc_gen_waterfalls
            case ModelType.JUDGMENT:
                return self.judgment_aliases, self.judgment_waterfalls

    def get_presets_for_type(
        self, *, model_type: ModelType
    ) -> Mapping[str, LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | DocGenSetting | JudgmentSetting]:
        """Return the type-specific presets dictionary."""
        match model_type:
            case ModelType.LLM:
                return self.llm_presets
            case ModelType.TEXT_EXTRACTOR:
                return self.extract_presets
            case ModelType.IMG_GEN:
                return self.img_gen_presets
            case ModelType.SEARCH:
                return self.search_presets
            case ModelType.DOC_GEN:
                return self.doc_gen_presets
            case ModelType.JUDGMENT:
                return self.judgment_presets

    def is_bare_handle_resolvable(self, *, name: str, model_type: ModelType) -> bool:
        """Whether a bare model name resolves for this model type, as a pipe's `model` field may name it.

        The name resolves when the runner can call a model of that name of this type, among every
        model it can call and not only those the deck names; failing that, when the deck defines an
        alias of that name for this type, or a waterfall of that name while model fallback is on.
        The order is the one the run's lookup (`get_optional_inference_model`) reads a bare name in.
        The fallback gate is the validation's and the setting builders' (`get_*_setting`), which a
        pipe's field passes through before the run's lookup: that lookup itself also resolves a bare
        waterfall name while fallback is off, where a binding inside the deck names one. A model of
        that name served only as another type does not make it resolve, so a pipe naming it is refused
        when its bundle loads rather than when the run reaches it. The name is taken literally, so a
        `handle:` reference whose name starts with a sigil names no alias, waterfall or preset.
        """
        if self.inference_models.get(model_type=model_type, handle=name) is not None:
            return True
        aliases, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)
        if name in aliases:
            return True
        return self.model_deck_config.is_model_fallback_enabled and name in waterfalls

    def is_reference_defined(self, *, reference: ModelReference, model_type: ModelType) -> bool:
        """Whether a pipe of this model type may name this reference in its `model` field.

        This is the test a validation applies to the field: a preset, an alias or a waterfall is
        defined when the deck defines that name for the type, and a bare handle when it resolves
        by `is_bare_handle_resolvable`. It is a matter of names: a preset, an alias or a waterfall
        whose binding reaches no model the runner can call is still defined.
        """
        match reference.kind:
            case ModelReferenceKind.PRESET:
                return reference.name in self.get_presets_for_type(model_type=model_type)
            case ModelReferenceKind.ALIAS:
                aliases, _ = self.get_aliases_and_waterfalls_for_type(model_type)
                return reference.name in aliases
            case ModelReferenceKind.WATERFALL:
                _, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)
                return reference.name in waterfalls
            case ModelReferenceKind.HANDLE:
                return self.is_bare_handle_resolvable(name=reference.name, model_type=model_type)

    def unresolved_handle_sentence(self, *, name: str, model_type: ModelType) -> str:
        """The sentence refusing a bare handle that does not resolve for this model type.

        It names the handle and the type the field needs. When the deck serves a model of that name
        only as other types, it says so rather than calling the handle missing, without naming them.
        """
        served_types = self.inference_models.types_serving(handle=name)
        if served_types and model_type not in served_types:
            return f"Model handle '{name}' is served by the model deck, but not as {model_type.indefinite_description}"
        return f"Model handle '{name}' was not found in the model deck"

    def _unresolved_preset_model_sentence(self, *, preset_label: str, preset_id: str, model_reference: str, model_type: ModelType) -> str:
        """The sentence refusing a deck preset whose model does not resolve for the preset's type, naming the preset.

        A bare handle gets `unresolved_handle_sentence`, so a model the deck serves only as another type
        is named as such rather than as missing.
        """
        sentence = f"Model reference '{model_reference}' was not found in the model deck"
        ref: ModelReference | None
        try:
            ref = ModelReference.parse(model_reference)
        except ModelReferenceParseError:
            ref = None
        if ref is not None:
            match ref.kind:
                case ModelReferenceKind.HANDLE:
                    sentence = self.unresolved_handle_sentence(name=ref.name, model_type=model_type)
                case ModelReferenceKind.PRESET | ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL:
                    pass
        return f"{preset_label} preset '{preset_id}': {sentence}"

    def is_model_handle_defined(self, model_handle: str, *, model_type: ModelType) -> bool:
        """Check if a model handle is defined in the model deck for this model type.

        Handles prefixed references (e.g., @alias_name, ~waterfall_name) by parsing
        them and looking up the appropriate dictionary. A bare handle is defined when it
        resolves for this model type (`is_bare_handle_resolvable`): a model the deck serves
        only as another type does not define it.
        """
        ref = ModelReference.parse(model_handle)
        aliases, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)

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
                return self.is_bare_handle_resolvable(name=ref.name, model_type=model_type)

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

    def _warn_if_ambiguous_doc_gen(self, name: str) -> None:
        """Log a warning if a bare string handle matches presets/aliases/waterfalls."""
        matches: list[str] = []
        if name in self.doc_gen_presets:
            matches.append(f"doc gen preset (use ${name} or preset:{name})")
        if name in self.doc_gen_aliases:
            matches.append(f"alias (use @{name} or alias:{name})")
        if name in self.doc_gen_waterfalls:
            matches.append(f"waterfall (use ~{name} or waterfall:{name})")
        if matches:
            log.warning(
                f"Bare string '{name}' matches: {', '.join(matches)}. Using it as a direct model handle. Add explicit prefix to avoid ambiguity."
            )

    def _warn_if_ambiguous_judgment(self, name: str) -> None:
        """Log a warning if a bare string handle matches presets/aliases/waterfalls."""
        matches: list[str] = []
        if name in self.judgment_presets:
            matches.append(f"judgment preset (use ${name} or preset:{name})")
        if name in self.judgment_aliases:
            matches.append(f"alias (use @{name} or alias:{name})")
        if name in self.judgment_waterfalls:
            matches.append(f"waterfall (use ~{name} or waterfall:{name})")
        if matches:
            log.warning(
                f"Bare string '{name}' matches: {', '.join(matches)}. Using it as a direct model handle. Add explicit prefix to avoid ambiguity."
            )

    def _raise_handle_not_found_error(
        self,
        ref: ModelReference,
        *,
        model_type: ModelType,
        presets: dict[str, LLMSetting]
        | dict[str, ExtractSetting]
        | dict[str, ImgGenSetting]
        | dict[str, SearchSetting]
        | dict[str, DocGenSetting]
        | dict[str, JudgmentSetting],
    ) -> NoReturn:
        """Raise ModelChoiceNotFoundError with migration hints if applicable."""
        msg = self.unresolved_handle_sentence(name=ref.name, model_type=model_type)

        # Add migration hints if the name matches a preset, alias, or waterfall
        aliases, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)
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
            available_options=self.inference_models.handles_of_type(model_type=model_type),
        )

    def check_llm_choice(
        self,
        llm_choice: LLMModelChoice,
        *,
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
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.LLM):
                    return
                msg = self.unresolved_handle_sentence(name=ref.name, model_type=ModelType.LLM)
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.LLM,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.HANDLE,
                    available_options=self.inference_models.handles_of_type(model_type=ModelType.LLM),
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
                    # Keep the sigil, so the run resolves the waterfall itself and not a model or an alias sharing its name
                    return LLMSetting(model=f"{SIGIL_WATERFALL}{ref.name}", temperature=self.llm_default_temperature)
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
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.LLM):
                    return LLMSetting(model=write_model_handle(name=ref.name), temperature=self.llm_default_temperature)
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
                    return ExtractSetting(model=f"{SIGIL_WATERFALL}{ref.name}")
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
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.TEXT_EXTRACTOR):
                    return ExtractSetting(model=write_model_handle(name=ref.name))
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
                    return SearchSetting(model=alias_target)
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
                    return SearchSetting(model=f"{SIGIL_WATERFALL}{ref.name}")
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
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.SEARCH):
                    return SearchSetting(model=write_model_handle(name=ref.name))
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.SEARCH,
                    presets=self.search_presets,
                )

    def get_doc_gen_choice_default(self, *, doc_gen_format: DocGenFormat, source: DocGenSource) -> DocGenModelChoice | None:
        """The engine the deck prints this format from this source with when a step names none, or None when it names none either."""
        return self.doc_gen_choice_defaults.get(doc_gen_choice_key(doc_gen_format=doc_gen_format, source=source))

    def get_doc_gen_setting(self, *, doc_gen_choice: DocGenModelChoice) -> DocGenSetting:
        if isinstance(doc_gen_choice, DocGenSetting):
            return doc_gen_choice

        ref = ensure_model_reference(doc_gen_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if preset := self.doc_gen_presets.get(ref.name):
                    return preset
                msg = f"Doc gen preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.DOC_GEN,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.doc_gen_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if alias_target := self.doc_gen_aliases.get(ref.name):
                    return DocGenSetting(model=alias_target)
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.DOC_GEN,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.doc_gen_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.doc_gen_waterfalls:
                    return DocGenSetting(model=f"{SIGIL_WATERFALL}{ref.name}")
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.DOC_GEN,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.doc_gen_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                self._warn_if_ambiguous_doc_gen(ref.name)
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.DOC_GEN):
                    return DocGenSetting(model=write_model_handle(name=ref.name))
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.DOC_GEN,
                    presets=self.doc_gen_presets,
                )

    def get_judgment_setting(self, judgment_choice: JudgmentModelChoice) -> JudgmentSetting:
        if isinstance(judgment_choice, JudgmentSetting):
            return judgment_choice

        ref = ensure_model_reference(judgment_choice)
        match ref.kind:
            case ModelReferenceKind.PRESET:
                if preset := self.judgment_presets.get(ref.name):
                    return preset
                msg = f"Judgment preset '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.JUDGMENT,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.PRESET,
                    available_options=list(self.judgment_presets.keys()),
                )
            case ModelReferenceKind.ALIAS:
                if alias_target := self.judgment_aliases.get(ref.name):
                    return JudgmentSetting(model=alias_target)
                msg = f"Alias '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.JUDGMENT,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.ALIAS,
                    available_options=list(self.judgment_aliases.keys()),
                )
            case ModelReferenceKind.WATERFALL:
                if ref.name in self.judgment_waterfalls:
                    return JudgmentSetting(model=f"{SIGIL_WATERFALL}{ref.name}")
                msg = f"Waterfall '{ref.name}' was not found in the model deck"
                raise ModelChoiceNotFoundError(
                    message=msg,
                    model_type=ModelType.JUDGMENT,
                    model_choice=ref.raw,
                    reference_kind=ModelReferenceKind.WATERFALL,
                    available_options=list(self.judgment_waterfalls.keys()),
                )
            case ModelReferenceKind.HANDLE:
                self._warn_if_ambiguous_judgment(ref.name)
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.JUDGMENT):
                    return JudgmentSetting(model=write_model_handle(name=ref.name))
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.JUDGMENT,
                    presets=self.judgment_presets,
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
                    return ImgGenSetting(model=f"{SIGIL_WATERFALL}{ref.name}", quality=self.img_gen_default_quality)
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
                if self.is_bare_handle_resolvable(name=ref.name, model_type=ModelType.IMG_GEN):
                    return ImgGenSetting(model=write_model_handle(name=ref.name), quality=self.img_gen_default_quality)
                self._raise_handle_not_found_error(
                    ref=ref,
                    model_type=ModelType.IMG_GEN,
                    presets=self.img_gen_presets,
                )

    ############################################################
    # ModelDeck validations
    ############################################################

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
                msg = self._unresolved_preset_model_sentence(
                    preset_label="LLM", preset_id=llm_preset_id, model_reference=llm_setting.model, model_type=ModelType.LLM
                )
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
                msg = self._unresolved_preset_model_sentence(
                    preset_label="Image generation", preset_id=img_gen_preset_id, model_reference=img_gen_setting.model, model_type=ModelType.IMG_GEN
                )
                raise ImgGenHandleNotFoundError(
                    message=msg,
                    preset_id=img_gen_preset_id,
                    model_handle=img_gen_setting.model,
                )
        return self

    def validate_extract_presets(self) -> Self:
        for extract_preset_id, extract_setting in self.extract_presets.items():
            if not self.is_model_handle_defined(model_handle=extract_setting.model, model_type=ModelType.TEXT_EXTRACTOR):
                msg = self._unresolved_preset_model_sentence(
                    preset_label="Extract", preset_id=extract_preset_id, model_reference=extract_setting.model, model_type=ModelType.TEXT_EXTRACTOR
                )
                raise ExtractHandleNotFoundError(
                    message=msg,
                    preset_id=extract_preset_id,
                    model_handle=extract_setting.model,
                )
        return self

    def validate_search_presets(self) -> Self:
        for search_preset_id, search_setting in self.search_presets.items():
            if not self.is_model_handle_defined(model_handle=search_setting.model, model_type=ModelType.SEARCH):
                msg = self._unresolved_preset_model_sentence(
                    preset_label="Search", preset_id=search_preset_id, model_reference=search_setting.model, model_type=ModelType.SEARCH
                )
                raise SearchHandleNotFoundError(
                    message=msg,
                    preset_id=search_preset_id,
                    model_handle=search_setting.model,
                )
        return self

    def validate_doc_gen_presets(self) -> Self:
        for doc_gen_preset_id, doc_gen_setting in self.doc_gen_presets.items():
            if not self.is_model_handle_defined(model_handle=doc_gen_setting.model, model_type=ModelType.DOC_GEN):
                msg = self._unresolved_preset_model_sentence(
                    preset_label="Doc gen", preset_id=doc_gen_preset_id, model_reference=doc_gen_setting.model, model_type=ModelType.DOC_GEN
                )
                raise DocGenHandleNotFoundError(
                    message=msg,
                    preset_id=doc_gen_preset_id,
                    model_handle=doc_gen_setting.model,
                )
        return self

    def validate_judgment_presets(self) -> Self:
        for judgment_preset_id, judgment_setting in self.judgment_presets.items():
            if not self.is_model_handle_defined(model_handle=judgment_setting.model, model_type=ModelType.JUDGMENT):
                msg = self._unresolved_preset_model_sentence(
                    preset_label="Judgment", preset_id=judgment_preset_id, model_reference=judgment_setting.model, model_type=ModelType.JUDGMENT
                )
                raise JudgmentHandleNotFoundError(
                    message=msg,
                    preset_id=judgment_preset_id,
                    model_handle=judgment_setting.model,
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
        try:
            self.validate_doc_gen_presets()
        except DocGenHandleNotFoundError as exc:
            match self.model_deck_config.missing_presets_reaction:
                case ProblemReaction.RAISE:
                    msg = f"Failed to validate all DocGen presets: {exc}"
                    raise ModelDeckPresetValidatonError(
                        message=msg,
                        model_type=ModelType.DOC_GEN,
                        preset_id=exc.preset_id,
                        model_handle=exc.model_handle,
                    ) from exc
                case ProblemReaction.LOG:
                    log.warning(f"DocGen handle not found: {exc}")
                case ProblemReaction.NONE:
                    pass
        try:
            self.validate_judgment_presets()
        except JudgmentHandleNotFoundError as exc:
            match self.model_deck_config.missing_presets_reaction:
                case ProblemReaction.RAISE:
                    msg = f"Failed to validate all Judgment presets: {exc}"
                    raise ModelDeckPresetValidatonError(
                        message=msg,
                        model_type=ModelType.JUDGMENT,
                        preset_id=exc.preset_id,
                        model_handle=exc.model_handle,
                    ) from exc
                case ProblemReaction.LOG:
                    log.warning(f"Judgment handle not found: {exc}")
                case ProblemReaction.NONE:
                    pass

    def validate_inference_models(self):
        for model_spec in self.inference_models.all_specs():
            self.get_required_inference_model(model_handle=write_model_handle(name=model_spec.name), model_type=model_spec.model_type)

    def _get_enabled_backends(self) -> set[str]:
        """Return the set of backend names that have at least one model enabled."""
        return {model.backend_name for model in self.inference_models.all_specs()}

    def _resolve_waterfall(
        self,
        waterfall_name: str,
        *,
        fallback_list: list[str],
        model_type: ModelType,
        visited: frozenset[str],
        is_quiet: bool,
    ) -> InferenceModelSpec | None:
        """Resolve a waterfall to an inference model spec by trying each fallback in order.

        `visited` holds the aliases and waterfalls the lookup is already inside, so a step leading back
        to one of them ends as no model rather than recursing, and so does a step reaching a waterfall that
        runs out. A quiet lookup logs nothing and leaves the one-time fallback notice to the next lookup that
        falls back.
        """
        waterfall_key = f"{NAMESPACE_WATERFALL}{waterfall_name}"
        if waterfall_key in visited:
            if not is_quiet:
                log.warning(f"Circular model reference detected: waterfall '{waterfall_name}' leads back to itself")
            return None
        step_visited = visited | {waterfall_key}
        ideal_model_handle = fallback_list[0]
        if not is_quiet:
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
            try:
                inference_model = self._get_optional_inference_model(
                    model_handle=fallback,
                    model_type=model_type,
                    visited=step_visited,
                    is_quiet=is_quiet,
                )
            except ModelWaterfallError:
                # The step is a waterfall of its own, or reaches one, none of whose steps is served: that step
                # serves no model, and this waterfall goes on. Only the waterfall resolved at the top raises its
                # own error. The refusal of a fallback while fallbacks are disabled is not caught: it holds here too.
                if not is_quiet:
                    log.verbose(f"Waterfall '{waterfall_name}': step '{fallback}' reaches a waterfall none of whose models is served")
                inference_model = None
            if inference_model is not None:
                # Only log if we haven't logged for this waterfall_name before, and never from a quiet lookup,
                # which would otherwise use up the notice the next real fallback owes its run.
                if fallback_index > 0 and not is_quiet and waterfall_name not in self._logged_fallback_warnings:
                    # Waterfall success: we explain what happened in the logs
                    msg = (
                        f"Inference model fallback: '{ideal_model_handle}' was not found in the model deck, "
                        f"so it was replaced by '{fallback}'. "
                        f"As a consequence, the results of the method may not have the expected quality, "
                        f"and the method might fail due to feature limitations such as context window size, etc. "
                        f"Consider getting access to '{ideal_model_handle}'."
                    )
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

    def _resolve_alias(
        self,
        *,
        alias_name: str,
        alias_target: str,
        model_type: ModelType,
        visited: frozenset[str],
        is_quiet: bool,
    ) -> InferenceModelSpec | None:
        """Resolve an alias through its target, ending as no model when the target leads back to an alias or a waterfall being resolved."""
        alias_key = f"{NAMESPACE_ALIAS}{alias_name}"
        if alias_key in visited:
            if not is_quiet:
                log.warning(f"Circular model reference detected: alias '{alias_name}' leads back to itself")
            return None
        if not is_quiet:
            log.verbose(f"Alias '{alias_name}' -> '{alias_target}'")
        return self._get_optional_inference_model(
            model_handle=alias_target,
            model_type=model_type,
            visited=visited | {alias_key},
            is_quiet=is_quiet,
        )

    def get_optional_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec | None:
        """Get an inference model spec, resolving aliases and waterfalls as needed.

        Handles prefixed references (e.g., @alias_name, ~waterfall_name) by parsing
        them and looking up the appropriate dictionary.
        """
        return self._get_optional_inference_model(
            model_handle=model_handle,
            model_type=model_type,
            visited=frozenset(),
            is_quiet=False,
        )

    def peek_inference_model(self, *, model_handle: str, model_type: ModelType) -> InferenceModelSpec | None:
        """The model a run through `model_handle` would call now, or None when it would find none, looked up without side effects.

        It follows the lookup `get_optional_inference_model` makes, but logs nothing, leaves the one-time
        fallback notice to the next run that falls back, and answers None where that lookup raises for a
        waterfall none of whose usable steps the deck serves. The model reference check reads a run this way.
        """
        try:
            return self._get_optional_inference_model(
                model_handle=model_handle,
                model_type=model_type,
                visited=frozenset(),
                is_quiet=True,
            )
        except ModelNotFoundError:
            return None

    def _get_optional_inference_model(
        self,
        model_handle: str,
        *,
        model_type: ModelType,
        visited: frozenset[str],
        is_quiet: bool,
    ) -> InferenceModelSpec | None:
        """Internal implementation, with cycle detection across aliases and waterfalls.

        A reference is resolved by its kind: `@name` as the alias, `~name` as the waterfall, and a bare
        name as a model of this type, failing that as an alias of that name, failing that as a waterfall.
        `visited` holds the aliases and waterfalls the lookup is already inside, so a binding leading back
        to one of them ends as no model.
        """
        # Parse the model_handle to handle prefixed references
        try:
            ref = ModelReference.parse(model_handle)
        except ModelReferenceParseError:
            # Invalid model handle (empty string, etc.)
            return None
        aliases, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)

        match ref.kind:
            case ModelReferenceKind.ALIAS:
                if alias_target := aliases.get(ref.name):
                    return self._resolve_alias(
                        alias_name=ref.name,
                        alias_target=alias_target,
                        model_type=model_type,
                        visited=visited,
                        is_quiet=is_quiet,
                    )
                if not is_quiet:
                    log.verbose(f"Prefixed alias '{model_handle}' not found in aliases")
                return None
            case ModelReferenceKind.WATERFALL:
                if fallback_list := waterfalls.get(ref.name):
                    return self._resolve_waterfall(
                        waterfall_name=ref.name,
                        fallback_list=fallback_list,
                        model_type=model_type,
                        visited=visited,
                        is_quiet=is_quiet,
                    )
                if not is_quiet:
                    log.verbose(f"Prefixed waterfall '{model_handle}' not found in waterfalls")
                return None
            case ModelReferenceKind.PRESET:
                # Presets should not be resolved here - they should be looked up in presets directly
                if not is_quiet:
                    log.verbose(f"Preset reference '{model_handle}' cannot be resolved as an inference model")
                return None
            case ModelReferenceKind.HANDLE:
                # Direct handle - proceed with normal lookup
                pass

        # For direct handles (HANDLE kind), try the model served as this type first. A model of that name served
        # only as another type does not answer this lookup, which goes on to this type's aliases and waterfalls,
        # as the load-time check (`is_bare_handle_resolvable`) reads the same name.
        if inference_model := self.inference_models.get(model_type=model_type, handle=ref.name):
            return inference_model
        # Then try aliases (without prefix)
        if alias_target := aliases.get(ref.name):
            return self._resolve_alias(
                alias_name=ref.name,
                alias_target=alias_target,
                model_type=model_type,
                visited=visited,
                is_quiet=is_quiet,
            )
        # Finally try waterfalls (without prefix)
        if fallback_list := waterfalls.get(ref.name):
            return self._resolve_waterfall(
                waterfall_name=ref.name,
                fallback_list=fallback_list,
                model_type=model_type,
                visited=visited,
                is_quiet=is_quiet,
            )
        if is_quiet:
            return None
        if served_types := self.inference_models.types_serving(handle=ref.name):
            served_types_description = ", ".join(f"'{served_type}'" for served_type in served_types)
            log.warning(f"Model handle '{ref.name}' is served as {served_types_description} but was requested as '{model_type}'. Skipping.")
            return None
        log.verbose(f"Skipping model handle '{model_handle}' because it's was not found in the model deck, it could be an external plugin.")
        return None

    def is_handle_defined(self, model_handle: str, *, model_type: ModelType) -> bool:
        aliases, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)
        is_served = self.inference_models.get(model_type=model_type, handle=model_handle) is not None
        return is_served or model_handle in aliases or model_handle in waterfalls

    def _is_deck_model_reference(self, *, model_handle: str, model_type: ModelType) -> bool:
        """Whether this deck defines the model reference `model_handle` or names it in one of its own entries.

        Every setting the deck hands out names a reference the deck defines (a model it serves, an
        alias, a waterfall) or one its own entries name (a preset's model, an alias's target, a
        waterfall's fallback, a default or override written as a setting). A reference that is
        neither can only have reached a model lookup from outside the deck, from a model setting
        written inline in the method being run.
        """
        aliases, waterfalls = self.get_aliases_and_waterfalls_for_type(model_type)
        ref: ModelReference | None
        try:
            ref = ModelReference.parse(model_handle)
        except ModelReferenceParseError:
            # A value no reference parses from can still be the deck's own: a default or an
            # override written as a setting table is not parsed when the deck loads.
            ref = None
        if ref is not None:
            match ref.kind:
                case ModelReferenceKind.HANDLE:
                    # A model served as another type only is not defined for this lookup, which refuses it.
                    served_model = self.inference_models.get(model_type=model_type, handle=ref.name)
                    if served_model is not None or ref.name in aliases or ref.name in waterfalls:
                        return True
                case ModelReferenceKind.ALIAS:
                    if ref.name in aliases:
                        return True
                case ModelReferenceKind.WATERFALL:
                    if ref.name in waterfalls:
                        return True
                case ModelReferenceKind.PRESET:
                    # A preset is never a model a lookup can serve, whether or not the deck defines it.
                    pass

        named_references: set[str] = set(aliases.values())
        for fallback_list in waterfalls.values():
            named_references.update(fallback_list)
        deck_settings: list[LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | DocGenSetting | JudgmentSetting]
        deck_choices: list[
            LLMModelChoice | ExtractModelChoice | ImgGenModelChoice | SearchModelChoice | DocGenModelChoice | JudgmentModelChoice | None
        ]
        match model_type:
            case ModelType.LLM:
                deck_settings = list(self.llm_presets.values())
                deck_choices = [
                    self.llm_choice_defaults.for_text,
                    self.llm_choice_defaults.for_object,
                    self.llm_choice_overrides.for_text,
                    self.llm_choice_overrides.for_object,
                ]
            case ModelType.TEXT_EXTRACTOR:
                deck_settings = list(self.extract_presets.values())
                deck_choices = [self.extract_choice_default]
            case ModelType.IMG_GEN:
                deck_settings = list(self.img_gen_presets.values())
                deck_choices = [self.img_gen_choice_default]
            case ModelType.SEARCH:
                deck_settings = list(self.search_presets.values())
                deck_choices = [self.search_choice_default]
            case ModelType.DOC_GEN:
                deck_settings = list(self.doc_gen_presets.values())
                deck_choices = list(self.doc_gen_choice_defaults.values())
            case ModelType.JUDGMENT:
                deck_settings = list(self.judgment_presets.values())
                deck_choices = [self.judgment_choice_default]
        named_references.update(deck_setting.model for deck_setting in deck_settings)
        for deck_choice in deck_choices:
            if isinstance(deck_choice, (LLMSetting, ExtractSetting, ImgGenSetting, SearchSetting, DocGenSetting, JudgmentSetting)):
                named_references.add(deck_choice.model)
            elif isinstance(deck_choice, ModelReference):
                match deck_choice.kind:
                    case ModelReferenceKind.HANDLE:
                        # A default or override written as a handle reaches the lookup by its name,
                        # whatever prefix spells it.
                        named_references.add(deck_choice.name)
                    case ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL | ModelReferenceKind.PRESET:
                        # These reach the lookup as a name the deck defines or names above: an
                        # alias's target, a waterfall's own name or members, a preset's model.
                        pass
        return model_handle in named_references

    def get_required_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec:
        inference_model = self.get_optional_inference_model(model_handle=model_handle, model_type=model_type)
        if inference_model is None:
            # The message states the fact and nothing else: it reaches every surface a run failure
            # reaches, a hosted run's stored error included, whose reader has no local deck. The
            # remedy for a stale local deck is the local CLI's to give, in its model panel.
            msg = f"Model handle '{model_handle}' was not found in the model deck."
            model_not_found_error = ModelNotFoundError(message=msg, model_handle=model_handle)
            if not self._is_deck_model_reference(model_handle=model_handle, model_type=model_type):
                # The deck neither defines this reference for this type nor names it anywhere, so the
                # method being run named it. The load-time check refuses every reference it sees that
                # the deck does not serve as the type its pipe asks for, a model served only as another
                # type included, as `ModelChoiceNotFoundError`; what is left to reach here is a reference
                # in an inline model setting, which that check does not look into: the caller's fault.
                # The message and the next step name nothing but the caller's own reference, as the
                # method wrote it, and the type its pipe asked for, never the type the deck serves it
                # as. A reference the deck itself names but cannot serve (a preset or an alias target on
                # a backend that is not enabled) stays the deployment's fault, and stays redacted, with
                # no next step.
                model_not_found_error.as_caller_fault(
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_MODEL,
                        detail=f"Change the model '{model_handle}' to {model_type.indefinite_description} the model deck serves.",
                    )
                )
            raise model_not_found_error
        if self.inference_models.get(model_type=model_type, handle=model_handle) is None:
            log.verbose(f"Model handle '{model_handle}' is an alias which resolves to '{inference_model.name}'")
        return inference_model
