from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pydantic import Field
from typing_extensions import Self

from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_model import LLMModel
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingChoicesDefaults, LLMSettingOrPresetId


class LLMDeckAbstract(ABC):
    llm_handles: Dict[str, LLMEngineBlueprint] = Field(default_factory=dict)
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
    def get_llm_engine_blueprint(self, llm_handle: str) -> LLMEngineBlueprint:
        pass

    @abstractmethod
    def get_llm_setting(self, llm_setting_or_preset_id: LLMSettingOrPresetId) -> LLMSetting:
        pass

    @abstractmethod
    def find_llm_model(self, llm_handle: str) -> LLMModel:
        pass

    @abstractmethod
    def find_optional_llm_model(self, llm_handle: str) -> Optional[LLMModel]:
        pass

    @classmethod
    @abstractmethod
    def final_validate(cls, deck: Self):
        pass
