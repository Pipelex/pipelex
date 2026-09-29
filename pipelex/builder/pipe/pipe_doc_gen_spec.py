from typing import TYPE_CHECKING, Literal

from pydantic import Field
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint
from pipelex.tools.misc.pretty import require_rich_for_rendering

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable


class PipeDocGenSpec(PipeSpec):
    """Spec for the PipeDocGen operator, which generates a document file from its inputs and calls no model.

    With no template, it lays the inputs out by itself: a `pdf` step without a template is what open Pipelex
    prints, and a `Markdown` input comes out formatted. A `pdf` with an HTML template, and the `xlsx`, `docx`
    and `pptx` formats, need the Pipelex document generation plugin, and a runtime without it refuses them when
    the method loads.

    Validation Rules:
        - the output must be a single Document, or a concept refining Document.
        - `template` (inline HTML and Jinja2) is for `pdf` only; `template_file` names a file beside the bundle
          whose suffix matches the format (`.html`, `.xlsx`, `.docx`, `.pptx`); never both.
        - `pptx` needs a `template_file`.
    """

    type: Literal["PipeDocGen"] = "PipeDocGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    format: DocGenFormat = Field(strict=False, description="The file format to generate: pdf, xlsx, docx or pptx.")
    template: str | None = Field(
        default=None,
        description="An inline HTML and Jinja2 template, for pdf only. Omit it for the auto-layout of the inputs.",
    )
    template_file: str | None = Field(
        default=None,
        description="A template file beside the bundle, relative to its file: .html for pdf, .xlsx, .docx or .pptx.",
    )
    filename: str | None = Field(
        default=None,
        description="A Jinja expression over the inputs for the file's name, without its suffix, such as 'invoice-{{ invoice.number }}'.",
    )

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        require_rich_for_rendering()
        from rich.console import Group
        from rich.markup import escape
        from rich.text import Text

        base_group = super().rendered_pretty(title=title, depth=depth)

        doc_gen_group = Group()
        doc_gen_group.renderables.append(base_group)

        doc_gen_group.renderables.append(Text())  # Blank line
        doc_gen_group.renderables.append(Text.from_markup(f"Format: [bold yellow]{escape(self.format)}[/bold yellow]"))
        if self.template_file is not None:
            doc_gen_group.renderables.append(Text.from_markup(f"Template file: [bold]{escape(self.template_file)}[/bold]"))

        return doc_gen_group

    @override
    def to_blueprint(self) -> PipeDocGenBlueprint:
        base_blueprint = super().to_blueprint()

        return PipeDocGenBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs_concept_specs,
            output=base_blueprint.output,
            format=self.format,
            template=self.template,
            template_file=self.template_file,
            filename=self.filename,
        )
