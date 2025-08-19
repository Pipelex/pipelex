from pathlib import Path
from typing import Any, Dict, Optional

import toml
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.core.bundle.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.tools.misc.toml_utils import clean_trailing_whitespace, validate_toml_content, validate_toml_file


class PipelexSyntaxConverter(BaseModel):
    """TOML -> PipelexBundleBlueprint"""

    file_path: Optional[Path] = None
    file_content: Optional[str] = None

    @model_validator(mode="after")
    def check_file_path_or_file_content(self) -> Self:
        """Need to check if there is at least one of file_path or file_content"""
        if self.file_path is None and self.file_content is None:
            raise ValueError("Either file_path or file_content must be provided")
        return self

    @model_validator(mode="after")
    def validate_file_path(self) -> Self:
        if self.file_path:
            validate_toml_file(path=str(self.file_path))
        if self.file_content:
            validate_toml_content(content=self.file_content, file_path=str(self.file_path))
        return self

    def _load_toml_content(self) -> str:
        """Load TOML content from file_path or use file_content directly."""
        if self.file_path:
            try:
                with open(self.file_path, "r", encoding="utf-8") as file:
                    file_content = file.read()

                # Clean trailing whitespace and write back if needed
                cleaned_content = clean_trailing_whitespace(file_content)
                if file_content != cleaned_content:
                    with open(self.file_path, "w", encoding="utf-8") as file:
                        file.write(cleaned_content)
                    return cleaned_content

                return file_content

            except Exception as exc:
                raise ValueError(f"Failed to read TOML file '{self.file_path}': {exc}") from exc
        else:
            if self.file_content is None:
                raise ValueError("file_content must be provided if file_path is not provided")
            return self.file_content

    def _parse_toml_content(self, content: str) -> Dict[str, Any]:
        """Parse TOML content and return the dictionary."""
        try:
            return toml.loads(content)
        except toml.TomlDecodeError as exc:
            file_path_str = str(self.file_path) if self.file_path else "content"
            raise toml.TomlDecodeError(f"TOML parsing error in '{file_path_str}': {exc}", exc.doc, exc.pos) from exc

    def make_pipelex_bundle_blueprint(self) -> PipelexBundleBlueprint:
        """Make a PipelexBundleBlueprint from the file_path or file_content"""
        file_content = self._load_toml_content()
        toml_data = self._parse_toml_content(file_content)
        from pipelex import pretty_print

        pretty_print(toml_data, "toml_data")
        return PipelexBundleBlueprint.model_validate(toml_data)
