from typing import Literal, Self

from pydantic import Field, model_validator
from typing_extensions import override

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenSize, SizeTier
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    prompt: str
    negative_prompt: str | None = None

    model: ImgGenModelChoice | None = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: AspectRatio | None = Field(default=None, strict=False)
    size: ImgGenSize | None = None
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    background: Background | None = Field(default=None, strict=False)
    output_format: ImageFormat | None = Field(default=None, strict=False)

    @model_validator(mode="after")
    def validate_size_vs_aspect_ratio(self) -> Self:
        if isinstance(self.size, ImageSize) and self.aspect_ratio is not None:
            msg = (
                f"PipeImgGen cannot set both an exact size ('{self.size.width}x{self.size.height}') and aspect_ratio "
                f"('{self.aspect_ratio}'): an exact size implies the aspect ratio. "
                f"Remove aspect_ratio, or use a size tier ({SizeTier.quoted_tokens()}) instead of an exact size."
            )
            raise ValueError(msg)
        return self

    @override
    def validate_inputs(self):
        # Get all required variables from prompt
        template_category = TemplateCategory.IMG_GEN_PROMPT
        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()
        try:
            preprocessed_template = preprocess_template(self.prompt, declared_inputs=declared_inputs)
        except TemplateSigilSyntaxError as exc:
            msg = f"Template sigil error in PipeImgGen prompt: {exc}"
            raise ValueError(msg) from exc
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse template for PipeImgGen: {exc}"
            raise ValueError(msg) from exc
        # Filter out internal variables that start with underscore
        full_paths = detect_jinja2_required_variables(
            template_category=template_category,
            template_source=preprocessed_template,
        )
        required_variables: set[str] = set()
        for path in full_paths:
            root = get_root_from_dotted_path(path)
            if not root.startswith("_"):
                required_variables.add(root)

        # Check that all required variables are in inputs
        missing_variables: set[str] = required_variables - declared_inputs

        if missing_variables:
            missing_vars_str = ", ".join(sorted(missing_variables))
            msg = (
                f"Missing input variable(s) in prompt template: {missing_vars_str}. "
                "These variables are used in the prompt but not declared in inputs."
            )
            raise ValueError(msg)

    @override
    def validate_output(self):
        pass
