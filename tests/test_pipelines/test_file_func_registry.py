
from pydantic import Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent


class FilePath(StructuredContent):
    """A path to a file in the codebase."""

    path: str = Field(description="Path to the file")


class CodebaseFileContent(StructuredContent):
    """Content of a codebase file."""

    file_path: str = Field(description="Path to the codebase file")
    file_content: str = Field(description="Content of the codebase file")


def read_file_content(working_memory: WorkingMemory) -> ListContent[CodebaseFileContent]:
    """Read the content of related codebase files.

    Args:
        working_memory: Working memory containing related_file_paths

    Returns:
        ListContent of CodebaseFileContent objects

    """
    file_paths_list = working_memory.get_stuff_as_list("related_file_paths", item_type=FilePath)

    codebase_files: list[CodebaseFileContent] = []
    for file_path in file_paths_list.items:
        try:
            with open(file_path.path, encoding="utf-8") as file:
                content = file.read()
                codebase_files.append(CodebaseFileContent(file_path=file_path.path, file_content=content))
        except Exception as e:
            codebase_files.append(
                CodebaseFileContent(file_path=file_path.path, file_content=f"# File not found or unreadable: {file_path.path}\n# Error: {e!s}"),
            )

    return ListContent[CodebaseFileContent](items=codebase_files)
