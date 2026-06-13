"""Tests for GatewayCompletionsFactory extract-output parsing.

Responses are built with ``GenericResponse.model_validate({...})``: the model allows extras,
so custom top-level fields like ``pages`` become attributes — exactly what the
``hasattr(response, "pages")`` branches need. Omitting ``pages`` exercises the
``choices[0].message.content`` fallback that survives Portkey proxying.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from portkey_ai.api_resources.utils import GenericResponse

from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.gateway.gateway_exceptions import GatewayExtractResponseError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_FACTORY_NAMESPACE = "pipelex.plugins.gateway.gateway_completions_factory"

_FALSY_CHOICES_PAYLOADS: list[dict[str, Any]] = [
    {},
    {"choices": []},
    {"choices": "nope"},
    {"choices": [{}]},
    {"choices": [{"message": "nope"}]},
    {"choices": [{"message": {"content": 42}}]},
    {"choices": [{"message": {"content": '{"key": 1}'}}]},
    {"choices": [{"message": {"content": "{not json"}}]},
]


def _response(payload: dict[str, Any]) -> GenericResponse:
    return GenericResponse.model_validate(payload)


def _choices_response(content: Any) -> GenericResponse:
    """Build a response whose pages/content live in choices[0].message.content."""
    return GenericResponse.model_validate({"choices": [{"message": {"content": content}}]})


class TestGatewayCompletionsExtractOutput:
    """Extract-protocol dispatch and per-protocol response parsing."""

    # ---- make_extract_output_from_response dispatch ----

    @pytest.mark.parametrize(
        ("model_handle", "target_method"),
        [
            ("mistral-document-ai-2505", "_make_extract_output_from_response_mistral"),
            ("azure-document-intelligence", "_make_extract_output_from_response_azure"),
            ("deepseek-ocr", "_make_extract_output_from_response_deepseek"),
            ("linkup-fetch", "_make_extract_output_from_response_linkup_fetch"),
        ],
    )
    def test_dispatch_routes_each_handle_to_its_parser(
        self,
        mocker: MockerFixture,
        model_handle: str,
        target_method: str,
    ) -> None:
        """Each known model handle dispatches to the matching protocol-specific parser."""
        sentinel_output = ExtractOutput(pages={})
        mock_parser = mocker.patch.object(GatewayCompletionsFactory, target_method, return_value=sentinel_output)
        inference_model = mocker.MagicMock()
        inference_model.name = model_handle
        response = _response({})

        result = GatewayCompletionsFactory.make_extract_output_from_response(inference_model=inference_model, response=response)

        assert result is sentinel_output
        mock_parser.assert_called_once_with(response=response)

    def test_dispatch_unknown_handle_raises_value_error(self, mocker: MockerFixture) -> None:
        """An unknown model handle is rejected by GatewayExtractProtocol.make_from_model_handle."""
        inference_model = mocker.MagicMock()
        inference_model.name = "gpt-4o"

        with pytest.raises(ValueError, match="Invalid model ID: gpt-4o"):
            GatewayCompletionsFactory.make_extract_output_from_response(inference_model=inference_model, response=_response({}))

    # ---- _extract_pages_from_choices_content ----

    def test_extract_pages_from_choices_content_happy_path(self) -> None:
        """A JSON list in choices[0].message.content is parsed and returned as page dicts."""
        page_dicts = [{"index": 0, "markdown": "hello"}, {"index": 1, "markdown": "world"}]
        response = _choices_response(json.dumps(page_dicts))

        result = GatewayCompletionsFactory._extract_pages_from_choices_content(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result == page_dicts

    @pytest.mark.parametrize(
        "payload",
        _FALSY_CHOICES_PAYLOADS,
        ids=[
            "no-choices",
            "empty-choices",
            "choices-not-a-list",
            "message-missing",
            "message-not-a-dict",
            "content-not-a-str",
            "content-json-not-a-list",
            "content-malformed-json",
        ],
    )
    def test_extract_pages_from_choices_content_falsy_paths_return_none(self, payload: dict[str, Any]) -> None:
        """Every malformed or missing choices/message/content shape returns None, never raises."""
        response = _response(payload)

        result = GatewayCompletionsFactory._extract_pages_from_choices_content(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result is None

    # ---- Azure Doc Intel ----

    def test_azure_top_level_pages_with_images(self) -> None:
        """Top-level pages parse into Pages, mapping image fields into ExtractedImageFromPage."""
        response = _response(
            {
                "pages": [
                    {
                        "index": 2,
                        "markdown": "# Invoice page",
                        "images": [
                            {
                                "base64_str": "QUJD",
                                "mime_type": "image/png",
                                "caption": "Company logo",
                                "bounding_box": {
                                    "top_left_x": 1.0,
                                    "top_left_y": 2.0,
                                    "top_right_x": 30.0,
                                    "top_right_y": 2.0,
                                    "bottom_right_x": 30.0,
                                    "bottom_right_y": 40.0,
                                    "bottom_left_x": 1.0,
                                    "bottom_left_y": 40.0,
                                },
                            }
                        ],
                    }
                ],
            },
        )

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_azure(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages.keys()) == [2]
        page = extract_output.pages[2]
        assert page.text == "# Invoice page"
        assert len(page.extracted_images) == 1
        extracted_image = page.extracted_images[0]
        assert extracted_image.size is None
        assert extracted_image.base64_str == "QUJD"
        assert extracted_image.mime_type == "image/png"
        assert extracted_image.caption == "Company logo"
        assert extracted_image.bounding_box is not None
        assert extracted_image.bounding_box.top_left_x == 1.0
        assert extracted_image.bounding_box.bottom_right_y == 40.0

    def test_azure_falls_back_to_choices_content(self) -> None:
        """Without a top-level pages field, pages are recovered from choices[0].message.content."""
        page_dicts: list[dict[str, Any]] = [{"index": 0, "markdown": "Fallback page", "images": []}]
        response = _choices_response(json.dumps(page_dicts))

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_azure(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages.keys()) == [0]
        assert extract_output.pages[0].text == "Fallback page"
        assert extract_output.pages[0].extracted_images == []

    def test_azure_without_pages_anywhere_raises(self) -> None:
        """Neither a top-level pages field nor a choices fallback means the response is unusable."""
        with pytest.raises(GatewayExtractResponseError, match="does not have pages"):
            GatewayCompletionsFactory._make_extract_output_from_response_azure(response=_response({"success": True}))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_azure_page_schema_violation_is_wrapped(self) -> None:
        """A page dict failing GatewayExtractPageAzure validation is wrapped in GatewayExtractResponseError."""
        response = _response({"pages": [{"index": 0, "images": []}]})

        with pytest.raises(GatewayExtractResponseError, match="Azure schema"):
            GatewayCompletionsFactory._make_extract_output_from_response_azure(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # ---- Mistral Doc AI ----

    def test_mistral_without_pages_raises(self) -> None:
        """A response with no pages attribute is rejected (Mistral has no choices fallback)."""
        with pytest.raises(GatewayExtractResponseError, match="does not have pages"):
            GatewayCompletionsFactory._make_extract_output_from_response_mistral(response=_response({"success": True}))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_mistral_pages_with_images_corner_handling(self) -> None:
        """Images without base64 are skipped; full corner coords build a BoundingBox; partial coords leave it None."""
        response = _response(
            {
                "pages": [
                    {
                        "index": 0,
                        "markdown": "# Report",
                        "images": [
                            {"image_base64": None, "image_annotation": "ghost"},
                            {
                                "image_base64": "data:image/png;base64,QUJD",
                                "top_left_x": 10,
                                "top_left_y": 20,
                                "bottom_right_x": 110,
                                "bottom_right_y": 220,
                                "image_annotation": "figure 1",
                            },
                            {"image_base64": "data:image/png;base64,REVG", "top_left_x": 5},
                        ],
                    }
                ],
            },
        )

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_mistral(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages.keys()) == [0]
        page = extract_output.pages[0]
        assert page.text == "# Report"
        # The image without image_base64 is skipped entirely
        assert len(page.extracted_images) == 2
        full_corners_image = page.extracted_images[0]
        assert full_corners_image.actual_url_or_prefixed_base64 == "data:image/png;base64,QUJD"
        assert full_corners_image.base64_str == "QUJD"
        assert full_corners_image.mime_type == "image/png"
        assert full_corners_image.caption == "figure 1"
        assert full_corners_image.bounding_box is not None
        assert full_corners_image.bounding_box.top_left_x == 10.0
        assert full_corners_image.bounding_box.top_left_y == 20.0
        assert full_corners_image.bounding_box.top_right_x == 110.0
        assert full_corners_image.bounding_box.top_right_y == 20.0
        assert full_corners_image.bounding_box.bottom_right_x == 110.0
        assert full_corners_image.bounding_box.bottom_right_y == 220.0
        assert full_corners_image.bounding_box.bottom_left_x == 10.0
        assert full_corners_image.bounding_box.bottom_left_y == 220.0
        partial_corners_image = page.extracted_images[1]
        assert partial_corners_image.bounding_box is None

    def test_mistral_page_schema_violation_is_wrapped(self) -> None:
        """A page dict failing GatewayExtractPageMistral validation is wrapped in GatewayExtractResponseError."""
        response = _response({"pages": [{"index": 0, "markdown": "missing images field"}]})

        with pytest.raises(GatewayExtractResponseError, match="Mistral schema"):
            GatewayCompletionsFactory._make_extract_output_from_response_mistral(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # ---- DeepSeek OCR ----

    def test_deepseek_top_level_pages_happy_path(self) -> None:
        """Top-level pages parse into text-only Pages with no extracted images."""
        response = _response({"pages": [{"index": 1, "markdown": "## Page two"}]})

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_deepseek(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages.keys()) == [1]
        assert extract_output.pages[1].text == "## Page two"
        assert extract_output.pages[1].extracted_images == []

    def test_deepseek_scaled_down_image_logs_warning_and_parses(self, mocker: MockerFixture) -> None:
        """source_image_info.scaled_down triggers the warning branch without breaking the parse."""
        mock_log = mocker.patch(f"{_FACTORY_NAMESPACE}.log")
        response = _response(
            {
                "pages": [
                    {
                        "index": 0,
                        "markdown": "Scaled page",
                        "source_image_info": {
                            "original": {"width": 2000, "height": 1000, "bytes": 204800},
                            "processed": {"width": 1000, "height": 500, "bytes": 51200},
                            "scaled_down": True,
                        },
                    }
                ],
            },
        )

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_deepseek(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert extract_output.pages[0].text == "Scaled page"
        mock_log.warning.assert_called_once()
        warning_message = mock_log.warning.call_args.args[0]
        assert "scaled down from 2000x1000" in warning_message
        assert "to 1000x500" in warning_message

    def test_deepseek_falls_back_to_choices_content(self) -> None:
        """Without a top-level pages field, pages are recovered from choices[0].message.content."""
        page_dicts = [{"index": 0, "markdown": "Fallback md"}]
        response = _choices_response(json.dumps(page_dicts))

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_deepseek(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages.keys()) == [0]
        assert extract_output.pages[0].text == "Fallback md"

    def test_deepseek_without_pages_anywhere_raises(self) -> None:
        """Neither a top-level pages field nor a choices fallback means the response is unusable."""
        with pytest.raises(GatewayExtractResponseError, match="does not have pages"):
            GatewayCompletionsFactory._make_extract_output_from_response_deepseek(response=_response({"success": True}))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_deepseek_page_schema_violation_is_wrapped(self) -> None:
        """A page dict failing GatewayExtractPageDeepseek validation is wrapped in GatewayExtractResponseError."""
        response = _response({"pages": [{"markdown": "missing index"}]})

        with pytest.raises(GatewayExtractResponseError, match="Deepseek schema"):
            GatewayCompletionsFactory._make_extract_output_from_response_deepseek(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # ---- Linkup fetch ----

    def test_linkup_fetch_happy_path(self) -> None:
        """A valid fetch result in choices content becomes a single page at index 0,
        with markdown, raw_html, and images whose empty alt maps to caption None.
        """
        fetch_payload = {
            "markdown": "# Fetched",
            "raw_html": "<html><body>hi</body></html>",
            "images": [
                {"url": "https://site.example/a.png", "alt": ""},
                {"url": "https://site.example/b.png", "alt": "Logo"},
            ],
        }
        response = _choices_response(json.dumps(fetch_payload))

        extract_output = GatewayCompletionsFactory._make_extract_output_from_response_linkup_fetch(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages.keys()) == [0]
        page = extract_output.pages[0]
        assert page.text == "# Fetched"
        assert page.raw_html == "<html><body>hi</body></html>"
        assert len(page.extracted_images) == 2
        first_image = page.extracted_images[0]
        assert first_image.actual_url == "https://site.example/a.png"
        assert first_image.caption is None
        assert first_image.mime_type is None
        second_image = page.extracted_images[1]
        assert second_image.actual_url == "https://site.example/b.png"
        assert second_image.caption == "Logo"

    @pytest.mark.parametrize(
        "payload",
        [
            {"choices": [{"message": "nope"}]},
            {"choices": [{"message": {"content": 42}}]},
        ],
        ids=["message-not-a-dict", "content-not-a-str"],
    )
    def test_extract_content_string_falsy_paths_return_none(self, payload: dict[str, Any]) -> None:
        """Malformed message/content shapes yield None from the content-string extractor."""
        result = GatewayCompletionsFactory._extract_content_string_from_response(response=_response(payload))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result is None

    def test_linkup_fetch_without_content_raises(self) -> None:
        """A response with no usable choices content cannot be parsed as a fetch result."""
        with pytest.raises(GatewayExtractResponseError, match="does not contain content"):
            GatewayCompletionsFactory._make_extract_output_from_response_linkup_fetch(response=_response({"success": True}))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(
        "invalid_content",
        ["[1, 2]", "{not valid json"],
        ids=["json-but-not-a-fetch-result", "malformed-json"],
    )
    def test_linkup_fetch_invalid_fetch_result_is_wrapped(self, invalid_content: str) -> None:
        """Content that is present but not a valid GatewayFetchResultResponse is wrapped."""
        response = _choices_response(invalid_content)

        with pytest.raises(GatewayExtractResponseError, match="Error parsing Gateway fetch response"):
            GatewayCompletionsFactory._make_extract_output_from_response_linkup_fetch(response=response)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
