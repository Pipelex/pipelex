from typing import Literal, Self

from pydantic import Field, model_validator
from typing_extensions import override

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenSize, SizeTier
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.pipe_machinery.validation import check_inputs_match_variables
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
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
        # An input counts as read when the prompt or the negative prompt reads it
        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()
        variable_paths: set[str] = set()
        for template_source, template_label in [(self.prompt, "prompt"), (self.negative_prompt, "negative_prompt")]:
            if template_source is None:
                continue
            variable_paths.update(
                self._read_variable_paths(template_source=template_source, template_label=template_label, declared_inputs=declared_inputs)
            )
        check_inputs_match_variables(
            declared_inputs=declared_inputs,
            variable_paths=variable_paths,
            reader="prompt or negative_prompt",
        )

    @classmethod
    def _read_variable_paths(cls, *, template_source: str, template_label: str, declared_inputs: set[str]) -> set[str]:
        """The dotted variable paths one template reads, internal names (starting with an underscore) excluded."""
        template_category = TemplateCategory.IMG_GEN_PROMPT
        try:
            preprocessed_template = preprocess_template(template_source, declared_inputs=declared_inputs)
        except TemplateSigilSyntaxError as exc:
            msg = f"Template sigil error in PipeImgGen {template_label}: {exc}"
            raise ValueError(msg) from exc
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse {template_label} template for PipeImgGen: {exc}"
            raise ValueError(msg) from exc
        full_paths = detect_jinja2_required_variables(
            template_category=template_category,
            template_source=preprocessed_template,
        )
        return {path for path in full_paths if not get_root_from_dotted_path(path).startswith("_")}

    @override
    def validate_output(self):
        pass
