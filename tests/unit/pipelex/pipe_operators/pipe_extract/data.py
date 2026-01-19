from typing import ClassVar

from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractInputTestCases:
    """Test cases for PipeExtract input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_IMAGE_INPUT: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_image_input",
        PipeExtractBlueprint(
            description="Test case: valid_image_input",
            inputs={"document_image": "native.Image"},
            output="native.Page[]",
        ),
    )

    VALID_PDF_INPUT: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_pdf_input",
        PipeExtractBlueprint(
            description="Test case: valid_pdf_input",
            inputs={"document": "native.Document"},
            output="native.Page[]",
        ),
    )

    VALID_IMAGE_WITH_PAGE_IMAGES: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_image_with_max_page_images",
        PipeExtractBlueprint(
            description="Test case: valid_image_with_max_page_images",
            inputs={"invoice_image": "native.Image"},
            output="native.Page[]",
            max_page_images=None,
        ),
    )

    VALID_PDF_WITH_PAGE_VIEWS: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_pdf_with_page_views",
        PipeExtractBlueprint(
            description="Test case: valid_pdf_with_page_views",
            inputs={"contract": "native.Document"},
            output="native.Page[]",
            page_views=True,
            page_views_dpi=150,
        ),
    )

    VALID_IMAGE_WITH_CAPTIONS: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_image_with_captions",
        PipeExtractBlueprint(
            description="Test case: valid_image_with_captions",
            inputs={"report_image": "native.Image"},
            output="native.Page[]",
            max_page_images=None,
            page_image_captions=True,
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeExtractBlueprint]]] = [
        VALID_IMAGE_INPUT,
        VALID_PDF_INPUT,
        VALID_IMAGE_WITH_PAGE_IMAGES,
        VALID_PDF_WITH_PAGE_VIEWS,
        VALID_IMAGE_WITH_CAPTIONS,
    ]
