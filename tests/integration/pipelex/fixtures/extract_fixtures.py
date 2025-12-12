"""Extract/OCR related test fixtures."""

import pytest

from pipelex.hub import get_model_deck
from tests.integration.pipelex.fixtures.routing_fixtures import ALL_BACKENDS, check_backend_supports_model


def is_extract_handle_supported(extract_handle: str) -> bool:
    """Check if an extract handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(extract_handle)


def is_extract_handle_supported_by_enabled_backends(extract_handle: str) -> bool:
    """Check if an extract handle is supported by at least one enabled backend."""
    return any(check_backend_supports_model(backend, extract_handle) for backend in ALL_BACKENDS)


# ================================================================================================
# Extract Handles by Backend
# Comment out handles you don't want to test
# ================================================================================================

EXTRACT_HANDLE_FROM_PDF = [
    "pypdfium2-extract-text",
    "docling-extract-text",
    "mistral-ocr",
]

EXTRACT_HANDLE_FROM_IMAGE = [
    "docling-extract-text",
    "mistral-ocr",
]

ALL_EXTRACT_HANDLES: list[str] = list(set(EXTRACT_HANDLE_FROM_PDF + EXTRACT_HANDLE_FROM_IMAGE))


@pytest.fixture(
    params=ALL_EXTRACT_HANDLES,
)
def extract_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    extract_handle_param = request.param
    if not is_extract_handle_supported(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not available in model deck")
    if not is_extract_handle_supported_by_enabled_backends(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not supported by any enabled backend")
    return extract_handle_param


@pytest.fixture(
    params=EXTRACT_HANDLE_FROM_PDF,
)
def extract_handle_from_pdf(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    extract_handle_param = request.param
    if not is_extract_handle_supported(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not available in model deck")
    if not is_extract_handle_supported_by_enabled_backends(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not supported by any enabled backend")
    return extract_handle_param


@pytest.fixture(
    params=EXTRACT_HANDLE_FROM_IMAGE,
)
def extract_handle_from_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    extract_handle_param = request.param
    if not is_extract_handle_supported(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not available in model deck")
    if not is_extract_handle_supported_by_enabled_backends(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not supported by any enabled backend")
    return extract_handle_param


@pytest.fixture(
    params=[
        "extract_text_from_visuals",
        "extract_text_from_pdf",
    ],
)
def extract_choice_for_pdf(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "extract_text_from_visuals",
    ],
)
def extract_choice_for_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
