"""A model spec's `inputs` names the file formats the model reads, with the same keys every format check compares.

An extractor's readable formats are its declared `pdf`, `docx`, `pptx`, `xlsx`, `html`, `md`, `csv`,
`txt`, `vtt`, `eml` and `image`; `web_page` is not a file format, since a web-page model fetches its page itself. An LLM's readable
document types are its declared `pdf`, `docx`, `pptx`, `xlsx` and `html`; its vision flag stays `images`.
"""

import pytest

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory


def _make_spec(*, model_type: ModelType, inputs: list[str]) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test",
        name="test-model",
        sdk="test_sdk",
        model_type=model_type,
        model_id="test-model-id",
        inputs=inputs,
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


class TestModelSpecReadableFormats:
    @pytest.mark.parametrize(
        ("inputs", "expected"),
        [
            (["pdf", "image"], {"pdf", "image"}),
            (["pdf", "docx", "pptx", "xlsx", "html", "image"], {"pdf", "docx", "pptx", "xlsx", "html", "image"}),
            (["md", "csv", "txt", "vtt", "eml", "text"], {"md", "csv", "txt", "vtt", "eml"}),
            (["web_page"], set[str]()),
            (["pdf", "web_page", "captions"], {"pdf"}),
            ([], set[str]()),
        ],
    )
    def test_an_extractor_reads_the_file_formats_it_declares(self, inputs: list[str], expected: set[str]):
        spec = _make_spec(model_type=ModelType.TEXT_EXTRACTOR, inputs=inputs)

        assert spec.readable_formats_for_extract == expected

    @pytest.mark.parametrize(
        ("inputs", "expected"),
        [
            (["text", "images", "pdf"], {"pdf"}),
            (["text", "pdf", "docx", "pptx", "xlsx", "html"], {"pdf", "docx", "pptx", "xlsx", "html"}),
            (["text", "images"], set[str]()),
        ],
    )
    def test_an_llm_reads_the_document_types_it_declares(self, inputs: list[str], expected: set[str]):
        spec = _make_spec(model_type=ModelType.LLM, inputs=inputs)

        assert spec.supported_document_types == expected
        assert spec.is_document_supported == bool(expected)
