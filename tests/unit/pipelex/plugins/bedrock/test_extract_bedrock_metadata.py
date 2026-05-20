"""Tests for extract_bedrock_metadata helper."""

from __future__ import annotations

from typing import Any, cast

import pytest
from botocore.exceptions import ClientError

from pipelex.cogt.inference.error_classification import extract_bedrock_metadata


def _make_client_error(
    error_code: str,
    error_message: str,
    request_id: str | None = None,
    http_status_code: int | None = None,
    retry_after: str | None = None,
) -> ClientError:
    """Build a botocore ClientError shaped like a real AWS response."""
    response: dict[str, Any] = {"Error": {"Code": error_code, "Message": error_message}}
    response_metadata: dict[str, Any] = {}
    if request_id is not None:
        response_metadata["RequestId"] = request_id
    if http_status_code is not None:
        response_metadata["HTTPStatusCode"] = http_status_code
    if retry_after is not None:
        response_metadata["HTTPHeaders"] = {"retry-after": retry_after}
    if response_metadata:
        response["ResponseMetadata"] = response_metadata
    return ClientError(error_response=cast("Any", response), operation_name="Converse")


class TestExtractBedrockMetadata:
    """extract_bedrock_metadata distills botocore ClientErrors into ProviderErrorMetadata."""

    def test_full_response_metadata(self) -> None:
        sdk_exc = _make_client_error(
            error_code="ThrottlingException",
            error_message="Rate exceeded",
            request_id="req-abc",
            http_status_code=429,
            retry_after="30",
        )
        metadata = extract_bedrock_metadata(sdk_exc)
        assert metadata.provider == "bedrock"
        assert metadata.sdk_exception_type == "ClientError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req-abc"
        assert metadata.retry_after_seconds == 30.0
        assert metadata.provider_error_code == "ThrottlingException"
        body: Any = metadata.body
        assert isinstance(body, dict)
        assert body["Error"]["Code"] == "ThrottlingException"

    def test_minimal_response_no_metadata(self) -> None:
        """With no ``ResponseMetadata``, the HTTP status is derived from the AWS error code."""
        sdk_exc = _make_client_error(error_code="ValidationException", error_message="Invalid parameter")
        metadata = extract_bedrock_metadata(sdk_exc)
        assert metadata.provider == "bedrock"
        assert metadata.sdk_exception_type == "ClientError"
        # No HTTPStatusCode in the response — status is derived from the error code.
        assert metadata.status_code == 400
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code == "ValidationException"

    def test_service_quota_exceeded(self) -> None:
        sdk_exc = _make_client_error(
            error_code="ServiceQuotaExceededException",
            error_message="Quota exceeded",
            http_status_code=400,
        )
        metadata = extract_bedrock_metadata(sdk_exc)
        assert metadata.provider_error_code == "ServiceQuotaExceededException"
        assert metadata.status_code == 400

    def test_access_denied_exception(self) -> None:
        sdk_exc = _make_client_error(
            error_code="AccessDeniedException",
            error_message="Not authorized",
            request_id="aws-req-1",
            http_status_code=403,
        )
        metadata = extract_bedrock_metadata(sdk_exc)
        assert metadata.provider_error_code == "AccessDeniedException"
        assert metadata.status_code == 403
        assert metadata.request_id == "aws-req-1"

    def test_invalid_retry_after_returns_none(self) -> None:
        sdk_exc = _make_client_error(
            error_code="ThrottlingException",
            error_message="Throttled",
            http_status_code=429,
            retry_after="not-a-number",
        )
        metadata = extract_bedrock_metadata(sdk_exc)
        assert metadata.retry_after_seconds is None
        assert metadata.status_code == 429

    def test_malformed_response_dict_tolerated(self) -> None:
        """An exception with no response attribute should produce ``None`` fields."""

        class FakeBoto3Error(Exception):
            pass

        metadata = extract_bedrock_metadata(FakeBoto3Error("boom"))
        assert metadata.provider == "bedrock"
        assert metadata.sdk_exception_type == "FakeBoto3Error"
        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code is None
        assert metadata.body is None

    @pytest.mark.parametrize(
        ("error_code", "expected_status_code"),
        [
            ("ThrottlingException", 429),
            ("ValidationException", 400),
            ("AccessDeniedException", 403),
            ("ResourceNotFoundException", 404),
            ("ServiceUnavailableException", 503),
        ],
    )
    def test_provider_error_code_set_per_aws_code(self, error_code: str, expected_status_code: int) -> None:
        sdk_exc = _make_client_error(
            error_code=error_code,
            error_message=f"{error_code} happened",
            http_status_code=expected_status_code,
        )
        metadata = extract_bedrock_metadata(sdk_exc)
        assert metadata.provider_error_code == error_code
        assert metadata.status_code == expected_status_code
