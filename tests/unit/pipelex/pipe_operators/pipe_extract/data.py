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
            output="native.Page",
        ),
    )

    VALID_PDF_INPUT: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_pdf_input",
        PipeExtractBlueprint(
            description="Test case: valid_pdf_input",
            inputs={"document": "native.PDF"},
            output="native.Page",
        ),
    )

    VALID_IMAGE_WITH_PAGE_IMAGES: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_image_with_page_images",
        PipeExtractBlueprint(
            description="Test case: valid_image_with_page_images",
            inputs={"invoice_image": "native.Image"},
            output="native.Page",
            page_images=True,
        ),
    )

    VALID_PDF_WITH_PAGE_VIEWS: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_pdf_with_page_views",
        PipeExtractBlueprint(
            description="Test case: valid_pdf_with_page_views",
            inputs={"contract": "native.PDF"},
            output="native.Page",
            page_views=True,
            page_views_dpi=150,
        ),
    )

    VALID_IMAGE_WITH_CAPTIONS: ClassVar[tuple[str, PipeExtractBlueprint]] = (
        "valid_image_with_captions",
        PipeExtractBlueprint(
            description="Test case: valid_image_with_captions",
            inputs={"report_image": "native.Image"},
            output="native.Page",
            page_images=True,
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

    # Error test cases: (test_id, blueprint, expected_error_message_fragment)
    ERROR_NO_INPUT: ClassVar[tuple[str, PipeExtractBlueprint, str]] = (
        "no_input",
        PipeExtractBlueprint(
            description="Test case: no_input",
            inputs={},
            output="native.Page",
        ),
        "missing_input_variable",
    )

    ERROR_TOO_MANY_INPUTS: ClassVar[tuple[str, PipeExtractBlueprint, str]] = (
        "too_many_inputs",
        PipeExtractBlueprint(
            description="Test case: too_many_inputs",
            inputs={"image1": "native.Image", "image2": "native.Image"},
            output="native.Page",
        ),
        "too_many_candidate_inputs",
    )

    ERROR_WRONG_INPUT_TYPE: ClassVar[tuple[str, PipeExtractBlueprint, str]] = (
        "wrong_input_type",
        PipeExtractBlueprint(
            description="Test case: wrong_input_type",
            inputs={"text_doc": "native.Text"},
            output="native.Page",
        ),
        "inadequate_input_concept",
    )

    ERROR_CASES: ClassVar[list[tuple[str, PipeExtractBlueprint, str]]] = [
        ERROR_NO_INPUT,
        ERROR_TOO_MANY_INPUTS,
        ERROR_WRONG_INPUT_TYPE,
    ]
