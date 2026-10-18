"""Method folders for the tests of the commands that take one, in each shape the MTHDS protocol's entry rule decides."""

from enum import StrEnum
from pathlib import Path
from typing import NamedTuple


def entry_bundle_text(*, domain: str, pipe_code: str, main_pipe: str | None) -> str:
    """A bundle of one PipeLLM, declaring `main_pipe` when given."""
    main_pipe_line = f'main_pipe = "{main_pipe}"\n' if main_pipe else ""
    return f"""domain = "{domain}"
{main_pipe_line}
[pipe.{pipe_code}]
type        = "PipeLLM"
description = "Summarize the text"
inputs      = {{ text = "Text" }}
output      = "Text"
prompt      = "Summarize $text"
"""


class FolderEntry(NamedTuple):
    """Where the entry rule starts a folder: the bundle by its tree path, and the pipe as `domain.pipe_code`."""

    tree_path: str
    pipe_ref: str


class MethodFolderShape(StrEnum):
    """The folders a command taking one must read alike, each named by what the entry rule finds in it."""

    # A METHODS.toml names the entry, in a bundle that is neither `bundle.mthds` nor at the top of the folder.
    MANIFEST_MAIN_PIPE = "manifest_main_pipe"
    # No manifest, and one bundle declares a main_pipe; a `bundle.mthds` beside it declares none.
    ONE_DECLARED_MAIN_PIPE = "one_declared_main_pipe"
    # No manifest, and two bundles declare a main_pipe.
    SEVERAL_MAIN_PIPES = "several_main_pipes"
    # No manifest, and no bundle declares a main_pipe.
    NO_MAIN_PIPE = "no_main_pipe"

    @property
    def files(self) -> dict[str, str]:
        """The folder's files, by tree path."""
        match self:
            case MethodFolderShape.MANIFEST_MAIN_PIPE:
                return {
                    "METHODS.toml": (
                        '[package]\naddress = "github.com/pipelex-tests/folder"\nversion = "1.0.0"\ndescription = "A method folder"\n'
                        'main_pipe = "extract"\n\n[exports.folder_steps]\npipes = ["extract"]\n'
                    ),
                    "bundle.mthds": entry_bundle_text(domain="folder_report", pipe_code="write_report", main_pipe="write_report"),
                    "steps/extract.mthds": entry_bundle_text(domain="folder_steps", pipe_code="extract", main_pipe=None),
                }
            case MethodFolderShape.ONE_DECLARED_MAIN_PIPE:
                return {
                    "bundle.mthds": entry_bundle_text(domain="folder_steps", pipe_code="extract", main_pipe=None),
                    "report.mthds": entry_bundle_text(domain="folder_report", pipe_code="write_report", main_pipe="write_report"),
                }
            case MethodFolderShape.SEVERAL_MAIN_PIPES:
                return {
                    "a.mthds": entry_bundle_text(domain="folder_a", pipe_code="first", main_pipe="first"),
                    "b.mthds": entry_bundle_text(domain="folder_b", pipe_code="second", main_pipe="second"),
                }
            case MethodFolderShape.NO_MAIN_PIPE:
                return {
                    "a.mthds": entry_bundle_text(domain="folder_a", pipe_code="first", main_pipe=None),
                    "b.mthds": entry_bundle_text(domain="folder_b", pipe_code="second", main_pipe=None),
                }

    @property
    def entry(self) -> FolderEntry | None:
        """Where the entry rule starts the folder, or None when it refuses it."""
        match self:
            case MethodFolderShape.MANIFEST_MAIN_PIPE:
                return FolderEntry(tree_path="steps/extract.mthds", pipe_ref="folder_steps.extract")
            case MethodFolderShape.ONE_DECLARED_MAIN_PIPE:
                return FolderEntry(tree_path="report.mthds", pipe_ref="folder_report.write_report")
            case MethodFolderShape.SEVERAL_MAIN_PIPES | MethodFolderShape.NO_MAIN_PIPE:
                return None

    @property
    def refusal(self) -> str | None:
        """What the refusal of the folder says, or None when the entry rule starts it."""
        match self:
            case MethodFolderShape.MANIFEST_MAIN_PIPE | MethodFolderShape.ONE_DECLARED_MAIN_PIPE:
                return None
            case MethodFolderShape.SEVERAL_MAIN_PIPES:
                return "several of its bundles declare a main_pipe: 'a.mthds' declares 'first', 'b.mthds' declares 'second'"
            case MethodFolderShape.NO_MAIN_PIPE:
                return "none of its bundles declares a main_pipe ('a.mthds', 'b.mthds')"


#: A pipe a test names with `--pipe` in a folder of several main pipes, and the bundle defining it.
NAMED_PIPE = FolderEntry(tree_path="b.mthds", pipe_ref="folder_b.second")


def write_method_folder(*, directory: Path, shape: MethodFolderShape) -> Path:
    """Write a folder of this shape into `directory`, and return it."""
    for tree_path, content in shape.files.items():
        file_path = directory / tree_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    return directory
