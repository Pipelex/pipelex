from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
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
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    background: Background | None = Field(default=None, strict=False)
    output_format: ImageFormat | None = Field(default=None, strict=False)

    @override
    def validate_inputs(self):
        # Get all required variables from prompt
        template_category = TemplateCategory.IMG_GEN_PROMPT
        preprocessed_template = preprocess_template(self.prompt)
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
        input_names: set[str] = set(self.inputs.keys()) if self.inputs else set()
        missing_variables: set[str] = required_variables - input_names

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
