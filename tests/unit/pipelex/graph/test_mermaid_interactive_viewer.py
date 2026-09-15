"""The interactive Mermaid page shows a stuff's JSON, and a preview for the content types it can render."""

from __future__ import annotations

import pytest

from pipelex.graph.mermaidflow.mermaid_html import render_mermaid_html_with_data_async

_MERMAID_CODE = "flowchart TD\n    s_abc[Result]\n"
_STUFF_ID = "s_abc"


@pytest.mark.asyncio(loop_scope="class")
class TestMermaidInteractiveViewer:
    async def _render(self, *, content_type: str) -> str:
        return await render_mermaid_html_with_data_async(
            _MERMAID_CODE,
            stuff_data={_STUFF_ID: {"text": "hello"}},
            stuff_metadata={_STUFF_ID: {"name": "result", "concept": "Text"}},
            stuff_content_type={_STUFF_ID: content_type},
            title="Viewer",
        )

    async def test_the_page_offers_the_json_and_preview_tabs_only(self) -> None:
        """The Pretty and HTML tabs went with the renderings that fed them."""
        html = await self._render(content_type="text/plain")

        assert 'id="tab-json"' in html
        assert 'id="tab-preview"' in html
        assert 'id="tab-text"' not in html
        assert 'id="tab-html"' not in html

    async def test_the_page_carries_the_stuff_json(self) -> None:
        html = await self._render(content_type="text/plain")

        assert "hello" in html

    async def test_the_page_loads_no_sanitizer(self) -> None:
        """DOMPurify was there for model-authored HTML; nothing renders markup into the page any more."""
        html = await self._render(content_type="image/png")

        assert "purify" not in html.lower()
