"""The files a judgment carries are refused by a model that does not read them, before its backend is called.

Each guard in `JudgmentWorkerAbstract._check_can_read_files` is mutation-tested: break it and exactly
one of these goes red.
"""

from typing import ClassVar

import pytest

from pipelex.cogt.document.prompt_document import PromptDocument, PromptDocumentUri
from pipelex.cogt.exceptions import JudgmentCapabilityError, PromptDocumentFormatError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_models import JudgmentAnswer, JudgmentQuestion, YesNoAnswer, YesNoQuestion
from tests.unit.pipelex.cogt.judgment.fake_judgment_worker import FakeJudgmentWorker, make_fake_judgment_job, make_fake_judgment_model


@pytest.mark.asyncio
class TestJudgmentWorkerFileCapability:
    """The files a judgment carries are refused by a model that does not read them, before the backend is called."""

    _IMAGE = PromptImageUri(uri="pipelex-storage://s/photo.png", mime_type="image/png")
    _PDF = PromptDocumentUri(uri="pipelex-storage://s/claim.pdf", mime_type="application/pdf")
    _DOCX = PromptDocumentUri(
        uri="pipelex-storage://s/claim.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    _QUESTION: ClassVar[dict[str, JudgmentQuestion]] = {"is_urgent": YesNoQuestion(instructions="Is it urgent?")}
    _ANSWER: ClassVar[dict[str, JudgmentAnswer]] = {"is_urgent": YesNoAnswer(probability=0.9)}

    def _worker(self, *, inputs: list[str], max_prompt_images: int | None = None) -> FakeJudgmentWorker:
        return FakeJudgmentWorker(make_fake_judgment_model(inputs=inputs, max_prompt_images=max_prompt_images), answers=self._ANSWER)

    def _job(self, *, images: dict[str, list[PromptImage]] | None = None, documents: dict[str, list[PromptDocument]] | None = None) -> JudgmentJob:
        return make_fake_judgment_job(self._QUESTION, images=images, documents=documents)

    async def test_a_text_only_model_refuses_an_image(self) -> None:
        worker = self._worker(inputs=["text"])

        with pytest.raises(JudgmentCapabilityError, match="does not read images"):
            await worker.judge(self._job(images={"photo": [self._IMAGE]}))

        assert not worker.was_called

    async def test_a_text_only_model_refuses_a_document(self) -> None:
        worker = self._worker(inputs=["text"])

        with pytest.raises(JudgmentCapabilityError, match="does not read documents"):
            await worker.judge(self._job(documents={"claim": [self._PDF]}))

        assert not worker.was_called

    async def test_a_model_reading_images_and_pdf_judges_both(self) -> None:
        worker = self._worker(inputs=["text", "images", "pdf"])

        answers = await worker.judge(self._job(images={"photo": [self._IMAGE]}, documents={"claim": [self._PDF]}))

        assert set(answers) == {"is_urgent"}
        assert worker.was_called

    async def test_a_document_of_a_format_the_model_does_not_read_is_refused(self) -> None:
        worker = self._worker(inputs=["text", "pdf"])

        with pytest.raises(PromptDocumentFormatError, match="does not read"):
            await worker.judge(self._job(documents={"claim": [self._PDF, self._DOCX]}))

        assert not worker.was_called

    async def test_a_document_of_unknown_format_is_left_to_the_provider(self) -> None:
        worker = self._worker(inputs=["text", "pdf"])

        await worker.judge(self._job(documents={"claim": [PromptDocumentUri(uri="pipelex-storage://s/claim")]}))

        assert worker.was_called

    async def test_an_image_input_carrying_a_document_is_refused(self) -> None:
        worker = self._worker(inputs=["text", "images"])

        with pytest.raises(PromptImageFormatError, match="not an image"):
            await worker.judge(self._job(images={"photo": [PromptImageUri(uri="pipelex-storage://s/claim.pdf", mime_type="application/pdf")]}))

        assert not worker.was_called

    async def test_more_images_than_the_model_reads_are_refused(self) -> None:
        worker = self._worker(inputs=["text", "images"], max_prompt_images=1)

        with pytest.raises(JudgmentCapabilityError, match="at most 1 images"):
            await worker.judge(self._job(images={"before": [self._IMAGE], "after": [self._IMAGE]}))

        assert not worker.was_called
