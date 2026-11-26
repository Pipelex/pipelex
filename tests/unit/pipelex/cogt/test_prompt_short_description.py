import pytest

from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.tools.uri.resolved_uri import UriKind


class TestPromptShortDescription:
    @pytest.mark.parametrize(
        ("topic", "uri"),
        [
            ("a base64 data URL", "data:image/png;base64,aGVsbG8="),
            ("a data URL that is not base64", "data:text/plain,hello"),
            ("a data URL with no comma", "data:text/plain;base64aGVsbG8="),
        ],
    )
    def test_a_data_url_is_described_without_being_read(self, topic: str, uri: str) -> None:
        """Describing a prompt file never reads it, so a data URL in a form no reader takes is still described."""
        expected = f"{UriKind.BASE64_DATA_URL.desc}: {uri}"
        assert PromptImageUri(uri=uri).short_description() == expected, topic
        assert PromptDocumentUri(uri=uri).short_description() == expected, topic
