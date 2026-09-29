from enum import StrEnum


class DocGenFormat(StrEnum):
    """The file formats a `PipeDocGen` step can ask for.

    The tokens are MTHDS: a method names one, and it loads wherever the standard is read. Which of them a
    runtime prints depends on the engines installed in it (`DocGenSource`, the document renderer
    registry): open Pipelex prints a `pdf` laid out without a template, and the Pipelex document
    generation plugin prints the rest. HTML is not a format: `PipeCompose` already produces the native
    `Html`.
    """

    PDF = "pdf"
    XLSX = "xlsx"
    DOCX = "docx"
    PPTX = "pptx"

    @property
    def mime_type(self) -> str:
        match self:
            case DocGenFormat.PDF:
                return "application/pdf"
            case DocGenFormat.XLSX:
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            case DocGenFormat.DOCX:
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            case DocGenFormat.PPTX:
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    @property
    def suffix(self) -> str:
        """The file suffix, without its dot."""
        return self.value

    @property
    def template_file_suffix(self) -> str:
        """The suffix a `template_file` must carry for this format: an HTML template for a PDF, the office file itself otherwise."""
        match self:
            case DocGenFormat.PDF:
                return ".html"
            case DocGenFormat.XLSX:
                return ".xlsx"
            case DocGenFormat.DOCX:
                return ".docx"
            case DocGenFormat.PPTX:
                return ".pptx"

    @property
    def is_template_html(self) -> bool:
        """Whether this format's template is HTML, composed by Pipelex before an engine prints it.

        Only a PDF's is: an office template is a file its engine fills from plain data.
        """
        match self:
            case DocGenFormat.PDF:
                return True
            case DocGenFormat.XLSX | DocGenFormat.DOCX | DocGenFormat.PPTX:
                return False

    @property
    def has_auto_layout(self) -> bool:
        """Whether a step in this format may have no template and print the auto-layout of its inputs.

        A deck generated without a design is not what anyone asks for (DB8), so `pptx` needs a template file.
        """
        match self:
            case DocGenFormat.PDF | DocGenFormat.XLSX | DocGenFormat.DOCX:
                return True
            case DocGenFormat.PPTX:
                return False


class DocGenSource(StrEnum):
    """What the compose stage hands an engine to print, which is half of what picks the engine.

    A `pdf` from the layout tree and a `pdf` from composed HTML are different engines, so engines register
    per format and per source.
    """

    LAYOUT = "layout"
    """The auto-layout of the step's inputs, as a layout tree: the step has no template."""

    HTML = "html"
    """Composed HTML: a `pdf` step's HTML template rendered against its inputs."""

    TEMPLATE_FILE = "template_file"
    """An office template file, which the engine fills from the step's inputs as plain data."""

    @property
    def desc(self) -> str:
        """How a message names this source after a format: 'pdf from the auto-layout'."""
        match self:
            case DocGenSource.LAYOUT:
                return "from the auto-layout of its inputs"
            case DocGenSource.HTML:
                return "from an HTML template"
            case DocGenSource.TEMPLATE_FILE:
                return "from a template file"

    @classmethod
    def for_step(cls, *, doc_gen_format: DocGenFormat, has_template: bool) -> "DocGenSource":
        """The source a step's format and template make: no template is the layout, a template is HTML for a PDF and a file otherwise."""
        if not has_template:
            return DocGenSource.LAYOUT
        if doc_gen_format.is_template_html:
            return DocGenSource.HTML
        return DocGenSource.TEMPLATE_FILE


def is_printed_by_open_pipelex(*, doc_gen_format: DocGenFormat, source: DocGenSource) -> bool:
    """Whether open Pipelex's built-in engine prints this format from this source: only a `pdf` without a template."""
    match doc_gen_format:
        case DocGenFormat.PDF:
            match source:
                case DocGenSource.LAYOUT:
                    return True
                case DocGenSource.HTML | DocGenSource.TEMPLATE_FILE:
                    return False
        case DocGenFormat.XLSX | DocGenFormat.DOCX | DocGenFormat.PPTX:
            return False
