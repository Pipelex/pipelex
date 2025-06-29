from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.cogt.exceptions import LLMModelPlatformError
from pipelex.cogt.llm.llm_models.llm_model import LLMModel
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform


class LLMEngine(BaseModel):
    llm_platform: LLMPlatform
    llm_model: LLMModel

    @model_validator(mode="after")
    def validate_llm_platform(self) -> Self:
        if self.llm_platform not in self.llm_model.platform_llm_id:
            raise LLMModelPlatformError(
                f"Missing id for {self.llm_model.name_and_version} on platform '{self.llm_platform}', provided ids: {self.llm_model.platform_llm_id}"
            )
        return self

    @property
    def llm_id(self) -> str:
        return self.llm_model.platform_llm_id[self.llm_platform]

    @property
    def desc(self) -> str:
        return f"""llm name:         '{self.llm_model.llm_name}':
version:          '{self.llm_model.version}'
platform:         '{self.llm_platform}'
platform llm id:  '{self.llm_id}'"""

    @property
    def tag(self) -> str:
        return f"{self.llm_platform}:{self.llm_model.llm_name}:{self.llm_model.version}:id-[{self.llm_id}]"

    @property
    def is_gen_object_supported(self) -> bool:
        return self.llm_model.is_gen_object_supported and self.llm_platform.is_gen_object_supported
