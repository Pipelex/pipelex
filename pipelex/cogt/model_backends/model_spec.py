from typing import Dict, List, Optional

from pydantic import Field

from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.model_backends.cost_category import CostCategory
from pipelex.tools.config.config_model import ConfigModel


class InferenceModelSpec(ConfigModel):
    backend_name: str
    name: str
    sdk: str
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: Dict[CostCategory, float] = Field(strict=False)
    max_tokens: Optional[int]
    max_prompt_images: Optional[int]

    # TODO: investigate if this is needed
    is_system_prompt_supported: bool = True

    @property
    def tag(self) -> str:
        return f"[{self.sdk}][{self.backend_name}][{self.model_id}]"

    @property
    def desc(self) -> str:
        return f"SDK[{self.sdk}]•Backend[{self.backend_name}]•Model[{self.model_id}]"

    @property
    def is_gen_object_supported(self) -> bool:
        return "structured" in self.outputs

    @property
    def is_vision_supported(self) -> bool:
        return "images" in self.inputs

    @property
    def llm_family(self) -> LLMFamily:
        last_part = self.model_id.split("/")[-1]
        return LLMFamily(last_part.split("-")[0])
