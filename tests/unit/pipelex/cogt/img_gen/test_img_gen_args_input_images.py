"""Tests for ImgGenArgsFactory input-image and input-fidelity argument mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job_components import InputFidelity
from pipelex.cogt.img_gen.img_gen_model_rules import (
    ImgGenArgTopic,
    ImgGenModelRules,
    InputFidelityTaxonomy,
    InputImagesTaxonomy,
    NumImagesTaxonomy,
    PromptTaxonomy,
)
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.uri.prepared_file import PreparedFile, PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath
from tests.unit.pipelex.cogt.img_gen.conftest import make_img_gen_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PNG_FILE_TYPE = FileType(extension="png", mime="image/png")


def make_prepped_base64(base64_data: str) -> PreparedFileBase64:
    """Create a PreparedFileBase64 with PNG file type for testing."""
    return PreparedFileBase64(base64_data=base64_data, file_type=PNG_FILE_TYPE)


def make_input_images(nb_images: int) -> list[PromptImage]:
    """Create a list of URI prompt images for testing."""
    return cast("list[PromptImage]", [PromptImageUri(uri=f"https://example.com/image_{index_image}.png") for index_image in range(nb_images)])


class TestImgGenArgsInputImages:
    @pytest.mark.asyncio
    async def test_bfl_flux_2_mixes_base64_and_http_url_prepped_files(self, mocker: MockerFixture) -> None:
        """BFL Flux 2 numbers keys input_image, input_image_2, ... and accepts both data URLs and raw HTTP URLs."""
        input_images = make_input_images(3)
        prepped_files: list[PreparedFile] = [
            make_prepped_base64("Zmlyc3Q="),
            PreparedFileHttpUrl(url="https://example.com/hosted.png"),
            make_prepped_base64("dGhpcmQ="),
        ]
        prep_mock = mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=prepped_files,
        )

        result = await ImgGenArgsFactory.make_args_from_input_images(
            input_images_taxonomy=InputImagesTaxonomy.BFL_FLUX_2,
            input_images=input_images,
        )

        assert result == {
            "input_image": "data:image/png;base64,Zmlyc3Q=",
            "input_image_2": "https://example.com/hosted.png",
            "input_image_3": "data:image/png;base64,dGhpcmQ=",
        }
        prep_mock.assert_awaited_once_with(prompt_images=input_images, is_http_url_enabled=True)

    @pytest.mark.asyncio
    async def test_bfl_flux_2_caps_prepped_images_at_eight(self, mocker: MockerFixture) -> None:
        """BFL Flux 2 keeps at most eight prepped images, dropping any extras."""
        input_images = make_input_images(10)
        prepped_files: list[PreparedFile] = [PreparedFileHttpUrl(url=f"https://example.com/img_{index_file}.png") for index_file in range(10)]
        mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=prepped_files,
        )

        result = await ImgGenArgsFactory.make_args_from_input_images(
            input_images_taxonomy=InputImagesTaxonomy.BFL_FLUX_2,
            input_images=input_images,
        )

        expected_keys = ["input_image"] + [f"input_image_{index_key}" for index_key in range(2, 9)]
        assert sorted(result.keys()) == sorted(expected_keys)
        assert result["input_image"] == "https://example.com/img_0.png"
        assert result["input_image_8"] == "https://example.com/img_7.png"
        assert "input_image_9" not in result

    @pytest.mark.asyncio
    async def test_gpt_image_collects_base64_data_urls(self, mocker: MockerFixture) -> None:
        """GPT Image returns all prepped images as a list of base64 data URLs under the `image` key."""
        input_images = make_input_images(2)
        prepped_files: list[PreparedFile] = [
            make_prepped_base64("Zmlyc3Q="),
            make_prepped_base64("c2Vjb25k"),
        ]
        prep_mock = mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=prepped_files,
        )

        result = await ImgGenArgsFactory.make_args_from_input_images(
            input_images_taxonomy=InputImagesTaxonomy.GPT_IMAGE,
            input_images=input_images,
        )

        assert result == {
            "image": [
                "data:image/png;base64,Zmlyc3Q=",
                "data:image/png;base64,c2Vjb25k",
            ],
        }
        prep_mock.assert_awaited_once_with(prompt_images=input_images, is_http_url_enabled=False)

    @pytest.mark.asyncio
    async def test_gpt_image_rejects_http_url_prepped_files(self, mocker: MockerFixture) -> None:
        """GPT Image raises a parameter error when a prepped file is an HTTP URL instead of base64."""
        input_images = make_input_images(1)
        prepped_files: list[PreparedFile] = [PreparedFileHttpUrl(url="https://example.com/hosted.png")]
        mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=prepped_files,
        )

        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_from_input_images(
                input_images_taxonomy=InputImagesTaxonomy.GPT_IMAGE,
                input_images=input_images,
            )

        assert "requires base64 data URLs" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_none_taxonomy_with_images_raises(self) -> None:
        """The NONE taxonomy rejects any provided input images."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_from_input_images(
                input_images_taxonomy=InputImagesTaxonomy.NONE,
                input_images=make_input_images(1),
            )

        assert "does not support image inputs" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "input_images_taxonomy",
        [
            InputImagesTaxonomy.GPT_IMAGE,
            InputImagesTaxonomy.BFL_FLUX_2,
            InputImagesTaxonomy.NONE,
        ],
    )
    @pytest.mark.parametrize("input_images", [None, []])
    async def test_no_input_images_returns_empty_without_prepping(
        self,
        mocker: MockerFixture,
        input_images_taxonomy: InputImagesTaxonomy,
        input_images: list[PromptImage] | None,
    ) -> None:
        """None or empty input images yield an empty dict and never trigger image preparation."""
        prep_mock = mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
        )

        result = await ImgGenArgsFactory.make_args_from_input_images(
            input_images_taxonomy=input_images_taxonomy,
            input_images=input_images,
        )

        assert result == {}
        prep_mock.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("input_images_taxonomy", "expected_provider_name"),
        [
            (InputImagesTaxonomy.GPT_IMAGE, "GPT Image"),
            (InputImagesTaxonomy.BFL_FLUX_2, "Flux 2"),
        ],
    )
    async def test_unexpected_prepped_file_type_raises_naming_provider(
        self,
        mocker: MockerFixture,
        input_images_taxonomy: InputImagesTaxonomy,
        expected_provider_name: str,
    ) -> None:
        """A prepped file outside the expected shapes raises a parameter error naming the provider and the type."""
        prepped_files: list[PreparedFile] = [PreparedFileLocalPath(path="some_dir/local_image.png")]
        mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=prepped_files,
        )

        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_from_input_images(
                input_images_taxonomy=input_images_taxonomy,
                input_images=make_input_images(1),
            )

        error_message = str(exc_info.value)
        assert expected_provider_name in error_message
        assert "PreparedFileLocalPath" in error_message

    @pytest.mark.parametrize(
        ("input_fidelity", "expected_value"),
        [
            (InputFidelity.LOW, "low"),
            (InputFidelity.HIGH, "high"),
        ],
    )
    def test_input_fidelity_gpt_image_legacy_emits_value(self, input_fidelity: InputFidelity, expected_value: str) -> None:
        """Legacy GPT Image taxonomy maps input fidelity through the OpenAI factory to its string value."""
        result = ImgGenArgsFactory.make_args_from_input_fidelity(
            input_fidelity_taxonomy=InputFidelityTaxonomy.GPT_IMAGE_LEGACY,
            input_fidelity=input_fidelity,
            model_name="gpt-image-1",
        )

        assert result == {"input_fidelity": expected_value}

    @pytest.mark.parametrize(
        "input_fidelity_taxonomy",
        [
            InputFidelityTaxonomy.GPT_IMAGE_LEGACY,
            InputFidelityTaxonomy.UNAVAILABLE,
        ],
    )
    def test_input_fidelity_none_returns_empty_for_all_taxonomies(self, input_fidelity_taxonomy: InputFidelityTaxonomy) -> None:
        """A missing input fidelity yields an empty dict regardless of taxonomy, even UNAVAILABLE."""
        result = ImgGenArgsFactory.make_args_from_input_fidelity(
            input_fidelity_taxonomy=input_fidelity_taxonomy,
            input_fidelity=None,
            model_name="any-model",
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_input_fidelity_without_rule_raises_with_model_name(self) -> None:
        """A job carrying input_fidelity fails when the model rules omit the input_fidelity topic entirely."""
        model_rules: ImgGenModelRules = {
            ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY,
            ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.FAL,
        }
        img_gen_job = make_img_gen_job(input_fidelity=InputFidelity.HIGH)

        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_for_model(
                model_rules=model_rules,
                img_gen_job=img_gen_job,
                nb_images=1,
                model_id="fal-ai/flux/dev",
                model_name="flux-dev",
            )

        error_message = str(exc_info.value)
        assert "flux-dev" in error_message
        assert "does not support input_fidelity" in error_message
