from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobConfig, ImgGenJobParams, ImgGenJobReport, SizeTier
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint, InferenceModelSpecFactory
from pipelex.providers.manifold.manifold_factory import ManifoldFactory
from tests.unit.pipelex.providers.manifold.test_data import ManifoldExtrasBySpecTestData, ManifoldMetadataTestData

if TYPE_CHECKING:
    from pipelex.cogt.image.image_size import ImageSize
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


def _spec(*, handle: str, entry: dict[str, Any]) -> InferenceModelSpec:
    """The spec the manifold backend would build from this catalog table, through the real factory."""
    return InferenceModelSpecFactory.make_inference_model_spec(
        PipelexBackend.MANIFOLD,
        name=handle,
        blueprint=InferenceModelSpecBlueprint.model_validate(entry),
        backend_listed_constraints=[],
        backend_valued_constraints={},
    )


def _img_gen_job(*, aspect_ratio: AspectRatio, size: SizeTier | ImageSize | None) -> ImgGenJob:
    return ImgGenJob(
        job_metadata=ManifoldMetadataTestData.JOB_METADATA,
        img_gen_prompt=ImgGenPrompt(positive_text="a lighthouse at dusk"),
        job_params=ImgGenJobParams(aspect_ratio=aspect_ratio, size=size, background=Background.AUTO),
        job_config=ImgGenJobConfig(is_sync_mode=True),
        job_report=ImgGenJobReport(),
    )


def _llm_job() -> LLMJob:
    return LLMJob(
        job_metadata=ManifoldMetadataTestData.JOB_METADATA,
        llm_prompt=LLMPrompt(user_text="ping"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(),
    )


class TestManifoldExtrasBySpec:
    @pytest.mark.parametrize(
        ("handle", "entry", "aspect_ratio", "size", "expected_image_config"),
        ManifoldExtrasBySpecTestData.GEMINI_IMAGE_CASES,
    )
    def test_gemini_image_spec_gets_image_config(
        self,
        handle: str,
        entry: dict[str, Any],
        aspect_ratio: AspectRatio,
        size: SizeTier | ImageSize | None,
        expected_image_config: dict[str, str],
    ) -> None:
        """A Gemini taxonomy in the rules sends `image_config`, whether the model id is the provider's or defaults to the handle."""
        spec = _spec(handle=handle, entry=entry)
        assert spec.model_id == entry.get("model_id", handle)

        _, extra_body = ManifoldFactory.make_extras(spec, inference_job=_img_gen_job(aspect_ratio=aspect_ratio, size=size), output_desc="Image")

        assert extra_body == {"image_config": expected_image_config}

    @pytest.mark.parametrize(
        ("topic", "handle", "entry"),
        ManifoldExtrasBySpecTestData.NON_GEMINI_IMAGE_CASES,
    )
    def test_non_gemini_image_spec_gets_no_image_config(
        self,
        topic: str,  # ruff: ignore[unused-method-argument]
        handle: str,
        entry: dict[str, Any],
    ) -> None:
        """Without a Gemini taxonomy in the rules no `image_config` is sent, even under a `gemini` model id."""
        spec = _spec(handle=handle, entry=entry)

        _, extra_body = ManifoldFactory.make_extras(
            spec, inference_job=_img_gen_job(aspect_ratio=AspectRatio.SQUARE, size=SizeTier.ONE_K), output_desc="Image"
        )

        assert extra_body == {}

    @pytest.mark.parametrize("size", [None, SizeTier.ONE_K])
    def test_unknown_taxonomy_is_refused(self, size: SizeTier | None) -> None:
        """An aspect_ratio value this release does not know fails the job instead of dropping the ratio and size silently."""
        spec = _spec(handle="nano-banana-next", entry=ManifoldExtrasBySpecTestData.UNKNOWN_TAXONOMY_ENTRY)

        with pytest.raises(ImgGenParameterError, match="unknown aspect_ratio taxonomy 'gemini_from_the_future'"):
            ManifoldFactory.make_extras(spec, inference_job=_img_gen_job(aspect_ratio=AspectRatio.SQUARE, size=size), output_desc="Image")

    def test_size_beyond_the_gemini_taxonomy_is_refused(self) -> None:
        """A handle-only Gemini spec still checks the request against its taxonomy's grids."""
        spec = _spec(handle="nano-banana", entry=ManifoldExtrasBySpecTestData.GEMINI_IMAGE_CASES[0][1])

        with pytest.raises(ImgGenParameterError, match="does not support image size '2K'"):
            ManifoldFactory.make_extras(spec, inference_job=_img_gen_job(aspect_ratio=AspectRatio.SQUARE, size=SizeTier.TWO_K), output_desc="Image")

    @pytest.mark.parametrize(
        ("topic", "handle", "entry", "expects_seed"),
        ManifoldExtrasBySpecTestData.MISTRAL_SEED_CASES,
    )
    def test_mistral_seed_follows_the_model_id_prefix(
        self,
        topic: str,  # ruff: ignore[unused-method-argument]
        handle: str,
        entry: dict[str, Any],
        expects_seed: bool,
    ) -> None:
        """The Mistral seed is sent for the manifold Mistral handle with or without a provider model id, and only for it."""
        spec = _spec(handle=handle, entry=entry)

        _, extra_body = ManifoldFactory.make_extras(spec, inference_job=_llm_job(), output_desc="text")

        if expects_seed:
            assert set(extra_body) == {"seed"}
            assert 0 <= extra_body["seed"] <= 1000000
        else:
            assert extra_body == {}
