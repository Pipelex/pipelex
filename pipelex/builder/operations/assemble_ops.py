"""Core operations for assembling TOML bundle from parts."""

# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# mypy: disable-error-code="arg-type"

from pathlib import Path

import tomlkit


def _merge_toml_sections(
    base_doc: tomlkit.TOMLDocument,
    section_name: str,
    content_to_merge: tomlkit.TOMLDocument,
) -> None:
    """Merge a section from content into the base document.

    Args:
        base_doc: The base TOML document to merge into.
        section_name: The name of the section (e.g., "concept", "pipe").
        content_to_merge: The content document to merge (tomlkit preserves inline tables).
    """
    if section_name not in content_to_merge:
        return

    section_content = content_to_merge[section_name]
    if not section_content:
        return

    if section_name not in base_doc:
        base_doc.add(section_name, tomlkit.table())

    existing_section = base_doc[section_name]
    for key, value in section_content.items():  # type: ignore[union-attr]
        existing_section[key] = value  # type: ignore[index]


def _load_toml_content(source: str) -> tomlkit.TOMLDocument:
    """Load TOML content from either a file path or inline string.

    Uses tomlkit to preserve inline tables and formatting.

    Args:
        source: Either a file path or inline TOML string.

    Returns:
        Parsed TOML document that preserves formatting.
    """
    try:
        source_path = Path(source)
        if source_path.exists() and source_path.is_file():
            with open(source_path, encoding="utf-8") as the_file:
                return tomlkit.load(the_file)
    except OSError:
        # Inline TOML content may contain characters invalid for file paths
        pass
    return tomlkit.parse(source)


def assemble_bundle(
    domain: str,
    main_pipe: str,
    description: str | None = None,
    system_prompt: str | None = None,
    concept_tomls: list[str] | None = None,
    pipe_tomls: list[str] | None = None,
) -> str:
    """Assemble a complete .mthds bundle TOML from individual parts.

    Each concept/pipe source can be either a file path or inline TOML content.

    Args:
        domain: Domain code for the bundle (snake_case).
        main_pipe: Main pipe code for the bundle.
        description: Optional description of the bundle.
        system_prompt: Optional default system prompt for LLM pipes.
        concept_tomls: TOML file paths or inline TOML containing concept definitions.
        pipe_tomls: TOML file paths or inline TOML containing pipe definitions.

    Returns:
        Assembled TOML content as a string.

    Raises:
        FileNotFoundError: If a referenced file is not found.
        Exception: If TOML parsing fails.
    """
    doc = tomlkit.document()
    doc.add("domain", domain)

    if description:
        doc.add("description", description)

    if system_prompt:
        doc.add("system_prompt", system_prompt)

    doc.add("main_pipe", main_pipe)

    # Process concept sources
    if concept_tomls:
        for concept_source in concept_tomls:
            concept_content = _load_toml_content(concept_source)
            _merge_toml_sections(doc, "concept", concept_content)

    # Process pipe sources
    if pipe_tomls:
        for pipe_source in pipe_tomls:
            pipe_content = _load_toml_content(pipe_source)
            _merge_toml_sections(doc, "pipe", pipe_content)

    toml_content = tomlkit.dumps(doc)
    if not toml_content.endswith("\n"):
        toml_content += "\n"

    return toml_content
