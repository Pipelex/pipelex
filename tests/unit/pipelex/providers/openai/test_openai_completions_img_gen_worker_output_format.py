"""The completions image worker's fixed output format comes from whoever registers it, never from a backend name.

Some services normalise every image to one format and may answer with a URL, from which no format can
be read. The registration for such a service passes that format to the worker; the worker refuses a
request for another one before the call, and reads a URL answer as that format. A worker built without
one cannot interpret a URL answer, and says so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.blackboxai.blackboxai_plugin import BlackboxaiPlugin
from pipelex.providers.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker
from pipelex.providers.openrouter.openrouter_plugin import OpenRouterPlugin
from pipelex.providers.pipelex_hosted.pipelex_hosted_plugin import PipelexHostedPlugin
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_IMAGE_URL = "https://images.example.com/generated/abc"


def _make_worker(mocker: MockerFixture, *, fixed_output_format: ImageFormat | None) -> OpenAICompletionsImgGenWorker:
    worker = object.__new__(OpenAICompletionsImgGenWorker)
    worker.fixed_output_format = fixed_output_format
    model = mocker.MagicMock()
    model.desc = "test-completions-img"
    model.model_id = "test-image-model"
    model.name = "test-image-model"
    model.backend_name = "any_backend_name"
    model.tag = "test-tag"
    worker.inference_model = model
    client = mocker.MagicMock()
    message = mocker.MagicMock(spec=["content"])
    message.content = _IMAGE_URL
    response = mocker.MagicMock()
    response.choices = [mocker.MagicMock(message=message)]
    response.usage = None
    client.chat.completions.create = mocker.AsyncMock(return_value=response)
    worker.openai_client = client
    factory = mocker.MagicMock()
    factory.make_extras.return_value = ({}, {})
    worker.openai_completions_factory = factory
    return worker


def _make_job(mocker: MockerFixture, *, output_format: ImageFormat | None) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a lighthouse at dusk"
    job.img_gen_prompt.input_images = None
    job.job_params.output_format = output_format
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestFixedOutputFormat:
    @pytest.mark.parametrize("fixed_output_format", [ImageFormat.PNG, ImageFormat.JPEG])
    async def test_a_url_answer_is_read_as_the_fixed_format(self, mocker: MockerFixture, fixed_output_format: ImageFormat) -> None:
        worker = _make_worker(mocker, fixed_output_format=fixed_output_format)

        details = await worker._gen_image(img_gen_job=_make_job(mocker, output_format=None))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert details.actual_url == _IMAGE_URL
        assert details.image_format == fixed_output_format

    async def test_a_request_for_the_fixed_format_is_served(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker, fixed_output_format=ImageFormat.JPEG)

        details = await worker._gen_image(img_gen_job=_make_job(mocker, output_format=ImageFormat.JPEG))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert details.image_format == ImageFormat.JPEG

    @pytest.mark.parametrize(
        ("fixed_output_format", "requested"),
        [(ImageFormat.PNG, ImageFormat.JPEG), (ImageFormat.PNG, ImageFormat.WEBP), (ImageFormat.JPEG, ImageFormat.PNG)],
    )
    async def test_another_format_is_refused_before_the_call(
        self, mocker: MockerFixture, fixed_output_format: ImageFormat, requested: ImageFormat
    ) -> None:
        worker = _make_worker(mocker, fixed_output_format=fixed_output_format)

        with pytest.raises(ImgGenParameterError, match=f"only supports {fixed_output_format} output format"):
            await worker._gen_image(img_gen_job=_make_job(mocker, output_format=requested))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        worker.openai_client.chat.completions.create.assert_not_called()  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    async def test_without_a_fixed_format_a_url_answer_is_refused(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker, fixed_output_format=None)

        with pytest.raises(ImgGenParameterError, match="no fixed output format"):
            await worker._gen_image(img_gen_job=_make_job(mocker, output_format=None))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    async def test_without_a_fixed_format_any_format_may_be_requested(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker, fixed_output_format=None)
        worker.openai_client.chat.completions.create.side_effect = RuntimeError("called")  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(RuntimeError, match="called"):
            await worker._gen_image(img_gen_job=_make_job(mocker, output_format=ImageFormat.WEBP))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


class TestEachRegistrationPassesItsFormat:
    @pytest.mark.parametrize(
        ("plugin", "sdk", "expected"),
        [
            (PipelexHostedPlugin(), "manifold_completions", ImageFormat.PNG),
            (BlackboxaiPlugin(), "blackboxai_img_gen", ImageFormat.JPEG),
            (OpenRouterPlugin(), "openrouter_img_gen", None),
        ],
        ids=["manifold", "blackboxai", "openrouter"],
    )
    def test_the_registration_builds_the_worker_with_its_format(
        self, mocker: MockerFixture, plugin: Any, sdk: str, expected: ImageFormat | None
    ) -> None:
        registrar = PluginRegistrar(config=mocker.MagicMock())
        plugin.register(registrar)
        make_worker = registrar.inference_backends[InferenceFamily.IMG_GEN, sdk]
        worker_class = mocker.patch("pipelex.providers.openai.openai_completions_img_gen_worker.OpenAICompletionsImgGenWorker")
        mocker.patch.object(ModelHandle, "make_for_inference_model", return_value=mocker.MagicMock())
        sdk_clients = mocker.MagicMock()

        make_worker(inference_model=mocker.MagicMock(), backend=mocker.MagicMock(), sdk_clients=sdk_clients, reporting_delegate=None)

        assert worker_class.call_args.kwargs.get("fixed_output_format") == expected
