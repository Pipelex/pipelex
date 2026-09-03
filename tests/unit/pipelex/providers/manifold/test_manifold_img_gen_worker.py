"""The image worker's escape paths — the ones that re-bill a generation if they leak.

The HTTP request succeeds in every test here; it is the *body* that is wrong. A raw exception at
this point is neither a `PipelexError` nor annotated with the model, so it slips past the Temporal
error bridge (`convert_pipelex_errors`), gets marked retryable, and resubmits a non-idempotent image
generation — the user pays twice for one picture.

**The `JSONDecodeError` arm is the one with no symptom.** A 2xx carrying an intermediary's HTML
error page makes the SDK's own decode raise, and `json.JSONDecodeError` is not an `APIError`, so it
falls straight through the `except (portkey_exceptions.APIError, portkey_vendored_openai.APIError)`
arm that catches everything else. Nothing about the code reads as missing a case.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from portkey_ai.api_resources import exceptions as portkey_exc

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.manifold.manifold_img_gen_worker import ManifoldImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# A one-pixel PNG, so the success path reaches the real image decoding rather than stopping earlier.
_PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

_AZURE_GPT_IMAGE_BODY = {
    "data": [{"b64_json": _PNG_1PX}],
    "size": "1024x1024",
    "output_format": "png",
    "usage": {"input_tokens": 11, "output_tokens": 22},
}


def _make_worker(mocker: MockerFixture) -> ManifoldImgGenWorker:
    worker = object.__new__(ManifoldImgGenWorker)
    model = mocker.MagicMock()
    model.model_id = "gpt-image-1"
    model.name = "gpt-image-1"
    model.desc = "test-manifold-img-gen"
    model.rules = mocker.MagicMock()
    worker.inference_model = model
    client = mocker.MagicMock()
    client.images.generate = mocker.AsyncMock()
    client.images.edit = mocker.AsyncMock()
    worker.portkey_client = client
    return worker


def _images(worker: ManifoldImgGenWorker) -> Any:
    """The stand-in for the vendor client's Images resource, as `Any` so its mocks typecheck."""
    return worker.portkey_client.images


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a manifold, rendered"
    job.job_report.img_gen_tokens_usage = None
    return job


def _patch_args_factory(mocker: MockerFixture, *, args: dict[str, Any] | None = None) -> None:
    mocker.patch(
        "pipelex.providers.manifold.manifold_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
        new_callable=mocker.AsyncMock,
        return_value=args if args is not None else {"prompt": "a manifold, rendered"},
    )


# Each body is a 2xx the worker must refuse rather than let escape, with the advice it deserves:
# a shape it cannot read at all is the model's fault, a stripped image is the prompt's.
_MALFORMED_BODIES: list[tuple[dict[str, Any], UserActionKind]] = [
    ({"data": [], "size": "1024x1024", "output_format": "png"}, UserActionKind.CHANGE_MODEL),
    ({"data": [{}], "size": "1024x1024", "output_format": "png"}, UserActionKind.CHANGE_INPUT),
    ({"data": [{"b64_json": _PNG_1PX}], "size": "wide x tall", "output_format": "png"}, UserActionKind.CHANGE_MODEL),
    ({"data": [{"b64_json": _PNG_1PX}], "output_format": "png"}, UserActionKind.CHANGE_MODEL),
]


def _make_response(mocker: MockerFixture, body: dict[str, Any]) -> Any:
    response = mocker.MagicMock()
    response.model_dump.return_value = body
    return response


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldImgGenWorkerSuccess:
    async def test_an_azure_gpt_image_body_becomes_generated_images(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        _patch_args_factory(mocker)
        _images(worker).generate.return_value = _make_response(mocker, _AZURE_GPT_IMAGE_BODY)

        images = await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert len(images) == 1
        generated = images[0]
        assert generated.base64_str == _PNG_1PX
        assert generated.size is not None
        assert (generated.size.width, generated.size.height) == (1024, 1024)
        assert generated.image_format == "png"

    async def test_input_images_route_to_the_edits_endpoint(self, mocker: MockerFixture) -> None:
        """The two Images routes are not interchangeable: /images/generations rejects input images."""
        worker = _make_worker(mocker)
        _patch_args_factory(mocker, args={"prompt": "edit it", "image": [("a.png", b"\x89PNG", "image/png")]})
        _images(worker).edit.return_value = _make_response(mocker, _AZURE_GPT_IMAGE_BODY)

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        _images(worker).edit.assert_awaited_once()
        _images(worker).generate.assert_not_awaited()

    async def test_several_input_images_travel_as_a_list_not_as_repeated_bare_parts(self, mocker: MockerFixture) -> None:
        """A server handed repeated bare `image` parts keeps one and drops the rest — silently.

        The SDK serializes a list under `image` as `image[]` parts and a single file as the bare
        field, so passing the list is what makes an edit of several images an edit of several
        images rather than a plausible edit of the first.
        """
        worker = _make_worker(mocker)
        files = [("a.png", b"\x89PNG", "image/png"), ("b.png", b"\x89PNG", "image/png")]
        _patch_args_factory(mocker, args={"prompt": "edit them", "image": files})
        _images(worker).edit.return_value = _make_response(mocker, _AZURE_GPT_IMAGE_BODY)

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=2)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert _images(worker).edit.call_args.kwargs["image"] == files


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldImgGenWorkerFailures:
    async def test_a_non_json_2xx_becomes_a_categorized_error(self, mocker: MockerFixture) -> None:
        """The arm with no symptom: a decode failure is not an `APIError` and catches nowhere else."""
        worker = _make_worker(mocker)
        _patch_args_factory(mocker)
        _images(worker).generate.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CONTACT_SUPPORT
        assert "gpt-image-1" in exc_info.value.message

    async def test_a_provider_status_error_is_classified_rather_than_raised_raw(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        _patch_args_factory(mocker)
        request = httpx.Request("POST", "https://manifold.example.com/v1/images/generations")
        response = httpx.Response(status_code=429, request=request, headers={"x-request-id": "mf-1"})
        _images(worker).generate.side_effect = portkey_exc.RateLimitError(
            message="http 429",
            request=request,
            response=response,
            body={},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT

    @pytest.mark.parametrize(
        ("body", "expected_kind"),
        _MALFORMED_BODIES,
        ids=["no-images", "image-without-data", "non-numeric-size", "no-size-at-all"],
    )
    async def test_a_malformed_success_body_is_wrapped_rather_than_escaping(
        self,
        mocker: MockerFixture,
        body: dict[str, Any],
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        _patch_args_factory(mocker)
        _images(worker).generate.return_value = _make_response(mocker, body)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
