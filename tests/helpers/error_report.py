"""Test helper for building ``ErrorReport`` instances with sensible defaults.

Every ``ErrorReport`` requires its ``code``, ``title`` and ``type_uri``, so every
test fixture that constructs one directly must pass them. Tests whose focus is
classification, HTTP status, or domain — not serialization — use this helper so
each fixture stays a single readable call. Serialization / round-trip /
disclosure tests should pass real values instead, or build the report with
``ErrorReport.make_for_code``, which reads them from the code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ErrorReport

if TYPE_CHECKING:
    from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction

_DEFAULT_TITLE = "Test error"
_DEFAULT_TYPE_URI = "https://test.pipelex.dev/errors/test-error/"


def make_error_report(
    error_type: str = "TestError",
    message: str = "test error message",
    *,
    code: str = CoreCode.RUNTIME_UNEXPECTED,
    title: str = _DEFAULT_TITLE,
    type_uri: str = _DEFAULT_TYPE_URI,
    error_category: str | None = None,
    error_domain: str | None = None,
    retryable: bool | None = None,
    user_action: UserAction | None = None,
    model: str | None = None,
    provider: str | None = None,
    provider_metadata: ProviderErrorMetadata | None = None,
) -> ErrorReport:
    """Build an ``ErrorReport`` with test-friendly defaults for ``code`` / ``title`` / ``type_uri``."""
    return ErrorReport(
        code=code,
        error_type=error_type,
        message=message,
        title=title,
        type_uri=type_uri,
        error_category=error_category,
        error_domain=error_domain,
        retryable=retryable,
        user_action=user_action,
        model=model,
        provider=provider,
        provider_metadata=provider_metadata,
    )
