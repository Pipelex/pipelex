"""Shared migration result types."""

from pathlib import Path

from pydantic import BaseModel, Field

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class MigrationResult(BaseModel):
    """Result of migration operation."""

    files_processed: int = 0
    files_modified: int = 0
    total_changes: int = 0
    modified_files: list[Path] = Field(default_factory=empty_list_factory_of(Path))
    errors: list[str] = Field(default_factory=list)
