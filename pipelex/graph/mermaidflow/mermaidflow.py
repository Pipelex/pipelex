from typing import Any

from pydantic import BaseModel


class Mermaidflow(BaseModel):
    """Mermaid code paired with optional stuff data for interactive HTML rendering.

    Attributes:
        mermaid_code: The generated Mermaid flowchart syntax.
        stuff_data: Optional mapping from stuff mermaid IDs to their full IOSpec.data content.
            Only populated when GraphConfig.data_inclusion.stuff_json_content is True.
        stuff_data_text: Optional mapping from stuff mermaid IDs to their ASCII text representation.
            Only populated when GraphConfig.data_inclusion.stuff_text_content is True.
        stuff_data_html: Optional mapping from stuff mermaid IDs to their HTML representation.
            Only populated when GraphConfig.data_inclusion.stuff_html_content is True.
        stuff_metadata: Optional mapping from stuff mermaid IDs to their display metadata (name, concept).
            Always populated when any stuff data is present.
        stuff_content_type: Optional mapping from stuff mermaid IDs to their content_type (e.g., 'application/pdf').
            Used for special rendering of content types like PDFs.
    """

    mermaid_code: str
    stuff_data: dict[str, Any] | None = None
    stuff_data_text: dict[str, str] | None = None
    stuff_data_html: dict[str, str] | None = None
    stuff_metadata: dict[str, dict[str, str]] | None = None
    stuff_content_type: dict[str, str] | None = None
