from typing import TYPE_CHECKING, Any, Final

from pydantic import Field, model_validator
from typing_extensions import Self

from pipelex.cogt.img_gen.img_gen_model_rules import ImgGenModelRules
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostsByCategoryDict
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.filetype_utils import IMAGE_FORMAT_KEY
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of

if TYPE_CHECKING:
    from instructor import Mode as InstructorMode


# The file formats a model spec's `inputs` may declare, as the format keys every format check compares
# (see `format_key_from_mime_type`). An LLM's vision flag stays spelled `images`, outside this vocabulary.
_EXTRACT_FILE_FORMATS: Final[frozenset[str]] = frozenset({"pdf", "docx", "pptx", "xlsx", "html", "md", "csv", "txt", "vtt", "eml", IMAGE_FORMAT_KEY})
_LLM_DOCUMENT_FORMATS: Final[frozenset[str]] = frozenset({"pdf", "docx", "pptx", "xlsx", "html"})


class InferenceModelSpec(ConfigModel):
    backend_name: str
    name: str
    sdk: str
    variant: str | None = None
    model_type: ModelType = Field(strict=False)
    model_id: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    costs: CostsByCategoryDict = Field(strict=False)
    structure_method: StructureMethod | None = Field(default=None, strict=False)
    thinking_mode: ThinkingMode = Field(strict=False)
    max_tokens: int | None
    max_prompt_images: int | None
    listed_constraints: list[ListedConstraint] = Field(default_factory=empty_list_factory_of(ListedConstraint))
    valued_constraints: dict[ValuedConstraint, Any] = Field(default_factory=empty_dict_factory_of(ValuedConstraint))
    extra_headers: dict[str, str] | None = None
    rules: ImgGenModelRules | None = None
    endpoint_path: str | None = None

    @model_validator(mode="after")
    def validate_thinking_budget_bounds(self) -> Self:
        bounds: dict[ValuedConstraint, int] = {}
        for constraint in (ValuedConstraint.MIN_THINKING_BUDGET, ValuedConstraint.MAX_THINKING_BUDGET):
            value = self.valued_constraints.get(constraint)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                msg = f"Model '{self.name}' declares {constraint}={value!r}, which must be a non-negative integer"
                raise ValueError(msg)
            bounds[constraint] = value
        min_budget = bounds.get(ValuedConstraint.MIN_THINKING_BUDGET)
        max_budget = bounds.get(ValuedConstraint.MAX_THINKING_BUDGET)
        if min_budget is not None and max_budget is not None and min_budget > max_budget:
            msg = f"Model '{self.name}' declares min_thinking_budget={min_budget} above max_thinking_budget={max_budget}"
            raise ValueError(msg)
        return self

    @property
    def min_thinking_budget(self) -> int | None:
        """The smallest manual thinking budget the provider accepts for this model, when it declares one."""
        return self.valued_constraints.get(ValuedConstraint.MIN_THINKING_BUDGET)

    @property
    def max_thinking_budget(self) -> int | None:
        """The largest manual thinking budget the provider accepts for this model, when it declares one."""
        return self.valued_constraints.get(ValuedConstraint.MAX_THINKING_BUDGET)

    @property
    def accepts_temperature(self) -> bool:
        """Whether the provider takes a temperature for this model: every LLM worker omits it when the model lists `temperature_unsupported`."""
        return ListedConstraint.TEMPERATURE_UNSUPPORTED not in self.listed_constraints

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

    @property
    def is_pdf_supported_for_extract(self) -> bool:
        return "pdf" in self.inputs

    @property
    def is_image_supported_for_extract(self) -> bool:
        return "image" in self.inputs

    @property
    def is_web_page_supported_for_extract(self) -> bool:
        return "web_page" in self.inputs

    @property
    def is_caption_supported_for_extract(self) -> bool:
        return "captions" in self.outputs

    @property
    def readable_formats_for_extract(self) -> set[str]:
        """The file formats this extractor reads, as format keys: its declared pdf, docx, pptx, xlsx, html, md, csv, txt, vtt, eml and image.

        `web_page` is not among them: a web-page model fetches its page itself, from a URL, so it is
        not a format a file is checked against.
        """
        return set(self.inputs) & _EXTRACT_FILE_FORMATS

    @property
    def supported_document_types(self) -> set[str]:
        """The document formats this LLM reads, as format keys: its declared pdf, docx, pptx, xlsx and html."""
        return set(self.inputs) & _LLM_DOCUMENT_FORMATS

    @property
    def is_document_supported(self) -> bool:
        """Check if any document type is supported for LLM input."""
        return bool(self.supported_document_types)

    @property
    def is_img2img_supported(self) -> bool:
        """Check if this model supports image-to-image generation (input images)."""
        return "images" in self.inputs

    def get_instructor_mode(self) -> "InstructorMode | None":
        if self.structure_method:
            return self.structure_method.as_instructor_mode()
        else:
            return None
