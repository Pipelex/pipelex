from typing import List, Optional

from pydantic import Field

from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.usage.cost_category import CostsByCategoryDict
from pipelex.tools.config.config_model import ConfigModel


class InferenceModelSpec(ConfigModel):
    backend_name: str
    name: str
    sdk: str
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: CostsByCategoryDict = Field(strict=False)
    max_tokens: Optional[int]
    max_prompt_images: Optional[int]
    prompting_target: Optional[PromptingTarget] = Field(default=None, strict=False)
    constraints: List[ModelConstraints] = Field(default_factory=list)

    # TODO: investigate if this is needed
    is_system_prompt_supported: bool = True

    @property
    def tag(self) -> str:
        return f"[{self.sdk}@{self.backend_name}]({self.model_id})"

    @property
    def desc(self) -> str:
        return f"SDK[{self.sdk}]•Backend[{self.backend_name}]•Model[{self.model_id}]"

    @property
    def is_gen_object_supported(self) -> bool:
        return "structured" in self.outputs

    @property
    def is_vision_supported(self) -> bool:
        return "images" in self.inputs
