"""Job metadata the manifold tests hand to a request, the header value it must produce, and catalog entries with the extras they yield."""

from typing import Any, ClassVar

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.system.job_metadata import JobMetadata, RunMetadata


class ManifoldMetadataTestData:
    """A job whose run carries host labels, and the exact `x-pipelex-metadata` value it yields.

    The expected value is written out as the wire string rather than rebuilt from the job, so a
    change to the encoding (key order, separators, escaping) turns a test red instead of moving with it.
    """

    EXTRAS: ClassVar[dict[str, str]] = {"org_id": "org_acme", "api_key_id": "key_123"}

    JOB_METADATA: ClassVar[JobMetadata] = JobMetadata(
        run_metadata=RunMetadata(
            storage_scope="test/scope",
            read_scope=None,
            user_id="user_42",
            pipeline_run_id="run_abc",
            extras={"org_id": "org_acme", "api_key_id": "key_123"},
        ),
        pipe_code="summarize_doc",
        pipe_run_id="0123456789abcdef",
        content_generation_job_id="cgj_1",
    )

    EXPECTED_HEADER_VALUE: ClassVar[str] = (
        '{"org_id":"org_acme","api_key_id":"key_123","user_id":"user_42","pipeline_run_id":"run_abc",'
        '"pipe_run_id":"0123456789abcdef","pipe_code":"summarize_doc","content_generation_job_id":"cgj_1"}'
    )


class ManifoldExtrasBySpecTestData:
    """Manifold catalog entries, written as the tables a catalog holds, and the body extras each must produce.

    The Gemini image entries carry no `model_id`, as the hosted catalog serves them: the spec's
    model id then defaults to the handle, which does not start with `gemini`, so only the spec's
    image rules can say that `image_config` is due. Each case is (handle, catalog entry, aspect
    ratio, size, expected `image_config`).
    """

    GEMINI_IMAGE_CASES: ClassVar[list[tuple[str, dict[str, Any], AspectRatio, SizeTier | ImageSize | None, dict[str, str]]]] = [
        (
            "nano-banana",
            {"model_type": "img_gen", "sdk": "manifold_completions", "rules": {"aspect_ratio": "gemini_2_5"}},
            AspectRatio.LANDSCAPE_16_9,
            None,
            {"aspect_ratio": "16:9"},
        ),
        (
            "nano-banana-pro",
            {"model_type": "img_gen", "sdk": "manifold_completions", "rules": {"aspect_ratio": "gemini_3_pro"}},
            AspectRatio.PORTRAIT_9_16,
            SizeTier.TWO_K,
            {"aspect_ratio": "9:16", "image_size": "2K"},
        ),
        (
            "nano-banana-2",
            {"model_type": "img_gen", "sdk": "manifold_completions", "rules": {"aspect_ratio": "gemini_3_flash"}},
            AspectRatio.LANDSCAPE_4_1,
            SizeTier.FOUR_K,
            {"aspect_ratio": "4:1", "image_size": "4K"},
        ),
        (
            "nano-banana-2-lite",
            {"model_type": "img_gen", "sdk": "manifold_completions", "rules": {"aspect_ratio": "gemini_3_flash_lite"}},
            AspectRatio.SQUARE,
            SizeTier.ONE_K,
            {"aspect_ratio": "1:1", "image_size": "1K"},
        ),
        (
            "nano-banana",
            {"model_type": "img_gen", "sdk": "manifold_completions", "model_id": "gemini-2.5-flash-image", "rules": {"aspect_ratio": "gemini_2_5"}},
            AspectRatio.PORTRAIT_3_4,
            None,
            {"aspect_ratio": "3:4"},
        ),
    ]

    # (topic, handle, catalog entry): image models whose spec names no Gemini taxonomy get no `image_config`,
    # whatever their name or model id says.
    NON_GEMINI_IMAGE_CASES: ClassVar[list[tuple[str, str, dict[str, Any]]]] = [
        (
            "gpt_image_legacy",
            "gpt-image-1",
            {"model_type": "img_gen", "sdk": "manifold_img_gen", "rules": {"model_choice": "model_name", "aspect_ratio": "gpt_image_legacy"}},
        ),
        (
            "gpt_image_2",
            "gpt-image-2",
            {"model_type": "img_gen", "sdk": "manifold_img_gen", "rules": {"model_choice": "model_name", "aspect_ratio": "gpt_image_2"}},
        ),
        (
            "gemini_id_without_rules",
            "gemini-lookalike",
            {"model_type": "img_gen", "sdk": "manifold_completions", "model_id": "gemini-2.5-flash-image"},
        ),
        (
            "unknown_taxonomy",
            "nano-banana-next",
            {"model_type": "img_gen", "sdk": "manifold_completions", "rules": {"aspect_ratio": "gemini_from_the_future"}},
        ),
    ]

    # (topic, handle, catalog entry, whether the job gets a seed): the Mistral seed still keys on the model id's prefix,
    # which the one manifold Mistral handle carries whether or not the entry names the provider's id.
    MISTRAL_SEED_CASES: ClassVar[list[tuple[str, str, dict[str, Any], bool]]] = [
        ("mistral_handle_only", "mistral-large", {"sdk": "manifold_completions", "structure_method": "instructor/mistral_tools"}, True),
        (
            "mistral_provider_id",
            "mistral-large",
            {"sdk": "manifold_completions", "model_id": "Mistral-Large-3", "structure_method": "instructor/mistral_tools"},
            True,
        ),
        ("not_mistral", "gpt-4o", {"sdk": "manifold_responses"}, False),
    ]
