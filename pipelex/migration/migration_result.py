"""Shared migration result types."""

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class MigrationResult(BaseModel):
    """Result of migration operation."""

    files_processed: int = 0
    files_modified: int = 0
    total_changes: int = 0
    modified_files: List[Path] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
