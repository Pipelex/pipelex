from pytest_mock import MockerFixture

from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.google.google_factory import GoogleFactory


class TestGoogleFactoryTokens:
    """Tests for thinking token usage extraction in GoogleFactory."""

    def test_thoughts_token_count_maps_to_output_reasoning(self, mocker: MockerFixture):
        """thoughts_token_count in usage metadata maps to OUTPUT_REASONING."""
        usage_metadata = mocker.MagicMock()
        usage_metadata.prompt_token_count = 100
        usage_metadata.candidates_token_count = 200
        usage_metadata.cached_content_token_count = None
        usage_metadata.thoughts_token_count = 500

        result = GoogleFactory.extract_token_usage(usage_metadata)

        assert result[TokenCategory.INPUT] == 100
        assert result[TokenCategory.OUTPUT] == 200
        assert result[TokenCategory.OUTPUT_REASONING] == 500

    def test_no_thoughts_token_count_omits_output_reasoning(self, mocker: MockerFixture):
        """When thoughts_token_count is absent, OUTPUT_REASONING key is not present."""
        usage_metadata = mocker.MagicMock()
        usage_metadata.prompt_token_count = 100
        usage_metadata.candidates_token_count = 200
        usage_metadata.cached_content_token_count = None
        usage_metadata.thoughts_token_count = None

        result = GoogleFactory.extract_token_usage(usage_metadata)

        assert result[TokenCategory.INPUT] == 100
        assert result[TokenCategory.OUTPUT] == 200
        assert TokenCategory.OUTPUT_REASONING not in result

    def test_zero_thoughts_token_count_omits_output_reasoning(self, mocker: MockerFixture):
        """When thoughts_token_count is 0, OUTPUT_REASONING key is not present (falsy check)."""
        usage_metadata = mocker.MagicMock()
        usage_metadata.prompt_token_count = 100
        usage_metadata.candidates_token_count = 200
        usage_metadata.cached_content_token_count = None
        usage_metadata.thoughts_token_count = 0

        result = GoogleFactory.extract_token_usage(usage_metadata)

        assert TokenCategory.OUTPUT_REASONING not in result
