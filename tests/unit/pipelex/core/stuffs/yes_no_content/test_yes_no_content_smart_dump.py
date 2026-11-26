from pipelex.core.stuffs.yes_no_content import YesNoContent
from tests.unit.pipelex.core.stuffs.yes_no_content.cases import YesNoContentCases


class TestYesNoContentSmartDump:
    """Tests for YesNoContent.smart_dump() method."""

    def test_smart_dump_true(self):
        """Verify smart_dump returns a dict for a true value."""
        content = YesNoContent(yes_no=YesNoContentCases.SAMPLE_TRUE)
        result = content.smart_dump()
        assert result == YesNoContentCases.EXPECTED_SMART_DUMP_TRUE
        assert isinstance(result, dict)

    def test_smart_dump_false(self):
        """Verify smart_dump returns a dict for a false value."""
        content = YesNoContent(yes_no=YesNoContentCases.SAMPLE_FALSE)
        result = content.smart_dump()
        assert result == YesNoContentCases.EXPECTED_SMART_DUMP_FALSE
        assert isinstance(result, dict)
