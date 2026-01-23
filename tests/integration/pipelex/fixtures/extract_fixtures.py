"""Extract/OCR related test fixtures."""

from pathlib import Path

import pytest

from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.hub import get_model_deck
from pipelex.tools.misc.toml_utils import load_toml_from_path


def is_extract_handle_supported(extract_handle: str) -> bool:
    """Check if an extract handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(extract_handle)


# ================================================================================================
# Extract model collections are now defined in .pipelex/test_profiles.toml
# See [collections.extract] section for from_pdf and from_image lists
# ================================================================================================


def _load_extract_collection(collection_name: str) -> list[str]:
    """Load an extract collection from test_profiles.toml.

    Args:
        collection_name: Name of the collection (e.g., "from_pdf", "from_image").

    Returns:
        List of model handles in the collection.
    """
    test_profiles_path = Path(".pipelex/test_profiles.toml")
    if not test_profiles_path.exists():
        return []

    try:
        profiles_config = load_toml_from_path(str(test_profiles_path))
        collections = profiles_config.get("collections", {})
        extract_collections = collections.get("extract", {})
        model_list = extract_collections.get(collection_name, [])
        if isinstance(model_list, list):
            return [str(mdl) for mdl in model_list]  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        return []
    except Exception:
        return []


# Load collections at module level for pytest parametrization
EXTRACT_HANDLE_FROM_PDF = _load_extract_collection("from_pdf")
EXTRACT_HANDLE_FROM_IMAGE = _load_extract_collection("from_image")


@pytest.fixture(
    params=EXTRACT_HANDLE_FROM_PDF,
)
def extract_handle_from_pdf(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    extract_handle_param = request.param
    if not is_extract_handle_supported(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not available in model deck")
    return extract_handle_param


@pytest.fixture(
    params=EXTRACT_HANDLE_FROM_IMAGE,
)
def extract_handle_from_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    extract_handle_param = request.param
    if not is_extract_handle_supported(extract_handle_param):
        pytest.skip(f"Extract handle '{extract_handle_param}' not available in model deck")
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
