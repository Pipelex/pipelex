from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pydantic import Field
from typing_extensions import Self

from pipelex.cogt.exceptions import LLMHandleNotFoundError
from pipelex.cogt.inference_backend.model_spec import InferenceModelSpec
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingChoicesDefaults, LLMSettingOrPresetId


class LLMDeckAbstract(ABC):
    llm_handles: Dict[str, InferenceModelSpec] = Field(default_factory=dict)
    llm_external_handles: List[str] = Field(default_factory=list)
    llm_presets: Dict[str, LLMSetting] = Field(default_factory=dict)
    llm_choice_defaults: LLMSettingChoicesDefaults
    llm_choice_overrides: LLMSettingChoices = LLMSettingChoices(
        for_text=None,
        for_object=None,
    )

    @abstractmethod
    def check_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId, is_disabled_allowed: bool = False):
        pass

    @abstractmethod
    def get_optional_inference_model(self, llm_handle: str) -> Optional[InferenceModelSpec]:
        pass

    def get_inference_model(self, llm_handle: str) -> InferenceModelSpec:
        if llm_model := self.get_optional_inference_model(llm_handle=llm_handle):
            return llm_model
        raise LLMHandleNotFoundError(f"LLM handle '{llm_handle}' not found in deck")

    @abstractmethod
    def get_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId) -> LLMSetting:
        pass

    # @abstractmethod
    # def find_llm_model(self, llm_handle: str) -> InferenceModelSpec:
    #     pass

    # @abstractmethod
    # def find_optional_llm_model(self, llm_handle: str) -> Optional[InferenceModelSpec]:
    #     pass

    @classmethod
    @abstractmethod
    def final_validate(cls, deck: Self):
        pass
