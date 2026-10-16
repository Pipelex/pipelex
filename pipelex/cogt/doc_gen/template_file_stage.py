"""The interpreter's part in printing from a template file: what only a loaded method can do with the file.

The print stage of a `PipeDocGen` step is a kernel-layer leaf (`pipelex.cogt.content_generation.doc_gen_generate`):
it reads the step's template file through the method file store and hands the engine its job. Two things it does with
the file need the method itself, its concepts and its steps' error classes, which live in the interpreter layer:
rendering an HTML template file with the step's data, typed by the run's library, under the whole stack of a
`PipeCompose` HTML template; and reporting what the engine's template checker found in an office template file at a dry
print, an error failing the step and a warning joining the validation verdict. The interpreter implements this protocol
and installs it on the runtime hub when it boots (`Pipelex.setup`); a process booted with the kernel layer alone prints
no template file.
"""

from typing import Protocol

from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile
from pipelex.cogt.doc_gen.template_check import TemplateFinding


class TemplateFileStageProtocol(Protocol):
    """Renders an HTML template file with its step's data, and reports the findings of an office template's check."""

    async def render_html_template_file(self, *, template_file: ComposedTemplateFile, template_source: str) -> str:
        """The HTML template file's text rendered with the step's data, as the compose stage of a `PipeCompose` renders one.

        Every value the template reads must exist, as in every template of a document: a missing one fails the step.

        Args:
            template_file: The template file as the compose stage named it, with the context it renders with.
            template_source: The template file's text, read through the method file store.
        """
        ...

    def report_template_findings(self, *, template_file: ComposedTemplateFile, findings: list[TemplateFinding]) -> None:
        """Report what the engine's template checker found in an office template file, at a dry print.

        An error finding fails the step; a warning joins the validation verdict's warnings, or the log when no
        validation collects them.
        """
        ...
