from typing import Any, Dict, List, Optional

import toml

from pipelex.tools.misc.file_utils import path_exists


class TOMLValidationError(Exception):
    """Raised when TOML file has formatting issues that could cause problems."""

    pass


def _validate_toml_content(content: str, file_path: str) -> None:
    """Validate TOML content for common formatting issues."""
    lines = content.splitlines()
    issues: List[str] = []

    for line_num, line in enumerate(lines, 1):
        # Check for trailing whitespace
        if line.rstrip() != line:
            trailing_chars = line[len(line.rstrip()) :]
            trailing_repr = repr(trailing_chars)
            issues.append(f"Line {line_num}: Trailing whitespace detected: {trailing_repr}")

        # Check for trailing whitespace after triple quotes (common issue)
        if line.strip().endswith('"""') and line != line.rstrip():
            issues.append(f"Line {line_num}: Trailing whitespace after triple quotes - this can cause TOML parsing issues")

    # Check for mixed line endings
    has_crlf = "\r\n" in content
    content_without_crlf = content.replace("\r\n", "")
    has_standalone_lf = "\n" in content_without_crlf
    if has_crlf and has_standalone_lf:
        issues.append("Mixed line endings detected (both CRLF and LF)")

    if issues:
        error_msg = f"TOML formatting issues in '{file_path}':\n" + "\n".join(f"  - {issue}" for issue in issues)
        raise TOMLValidationError(error_msg)


def validate_toml_file(path: str) -> None:
    """Validate TOML file for formatting issues.

    Args:
        path: Path to the TOML file to validate

    Raises:
        TOMLValidationError: If formatting issues are detected
    """
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
        _validate_toml_content(content, path)


def load_toml_from_path(path: str) -> Dict[str, Any]:
    """Load TOML from path.

    Args:
        path: Path to the TOML file

    Returns:
        Dictionary loaded from TOML

    Raises:
        toml.TomlDecodeError: If TOML parsing fails, with file path included
    """
    try:
        with open(path, "r", encoding="utf-8") as file:
            dict_from_toml = toml.load(file)
            return dict_from_toml
    except toml.TomlDecodeError as exc:
        raise toml.TomlDecodeError(f"TOML parsing error in file '{path}': {exc}", exc.doc, exc.pos) from exc


def failable_load_toml_from_path(path: str) -> Optional[Dict[str, Any]]:
    """Load TOML from path with failure handling."""
    if not path_exists(path):
        return None
    try:
        return load_toml_from_path(path)
    except toml.TomlDecodeError as exc:
        print(f"Failed to parse TOML file '{path}': {exc}")
        return None
