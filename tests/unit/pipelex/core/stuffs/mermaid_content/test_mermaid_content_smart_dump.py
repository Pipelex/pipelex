from pipelex.core.stuffs.mermaid_content import MermaidContent
from tests.unit.pipelex.core.stuffs.mermaid_content.test_data import TestData


class TestMermaidContentSmartDump:
    """Tests for MermaidContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump returns a dict with mermaid_code and mermaid_url."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_simple_diagram(self):
        """Verify smart_dump handles simple diagrams."""
        simple_code = "graph LR\n    A --> B"
        simple_url = "https://mermaid.live/simple"
        content = MermaidContent(mermaid_code=simple_code, mermaid_url=simple_url)
        result = content.smart_dump()
        assert result == {"mermaid_code": simple_code, "mermaid_url": simple_url}
        assert isinstance(result, dict)
