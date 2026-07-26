"""Integration tests for PipeImgGen.validate_inputs_static against Google image model rules.

Google image models historically had no `rules` block in the deck, so
`_validate_param_support_against_model_rules` silently skipped them and an
unsupported aspect ratio or size only failed at runtime. These tests verify the
gap is closed: with the Gemini taxonomies in `google.toml`, bad (aspect_ratio,
size) combinations raise a PipeValidationError at blueprint-load time.

Uses a routing-override fixture (mirroring the openai variant in
test_pipe_img_gen_blueprint_validation.py) to force model handles to resolve to
the google backend TOML, whose rules carry the current taxonomies.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterator

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import get_console, get_model_deck
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path


@pytest.fixture(scope="class")
def pipelex_routed_to_google() -> Iterator[None]:
    """Reload Pipelex with routing forced to the google backend so img-gen rules
    come from the google TOML (Gemini taxonomies) rather than the gateway one.
    """
    Pipelex.teardown_if_needed()

    routing_profile_name = "all_google"
    routing_monkeypatch = MonkeyPatch()
    routing_profiles_path = Path(config_manager.routing_profiles_file_path)
    routing_profiles_doc = load_toml_with_tomlkit(str(routing_profiles_path))
    routing_profiles_doc["active"] = routing_profile_name
    routing_override_dir = Path(tempfile.mkdtemp(prefix="pipelex-routing-pipe-img-gen-google-validation-"))
    routing_override_path = routing_override_dir / routing_profiles_path.name
    save_toml_to_path(routing_profiles_doc, path=str(routing_override_path))
    routing_monkeypatch.setattr(
        type(config_manager),
        "routing_profiles_file_path",
        property(lambda _self: str(routing_override_path)),
    )
    get_console().print("[cyan]Routing to backend:[/cyan] google (for blueprint-validation test)")

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


def _require_google_rules(model_handle: str) -> None:
    spec = get_model_deck().get_optional_inference_model(model_handle=model_handle, model_type=ModelType.IMG_GEN)
    if spec is None or spec.rules is None:
        pytest.skip(f"{model_handle} not available with rules in current deck routing")


@pytest.mark.usefixtures("pipelex_routed_to_google")
class TestPipeImgGenGoogleBlueprintValidation:
    """Static validation of PipeImgGen (aspect_ratio, size) against Google deck rules."""

    def test_gemini_2_5_with_banner_ratio_raises(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """nano-banana (Gemini 2.5) publishes no banner ratios — must fail at blueprint load."""
        load_empty_library()
        _require_google_rules("nano-banana")

        blueprint = PipeImgGenBlueprint(
            description="Bad config: nano-banana + banner ratio",
            model="nano-banana",
            output=NativeConceptCode.IMAGE,
            prompt="A test prompt",
            aspect_ratio=AspectRatio.LANDSCAPE_4_1,
        )

        with pytest.raises((PipeValidationError, ValidationError)) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="test_domain",
                pipe_code="bad_pipe_banner_on_gemini_2_5",
                blueprint=blueprint,
            )

        msg = str(exc_info.value)
        assert "nano-banana" in msg
        assert "landscape_4_1" in msg.lower()

    def test_gemini_2_5_with_2k_tier_raises(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """nano-banana is 1K-only — a '2k' tier must fail at blueprint load."""
        load_empty_library()
        _require_google_rules("nano-banana")

        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "Bad config: nano-banana + 2k",
                "model": "nano-banana",
                "output": NativeConceptCode.IMAGE,
                "prompt": "A test prompt",
                "size": "2k",
            }
        )

        with pytest.raises((PipeValidationError, ValidationError)) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="test_domain",
                pipe_code="bad_pipe_2k_on_gemini_2_5",
                blueprint=blueprint,
            )

        msg = str(exc_info.value)
        assert "nano-banana" in msg

    def test_gemini_3_flash_with_16_9_at_2k_builds(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Worked example: nano-banana-2 + landscape_16_9 + '2k' is valid and builds cleanly."""
        load_empty_library()
        _require_google_rules("nano-banana-2")

        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "Good config: nano-banana-2 + 16:9 @ 2k",
                "model": "nano-banana-2",
                "output": NativeConceptCode.IMAGE,
                "prompt": "A test prompt",
                "aspect_ratio": "landscape_16_9",
                "size": "2k",
            }
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="good_pipe_16_9_2k",
            blueprint=blueprint,
        )
        assert isinstance(pipe, PipeImgGen)

    def test_gemini_3_flash_with_exact_grid_hit_builds(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Worked example: '2048x2048' exactly matches a Gemini 3 grid cell (1:1 @ 2K)."""
        load_empty_library()
        _require_google_rules("nano-banana-2")

        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "Good config: nano-banana-2 + exact grid hit",
                "model": "nano-banana-2",
                "output": NativeConceptCode.IMAGE,
                "prompt": "A test prompt",
                "size": "2048x2048",
            }
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="good_pipe_exact_grid_hit",
            blueprint=blueprint,
        )
        assert isinstance(pipe, PipeImgGen)

    def test_gemini_3_flash_with_exact_grid_miss_raises_with_suggestion(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Worked example: '2000x2000' misses the grid and the error names the nearest cell."""
        load_empty_library()
        _require_google_rules("nano-banana-2")

        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "Bad config: nano-banana-2 + exact grid miss",
                "model": "nano-banana-2",
                "output": NativeConceptCode.IMAGE,
                "prompt": "A test prompt",
                "size": "2000x2000",
            }
        )

        with pytest.raises((PipeValidationError, ValidationError)) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="test_domain",
                pipe_code="bad_pipe_exact_grid_miss",
                blueprint=blueprint,
            )

        msg = str(exc_info.value)
        assert "2048x2048" in msg

    def test_gemini_3_flash_lite_with_4k_tier_raises(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """nano-banana-2-lite is 1K-only — a '4k' tier must fail at blueprint load."""
        load_empty_library()
        _require_google_rules("nano-banana-2-lite")

        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "Bad config: nano-banana-2-lite + 4k",
                "model": "nano-banana-2-lite",
                "output": NativeConceptCode.IMAGE,
                "prompt": "A test prompt",
                "size": "4k",
            }
        )

        with pytest.raises((PipeValidationError, ValidationError)) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="test_domain",
                pipe_code="bad_pipe_4k_on_lite",
                blueprint=blueprint,
            )

        msg = str(exc_info.value)
        assert "nano-banana-2-lite" in msg
