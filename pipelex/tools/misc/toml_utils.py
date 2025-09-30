from __future__ import annotations

from typing import Any

import toml

from pipelex.tools.misc.file_utils import path_exists


class TOMLValidationError(Exception):
    """Raised when TOML file has formatting issues that could cause problems."""


def validate_toml_content(content: str, file_path: str | None = None) -> None:
    """Validate TOML content for common formatting issues."""
    # lines = content.splitlines()
    # issues: list[str] = []

    # for line_num, line in enumerate(lines, 1):
    #     # Check for trailing whitespace
    #     if line.rstrip() != line:
    #         trailing_chars = line[len(line.rstrip()) :]
    #         trailing_repr = repr(trailing_chars)
    #         issues.append(f"Line {line_num}: Trailing whitespace detected: {trailing_repr}")

    #     # Check for trailing whitespace after triple quotes (common issue)
    #     if line.strip().endswith('"""') and line != line.rstrip():
    #         issues.append(f"Line {line_num}: Trailing whitespace after triple quotes - this can cause TOML parsing issues")

    # # Check for mixed line endings
    # has_crlf = "\r\n" in content
    # content_without_crlf = content.replace("\r\n", "")
    # has_standalone_lf = "\n" in content_without_crlf
    # if has_crlf and has_standalone_lf:
    #     issues.append("Mixed line endings detected (both CRLF and LF)")

    # if issues:
    #     error_msg = f"TOML formatting issues in '{file_path}':\n" + "\n".join(f"  - {issue}" for issue in issues)
    #     raise TOMLValidationError(error_msg)


def validate_toml_file(path: str) -> None:
    """Validate TOML file for formatting issues.

    Args:
        path: Path to the TOML file to validate

    Raises:
        TOMLValidationError: If formatting issues are detected

    """
    with open(path, encoding="utf-8") as file:
        content = file.read()
        validate_toml_content(content, path)


def clean_trailing_whitespace(content: str) -> str:
    # """Clean trailing whitespace from TOML content.

    # This function:
    # 1. Removes trailing whitespace from all lines
    # 2. Ensures exactly one empty line at EOF (two newline characters)
    # 3. If no empty line at EOF, removes trailing whitespace from last non-empty line

    # Args:
    #     content: The TOML content to clean

    # Returns:
    #     The cleaned TOML content with trailing whitespace removed and an empty line at EOF

    # """
    # # Split into lines and clean each line
    # lines = [line.rstrip() for line in content.splitlines()]

    # # Remove trailing empty lines
    # while lines and not lines[-1]:
    #     lines.pop()

    # # If we have lines and the last line has trailing whitespace, remove it
    # if lines:
    #     lines[-1] = lines[-1].rstrip()

    # # Join with newlines and ensure an empty line at EOF (two newlines)
    # return "\n".join(lines) + "\n\n"
    return content


def load_toml_from_path(path: str) -> dict[str, Any]:
    """Load TOML from path.

    Args:
        path: Path to the TOML file

    Returns:
        Dictionary loaded from TOML

    Raises:
        toml.TomlDecodeError: If TOML parsing fails, with file path included

    """
    try:
        with open(path, encoding="utf-8") as file:
            content = file.read()

        cleaned_content = clean_trailing_whitespace(content)

        # If content changed, write it back
        if content != cleaned_content:
            with open(path, "w", encoding="utf-8") as file:
                file.write(cleaned_content)

        # Parse TOML first
        return toml.loads(cleaned_content)
    except toml.TomlDecodeError as exc:
        msg = f"TOML parsing error in file '{path}': {exc}"
        raise toml.TomlDecodeError(msg, exc.doc, exc.pos) from exc


def load_toml_from_path_if_exists(path: str) -> dict[str, Any] | None:
    """Load TOML from path if it exists."""
    if not path_exists(path):
        return None
    return load_toml_from_path(path)
