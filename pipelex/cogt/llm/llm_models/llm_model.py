from typing import Dict, Optional, Set

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from pipelex.cogt.exceptions import LLMModelDefinitionError
from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.token_category import TokenCostsByCategoryDict

LATEST_VERSION_NAME = "latest"
DISABLED_PLATFORM_NAME = "disabled"


class LLMModel(BaseModel):
    default_platform: LLMPlatform
    llm_family: LLMFamily
    llm_name: str
    version: str
    is_gen_object_supported: bool
    is_vision_supported: bool = False
    # TODO: add skill regarding live online data access
    cost_per_million_tokens_usd: Optional[TokenCostsByCategoryDict] = None
    platform_llm_id: Dict[LLMPlatform, str] = Field(..., min_length=1)
    max_tokens: Optional[int] = None

    max_prompt_images: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def check_vision_and_nb_images(self) -> Self:
        if self.is_vision_supported and self.max_prompt_images and self.max_prompt_images < 1:
            raise LLMModelDefinitionError("If vision is True, max_prompt_images must be >= 1 or not set")
        if not self.is_vision_supported and self.max_prompt_images and self.max_prompt_images > 0:
            raise LLMModelDefinitionError("If vision is False, max_prompt_images must be 0 or not set")
        return self

    @property
    def name_and_version(self) -> str:
        return f"{self.llm_name}/{self.version}"

    @property
    def name_and_version_and_platform(self) -> str:
        return f"{self.llm_name}/{self.version}/{self.default_platform}"

    @property
    def desc(self) -> str:
        return f"{self.llm_family}/{self.llm_name}/{self.version}/{self.default_platform}"

    @property
    def is_system_prompt_supported(self) -> bool:
        return self.llm_family != LLMFamily.O_SERIES or self.llm_name == "o1"

    @property
    def supported_platforms(self) -> Set[LLMPlatform]:
        return set(self.platform_llm_id.keys())

    @property
    def enabled_platforms(self) -> Set[LLMPlatform]:
        return set([key for key, value in self.platform_llm_id.items() if value != DISABLED_PLATFORM_NAME])
