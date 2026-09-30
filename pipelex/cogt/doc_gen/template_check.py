"""What an engine's template checker takes and returns, part of the plugin contract.

An office template names the fields it is filled with in its own way: an Excel workbook through its defined
names and Tables, a Word document through its tags, a PowerPoint deck through its shape names. Pipelex cannot
read those, so an engine that fills a template file overrides its worker's `check_template`
(`DocGenWorkerAbstract`). The dry run, and so `pipelex validate`, calls it for every `PipeDocGen` step with a
`template_file`, before anything is spent: an error finding fails the step, and a warning is logged. The
built-in PDF engine takes no template, and Pipelex checks HTML templates itself, so neither needs one.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.cogt.doc_gen.input_shape import InputShape


class TemplateFindingSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"

    @property
    def is_error(self) -> bool:
        """Whether a finding of this severity fails the step, rather than being logged."""
        match self:
            case TemplateFindingSeverity.ERROR:
                return True
            case TemplateFindingSeverity.WARNING:
                return False


class TemplateFinding(BaseModel):
    """One thing a checker found in a template file."""

    severity: TemplateFindingSeverity = Field(strict=False)
    message: str = Field(description="What is wrong, in the template author's words: the name, the field, the fix")
    location: str | None = Field(default=None, description="Where it is in the file, such as 'the Table LineItems on sheet Invoice'")


class TemplateCheckRequest(BaseModel):
    """A template file and the inputs it is filled with, for a checker to compare."""

    model_config = ConfigDict(extra="forbid", ser_json_bytes="base64", val_json_bytes="base64")

    format: DocGenFormat = Field(strict=False)
    template: bytes = Field(description="The template file's bytes")
    template_name: str = Field(description="The template file as the method names it, for messages")
    inputs: dict[str, InputShape] = Field(description="The step's declared inputs by name, as the shape of their plain data")
    data: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Mock inputs as plain data, shaped as `RenderJob.data` is, so the checker can fill the template in memory and report "
            "what the fill would raise; None when only the structure is to be compared"
        ),
    )
