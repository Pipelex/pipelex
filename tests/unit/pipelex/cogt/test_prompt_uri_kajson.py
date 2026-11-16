import pytest
from kajson import kajson

from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl

_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


class TestPromptUriKajson:
    @pytest.mark.parametrize(
        "prompt_uri",
        [
            PromptImageUri(uri=_DATA_URL, input_name="photo"),
            PromptDocumentUri(uri=_DATA_URL, input_name="scan"),
        ],
    )
    def test_a_resolved_prompt_uri_crosses_kajson_with_its_uri_alone(self, prompt_uri: PromptImageUri | PromptDocumentUri) -> None:
        """Resolving a prompt URI leaves nothing on the instance, so a base64 data URL's payload is not encoded twice."""
        resolved = prompt_uri.resolved
        assert isinstance(resolved, ResolvedBase64DataUrl)
        assert resolved.mime_type == "image/png"

        serialized = kajson.dumps(prompt_uri)  # pyright: ignore[reportUnknownMemberType]
        assert serialized.count("iVBORw0KGgo") == 1
        assert "resolved" not in vars(prompt_uri)

        roundtripped = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]
        assert type(roundtripped) is type(prompt_uri)
        assert roundtripped == prompt_uri
        assert roundtripped.resolved == resolved
