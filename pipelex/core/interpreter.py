from pathlib import Path

from pydantic import BaseModel, model_validator

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.exceptions import (
    PipelexConfigurationError,
)
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_content, load_toml_from_path
from pipelex.types import Self


class PLXDecodeError(TomlError):
    """Raised when PLX decoding fails."""


class PipelexInterpreter(BaseModel):
    """plx -> PipelexBundleBlueprint"""

    file_path: Path | None = None
    file_content: str | None = None

    @model_validator(mode="after")
    def check_file_path_or_file_content(self) -> Self:
        """Need to check if there is at least one of file_path or file_content"""
        if self.file_path is None and self.file_content is None:
            msg = "Either file_path or file_content must be provided"
            raise PipelexConfigurationError(msg)
        return self

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

    def make_pipelex_bundle_blueprint(self) -> PipelexBundleBlueprint:
        """Make a PipelexBundleBlueprint from the file_path or file_content"""
        # Load PLX content from file_path or use file_content directly.
        try:
            if self.file_path:
                blueprint_dict = load_toml_from_path(path=str(self.file_path))
                blueprint_dict.update(source=str(self.file_path))
            elif self.file_content:
                blueprint_dict = load_toml_from_content(content=self.file_content)
            else:
                msg = "Could not make PipelexBundleBlueprint: either file_path or file_content must be provided"
                raise PipelexConfigurationError(msg)
        except TomlError as exc:
            raise PLXDecodeError(message=exc.message, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno) from exc
        return PipelexBundleBlueprint.model_validate(blueprint_dict)
