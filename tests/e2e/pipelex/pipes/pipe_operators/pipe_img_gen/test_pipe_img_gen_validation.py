"""End-to-end validation tests for PipeImgGen — drives validation through `validate_bundle`.

Each test feeds a small synthetic `.mthds` bundle string into `validate_bundle`
and asserts that the bundle validator raises (or doesn't) based on whether the
PipeImgGen blueprint's parameter values are accepted by the model's rules.

Mirrors the pattern used by the PipeFunc validation e2e tests.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from pytest import MonkeyPatch

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.hub import get_console, get_model_deck
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path


@pytest.fixture(scope="class")
def pipelex_routed_to_openai_for_e2e() -> Iterator[None]:
    """Reload Pipelex with routing forced to the openai backend so img-gen rules
    use the current taxonomy (legacy gpt-image-1 = GPT_IMAGE_LEGACY etc.).
    """
    Pipelex.teardown_if_needed()

    routing_profile_name = "all_openai"
    routing_monkeypatch = MonkeyPatch()
    routing_profiles_path = Path(config_manager.routing_profiles_file_path)
    routing_profiles_doc = load_toml_with_tomlkit(str(routing_profiles_path))
    routing_profiles_doc["active"] = routing_profile_name
    routing_override_dir = Path(tempfile.mkdtemp(prefix="pipelex-routing-pipe-img-gen-e2e-validation-"))
    routing_override_path = routing_override_dir / routing_profiles_path.name
    save_toml_to_path(routing_profiles_doc, str(routing_override_path))
    routing_monkeypatch.setattr(
        type(config_manager),
        "routing_profiles_file_path",
        property(lambda _self: str(routing_override_path)),
    )
    get_console().print("[cyan]Routing to backend:[/cyan] openai (for e2e validation test)")

    try:
        integration_mode = IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST
        Pipelex.make(integration_mode=integration_mode)
    except Exception:
        routing_monkeypatch.undo()
        shutil.rmtree(routing_override_dir, ignore_errors=True)
        raise

    yield

    Pipelex.teardown_if_needed()
    routing_monkeypatch.undo()
    shutil.rmtree(routing_override_dir, ignore_errors=True)


_BAD_BUNDLE_LEGACY_LANDSCAPE_4_3 = """\
domain      = "img_gen_validation_e2e"
description = "E2E test: legacy model + landscape_4_3 must fail validation"

[pipe.bad_landscape_4_3]
type         = "PipeImgGen"
description  = "Should fail: gpt-image-1 doesn't accept landscape_4_3"
output       = "Image"
prompt       = "A test prompt"
model        = "gpt-image-1"
aspect_ratio = "landscape_4_3"
"""

_BAD_BUNDLE_GPT_IMAGE_2_TRANSPARENT = """\
domain      = "img_gen_validation_e2e"
description = "E2E test: gpt-image-2 + transparent background must fail validation"

[pipe.bad_gpt_image_2_transparent]
type         = "PipeImgGen"
description  = "Should fail: gpt-image-2 doesn't accept transparent background"
output       = "Image"
prompt       = "A test prompt"
model        = "gpt-image-2"
background   = "transparent"
"""

_GOOD_BUNDLE_LEGACY_SQUARE = """\
domain      = "img_gen_validation_e2e"
description = "E2E test: legacy model + square must succeed"

[pipe.good_legacy_square]
type         = "PipeImgGen"
description  = "Should succeed: gpt-image-1 accepts square"
output       = "Image"
prompt       = "A test prompt"
model        = "gpt-image-1"
aspect_ratio = "square"
"""


@pytest.mark.usefixtures("pipelex_routed_to_openai_for_e2e")
@pytest.mark.asyncio(loop_scope="class")
class TestPipeImgGenE2EValidation:
    """E2E: bad PipeImgGen blueprints must surface as ValidateBundleError at bundle-load time."""

    async def test_validate_bundle_rejects_legacy_with_landscape_4_3(self) -> None:
        if get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN) is None:
            pytest.skip("gpt-image-1 not available in current deck routing")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_BAD_BUNDLE_LEGACY_LANDSCAPE_4_3])

        msg = str(exc_info.value)
        assert "gpt-image-1" in msg
        assert "landscape_4_3" in msg.lower()

    async def test_validate_bundle_rejects_gpt_image_2_with_transparent(self) -> None:
        if get_model_deck().get_optional_inference_model(model_handle="gpt-image-2", model_type=ModelType.IMG_GEN) is None:
            pytest.skip("gpt-image-2 not available in current deck routing")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_BAD_BUNDLE_GPT_IMAGE_2_TRANSPARENT])

        msg = str(exc_info.value).lower()
        assert "gpt-image-2" in msg
        assert "transparent" in msg

    async def test_validate_bundle_accepts_legacy_with_square(self) -> None:
        if get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN) is None:
            pytest.skip("gpt-image-1 not available in current deck routing")

        result = await validate_bundle(mthds_contents=[_GOOD_BUNDLE_LEGACY_SQUARE])

        assert len(result.pipes) == 1
        assert result.pipes[0].code == "good_legacy_square"
