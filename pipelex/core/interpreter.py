from pathlib import Path
from typing import Any

import toml
from pydantic import BaseModel, model_validator

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.exceptions import (
    PipelexConfigurationError,
)
from pipelex.tools.misc.file_utils import load_text_from_path
from pipelex.types import Self


class PLXDecodeError(toml.TomlDecodeError):
    """Raised when PLX decoding fails."""


class PipelexInterpreter(BaseModel):
    """plx -> PipelexBundleBlueprint"""

    file_path: Path | None = None
    file_content: str | None = None

    @staticmethod
    def escape_plx_string(value: str | None) -> str:
        """Escape a string for plx serialization."""
        if value is None:
            return ""
        # Escape backslashes first (must be done first)
        value = value.replace("\\", "\\\\")
        # Escape quotes
        value = value.replace('"', '\\"')
        # Replace actual newlines with escaped newlines
        value = value.replace("\n", "\\n")
        value = value.replace("\r", "\\r")
        return value.replace("\t", "\\t")

    @model_validator(mode="after")
    def check_file_path_or_file_content(self) -> Self:
        """Need to check if there is at least one of file_path or file_content"""
        if self.file_path is None and self.file_content is None:
            msg = "Either file_path or file_content must be provided"
            raise PipelexConfigurationError(msg)
        return self

    def _get_content(self) -> str:
        """Load PLX content from file_path or use file_content directly."""
        if self.file_path:
            return load_text_from_path(path=str(self.file_path))
        elif self.file_content:
            return self.file_content
        else:
            msg = "file_content must be provided if file_path is not provided"
            raise PipelexConfigurationError(msg)

    @staticmethod
    def is_pipelex_file(file_path: Path) -> bool:
        """Check if a file is a valid Pipelex PLX file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if the file is a Pipelex file, False otherwise

        Criteria:
            - Has .plx extension
            - Starts with "domain =" (ignoring leading whitespace)

        """
        # Check if it has .toml extension
        if file_path.suffix != ".plx":
            return False

        # Check if file exists
        if not file_path.exists() or not file_path.is_file():
            return False

        try:
            # Read the first few lines to check for "domain ="
            with open(file_path, encoding="utf-8") as f:
                # Read first 100 characters (should be enough to find domain)
                content = f.read(100)
                # Remove leading whitespace and check if it starts with "domain ="
                stripped_content = content.lstrip()
                return stripped_content.startswith("domain =")
        except Exception:
            # If we can't read the file, it's not a valid Pipelex file
            return False

    def _parse_plx_content(self, content: str) -> dict[str, Any]:
        """Parse PLX content and return the dictionary."""
        try:
            return toml.loads(content)
        except toml.TomlDecodeError as exc:
            file_path_str = str(self.file_path) if self.file_path else "content"
            msg = f"PLX parsing error in '{file_path_str}': {exc}"
            raise PLXDecodeError(msg, exc.doc, exc.pos) from exc

    def make_pipelex_bundle_blueprint(self) -> PipelexBundleBlueprint:
        """Make a PipelexBundleBlueprint from the file_path or file_content"""
        file_content = self._get_content()
        blueprint_dict = self._parse_plx_content(file_content)
        if self.file_path:
            blueprint_dict.update(source=str(self.file_path))
        return PipelexBundleBlueprint.model_validate(blueprint_dict)
