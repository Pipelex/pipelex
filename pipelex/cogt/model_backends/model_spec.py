from instructor import Mode as InstructorMode
from pydantic import Field

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.usage.cost_category import CostsByCategoryDict
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class InferenceModelSpec(ConfigModel):
    backend_name: str
    name: str
    sdk: str
    model_type: ModelType = Field(strict=False)
    model_id: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    costs: CostsByCategoryDict = Field(strict=False)
    structure_method: StructureMethod | None = Field(default=None, strict=False)
    max_tokens: int | None
    max_prompt_images: int | None
    prompting_target: PromptingTarget | None = Field(default=None, strict=False)
    constraints: list[ModelConstraints] = Field(default_factory=empty_list_factory_of(ModelConstraints))

    @property
    def tag(self) -> str:
        return rf"{self.name} → \[{self.sdk}@{self.backend_name}]({self.model_id})"

    @property
    def desc(self) -> str:
        return rf"{self.name} → SDK\[{self.sdk}]•Backend\[{self.backend_name}]•Model\[{self.model_id}]"

    @property
    def is_gen_object_supported(self) -> bool:
        return "structured" in self.outputs

    @property
    def is_vision_supported(self) -> bool:
        return "images" in self.inputs

    def get_instructor_mode(self) -> InstructorMode | None:
        if self.structure_method:
            return self.structure_method.as_instructor_mode()
        else:
            return None
