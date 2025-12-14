from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables


class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    prompt: str

    model: ImgGenModelChoice | None = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: AspectRatio | None = Field(default=None, strict=False)
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    background: Background | None = Field(default=None, strict=False)
    output_format: OutputFormat | None = Field(default=None, strict=False)

    @override
    def validate_inputs(self):
        # Get all required variables from prompt
        preprocessed_template = preprocess_template(self.prompt)
        try:
            required_variables = detect_jinja2_required_variables(
                template_category=TemplateCategory.IMG_GEN_PROMPT,
                template_source=preprocessed_template,
            )
        except Jinja2DetectVariablesError as exc:
            msg = f"Could not detect required variables in prompt for PipeImgGen: {exc}"
            raise ValueError(msg) from exc

        # Filter out internal variables that start with underscore
        required_variables = {var for var in required_variables if not var.startswith("_")}

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
