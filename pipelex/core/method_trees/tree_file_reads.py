"""A file of its method tree that a step reads, named by its tree path, with what the step reads it as.

A step names the files of its tree it reads in the fields the MTHDS standard gives it (`mthds/docs/spec/method-tree.md`):
a `PipeDocGen` step's `template_file`, by a file reference, and the relative URLs of an HTML template, by URL
references; and a `PipeFunc` step's `function_name`, by an import path whose module is a file of the tree. Each pipe
resolves those names to tree paths as it is built and validated, so a validation can say which step reads which file,
and which files of the tree no step reads (`wip/extra-files/design.md`, "Validation explains the method's files").
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TreeFileUse(StrEnum):
    """What a step reads a file of its method tree as."""

    TEMPLATE = "template"
    """The template a `PipeDocGen` step fills, named by its `template_file`."""

    TEMPLATE_ASSET = "template_asset"
    """An image, a stylesheet or a font that an HTML template names by a literal relative URL, or that one of its
    stylesheets names, which the step's print reads."""

    PYTHON_MODULE = "python_module"
    """The module defining the function a `PipeFunc` step calls, named by the import path of its `function_name`."""

    @property
    def label(self) -> str:
        """How a sentence names the use: "template", "template asset", "Python module"."""
        match self:
            case TreeFileUse.TEMPLATE:
                return "template"
            case TreeFileUse.TEMPLATE_ASSET:
                return "template asset"
            case TreeFileUse.PYTHON_MODULE:
                return "Python module"


class TreeFileRead(BaseModel):
    """A file of its method tree a step reads: its tree path, and what the step reads it as."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_path: str = Field(description="The file's path from the root of the step's method tree, such as `templates/invoice.html`.")
    use: TreeFileUse = Field(
        strict=False,
        description=(
            "What the step reads the file as: `template`, the template a PipeDocGen step fills; `template_asset`, an image, "
            "a stylesheet or a font its HTML template names; `python_module`, the module of the function a PipeFunc step calls."
        ),
    )
