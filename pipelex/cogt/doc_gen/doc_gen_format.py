from enum import StrEnum


class DocGenFormat(StrEnum):
    """The file formats a `PipeDocGen` step can ask for.

    The tokens are MTHDS: a method names one, and it loads wherever the standard is read. Which of them a
    runtime prints depends on the document engines installed in it, each a model of the `doc_gen` family:
    open Pipelex prints a `pdf` laid out without a template, on `reportlab-pdf`, and the Pipelex document
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
    def with_article(self) -> str:
        """The token after its indefinite article, for a message: 'a pdf', 'an xlsx'."""
        match self:
            case DocGenFormat.XLSX:
                return f"an {self}"
            case DocGenFormat.PDF | DocGenFormat.DOCX | DocGenFormat.PPTX:
                return f"a {self}"

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

    A `pdf` from the layout tree and a `pdf` from composed HTML may print on different engines, so the model deck
    names a default engine per format and per source, and a `doc_gen` model lists the sources it prints from as
    its `inputs` and its format as its `outputs`.
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

    @classmethod
    def possible_for(cls, *, doc_gen_format: DocGenFormat) -> list["DocGenSource"]:
        """The sources a step in this format can compose from: the auto-layout where the format has one, and its kind of template."""
        sources: list[DocGenSource] = []
        if doc_gen_format.has_auto_layout:
            sources.append(DocGenSource.LAYOUT)
        sources.append(DocGenSource.HTML if doc_gen_format.is_template_html else DocGenSource.TEMPLATE_FILE)
        return sources


def doc_gen_choice_key(*, doc_gen_format: DocGenFormat, source: DocGenSource) -> str:
    """The key the model deck lists a format and source's default engine under: 'pdf.layout'."""
    return f"{doc_gen_format}.{source}"


def parse_doc_gen_choice_key(key: str) -> tuple[DocGenFormat, DocGenSource]:
    """The format and source a key of the model deck's doc-gen defaults names.

    Raises:
        ValueError: the key is not '<format>.<source>', or no step composes that format from that source.
    """
    format_token, separator, source_token = key.partition(".")
    try:
        doc_gen_format = DocGenFormat(format_token)
        source = DocGenSource(source_token)
    except ValueError as exc:
        msg = f"'{key}' is not a '<format>.<source>' key, such as 'pdf.layout'."
        raise ValueError(msg) from exc
    if not separator or source not in DocGenSource.possible_for(doc_gen_format=doc_gen_format):
        msg = f"'{key}' names no step: {doc_gen_format.with_article} is never composed {source.desc}."
        raise ValueError(msg)
    return doc_gen_format, source
