"""Extract/OCR related test fixtures."""

import pytest

from pipelex.cogt.extract.extract_job_components import ExtractJobParams
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
    "pypdfium2-extract-pdf",
    "docling-extract-text",
    "mistral-ocr",
    "mistral-ocr-2503",
    "mistral-ocr-2505",
    "mistral-ocr-2512",
    "mistral-document-ai-2505",
    "azure-document-intelligence",
]

EXTRACT_HANDLE_FROM_IMAGE = [
    "docling-extract-text",
    "mistral-ocr",
    "mistral-ocr-2503",
    "mistral-ocr-2505",
    "mistral-ocr-2512",
    "deepseek-ocr",
    "azure-document-intelligence",
]

ALL_EXTRACT_HANDLES: list[str] = list(set(EXTRACT_HANDLE_FROM_PDF + EXTRACT_HANDLE_FROM_IMAGE))


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
        "extract_ocr_from_document",
        "extract_basic_from_pdf",
    ],
)
def extract_choice_for_pdf(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "extract_ocr_from_document",
    ],
)
def extract_choice_for_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # max_nb_images=None: Extract all images (unlimited)
        ExtractJobParams(
            max_nb_images=None,
            should_caption_images=False,
            should_include_page_views=False,
            page_views_dpi=72,
            image_min_size=None,
        ),
        # max_nb_images=10: Limit to 10 images
        ExtractJobParams(
            max_nb_images=10,
            should_caption_images=True,
            should_include_page_views=False,
            page_views_dpi=72,
            image_min_size=100,
        ),
        # max_nb_images=0: No images but page_views True
        ExtractJobParams(
            max_nb_images=0,
            should_caption_images=False,
            should_include_page_views=True,
            page_views_dpi=150,
            image_min_size=None,
        ),
        # max_nb_images=0: No images and no page_views
        ExtractJobParams(
            max_nb_images=0,
            should_caption_images=False,
            should_include_page_views=False,
            page_views_dpi=None,
            image_min_size=None,
        ),
    ],
)
def extract_job_params(request: pytest.FixtureRequest) -> ExtractJobParams:
    assert isinstance(request.param, ExtractJobParams)
    return request.param
