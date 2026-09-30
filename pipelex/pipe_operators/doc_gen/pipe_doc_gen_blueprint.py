from typing import Literal, Self

from pydantic import Field, model_validator
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


def template_required_roots(*, template_source: str, template_category: TemplateCategory, declared_inputs: set[str], label: str) -> set[str]:
    """Check that a `PipeDocGen` template parses, and return the input names it reads.

    Sigils are rewritten first, exactly as PipeCompose does, so `$invoice` and `@invoice` count as reads of
    `invoice`. Raises `ValueError`, which pydantic turns into a validation error located on the blueprint.
    """
    try:
        preprocessed = preprocess_template(template_source, declared_inputs=declared_inputs)
    except TemplateSigilSyntaxError as exc:
        msg = f"Template sigil error in the PipeDocGen {label}: {exc}"
        raise ValueError(msg) from exc
    try:
        check_jinja2_parsing(template_source=preprocessed, template_category=template_category)
    except Jinja2TemplateSyntaxError as exc:
        msg = f"Could not parse the PipeDocGen {label}: {exc}"
        raise ValueError(msg) from exc
    roots: set[str] = set()
    for path in detect_jinja2_required_variables(template_category=template_category, template_source=preprocessed):
        root = get_root_from_dotted_path(path)
        if not root.startswith("_") and root != "place_holder":
            roots.add(root)
    return roots


class PipeDocGenBlueprint(PipeBlueprint):
    """Generate a document file from a method's structured result: a PDF, an Excel workbook, a Word document or a PowerPoint deck.

    It calls no AI model: it lays out or fills what its inputs already hold. With no template, the pipe lays its inputs
    out by itself (the auto-layout), for every format but `pptx`. `template` is an inline HTML and Jinja2 template, for
    `pdf` only; `template_file` is a path relative to the bundle's file: an `.html` for `pdf`, an `.xlsx` for `xlsx`, a
    `.docx` for `docx` and a `.pptx` for `pptx`, which `pptx` requires. `filename` is a Jinja expression over the
    inputs; the suffix is added. The output must be a single `Document`, or a concept refining it. `model` names the
    document engine that prints it, a model of the `doc_gen` family such as `reportlab-pdf` or `weasyprint-pdf`;
    without it, the model deck's default for the format and source prints it. Which engines a runtime has depends
    on its plugins: open Pipelex prints a `pdf` without a template on `reportlab-pdf`, and a runtime without the
    engine a step needs refuses the method when it loads.
    """

    type: Literal["PipeDocGen"] = "PipeDocGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    format: DocGenFormat = Field(strict=False)
    model: DocGenModelChoice | None = None
    template: str | None = None
    template_file: str | None = None
    filename: str | None = None

    @model_validator(mode="after")
    def validate_template_sources(self) -> Self:
        if self.template is not None and self.template_file is not None:
            msg = "PipeDocGen cannot have both 'template' and 'template_file': use one or the other."
            raise ValueError(msg)
        if self.template is not None and not self.format.is_template_html:
            msg = (
                f"PipeDocGen's inline 'template' is an HTML template, for the 'pdf' format only. "
                f"For '{self.format}', use 'template_file' with a {self.format.template_file_suffix} file"
                f"{', or no template for the auto-layout' if self.format.has_auto_layout else ''}."
            )
            raise ValueError(msg)
        if self.template_file is not None and not self.template_file.lower().endswith(self.format.template_file_suffix):
            msg = (
                f"PipeDocGen's 'template_file' for the '{self.format}' format must be a {self.format.template_file_suffix} file, "
                f"got '{self.template_file}'."
            )
            raise ValueError(msg)
        if not self.format.has_auto_layout and self.template_file is None:
            msg = (
                f"PipeDocGen's '{self.format}' format has no auto-layout: name the designed {self.format.template_file_suffix} "
                "file it fills with 'template_file'."
            )
            raise ValueError(msg)
        return self

    @override
    def validate_inputs(self):
        declared_inputs = set(self.input_names)
        if self.template is not None:
            self._check_roots_are_inputs(
                roots=template_required_roots(
                    template_source=self.template,
                    template_category=TemplateCategory.HTML,
                    declared_inputs=declared_inputs,
                    label="template",
                ),
                label="template",
            )
        if self.filename is not None:
            self._check_roots_are_inputs(
                roots=template_required_roots(
                    template_source=self.filename,
                    template_category=TemplateCategory.BASIC,
                    declared_inputs=declared_inputs,
                    label="filename",
                ),
                label="filename",
            )

    def _check_roots_are_inputs(self, *, roots: set[str], label: str):
        for root in sorted(roots):
            if root not in self.input_names:
                msg = f"Variable '{root}' in the PipeDocGen {label} is not in the inputs of the pipe."
                raise ValueError(msg)

    @override
    def validate_output(self):
        parsed_output = parse_concept_with_multiplicity(concept_ref_or_code=self.output)
        if parsed_output.multiplicity:
            msg = f"PipeDocGen produces one file: its output must be a single Document, or a concept refining Document. Current output: {self.output}"
            raise ValueError(msg)
