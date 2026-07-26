"""Integration tests for PipeImgGen.validate_inputs_static parameter-support check.

Verifies that constructing a PipeImgGen with a model handle and an
explicit parameter value the model's rules don't accept raises a
PipeValidationError at static-validation time (i.e. as soon as the
blueprint is converted to a pipe — before any inference runs).

These tests use a routing-override fixture to ensure model handles
resolve to backends with up-to-date rules (the openai backend), not to
backends whose rules predate the current taxonomy enums.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterator

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background
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
def pipelex_routed_to_openai() -> Iterator[None]:
    """Reload Pipelex with routing forced to the openai backend so img-gen rules
    come from the openai TOML (current taxonomies) rather than the gateway one.
    """
    Pipelex.teardown_if_needed()

    routing_profile_name = "all_openai"
    routing_monkeypatch = MonkeyPatch()
    routing_profiles_path = Path(config_manager.routing_profiles_file_path)
    routing_profiles_doc = load_toml_with_tomlkit(str(routing_profiles_path))
    routing_profiles_doc["active"] = routing_profile_name
    routing_override_dir = Path(tempfile.mkdtemp(prefix="pipelex-routing-pipe-img-gen-validation-"))
    routing_override_path = routing_override_dir / routing_profiles_path.name
    save_toml_to_path(routing_profiles_doc, path=str(routing_override_path))
    routing_monkeypatch.setattr(
        type(config_manager),
        "routing_profiles_file_path",
        property(lambda _self: str(routing_override_path)),
    )
    get_console().print("[cyan]Routing to backend:[/cyan] openai (for blueprint-validation test)")

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


@pytest.mark.usefixtures("pipelex_routed_to_openai")
class TestPipeImgGenBlueprintValidation:
    """End-to-blueprint-load validation of PipeImgGen parameters against model rules."""

    def test_legacy_model_with_unsupported_aspect_ratio_raises(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """gpt-image-1 doesn't support landscape_4_3 — building the pipe must raise PipeValidationError."""
        load_empty_library()
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("gpt-image-1 not available in current deck routing")

        blueprint = PipeImgGenBlueprint(
            description="Bad config: legacy model + landscape_4_3",
            model="gpt-image-1",
            output=NativeConceptCode.IMAGE,
            prompt="A test prompt",
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
        )

        with pytest.raises((PipeValidationError, ValidationError)) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="test_domain",
                pipe_code="bad_pipe_landscape_4_3",
                blueprint=blueprint,
            )

        msg = str(exc_info.value)
        assert "gpt-image-1" in msg
        assert "landscape_4_3" in msg.lower()

    def test_legacy_model_with_supported_aspect_ratio_succeeds(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Same model with a supported aspect ratio (square) must build cleanly."""
        load_empty_library()
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("gpt-image-1 not available in current deck routing")

        blueprint = PipeImgGenBlueprint(
            description="Good config: legacy model + square",
            model="gpt-image-1",
            output=NativeConceptCode.IMAGE,
            prompt="A test prompt",
            aspect_ratio=AspectRatio.SQUARE,
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="good_pipe_square",
            blueprint=blueprint,
        )
        assert isinstance(pipe, PipeImgGen)

    def test_gpt_image_2_with_transparent_background_raises(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """gpt-image-2 has BackgroundTaxonomy.UNAVAILABLE — transparent must be rejected."""
        load_empty_library()
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-2", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("gpt-image-2 not available in current deck routing")

        blueprint = PipeImgGenBlueprint(
            description="Bad config: gpt-image-2 + transparent",
            model="gpt-image-2",
            output=NativeConceptCode.IMAGE,
            prompt="A test prompt",
            background=Background.TRANSPARENT,
        )

        with pytest.raises((PipeValidationError, ValidationError)) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="test_domain",
                pipe_code="bad_pipe_gpt_image_2_transparent",
                blueprint=blueprint,
            )

        msg = str(exc_info.value).lower()
        assert "gpt-image-2" in msg
        assert "transparent" in msg

    def test_blueprint_with_no_explicit_params_does_not_raise(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """If the blueprint defers all params to deck defaults, no early validation should fire."""
        load_empty_library()
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("gpt-image-1 not available in current deck routing")

        blueprint = PipeImgGenBlueprint(
            description="Defers all params to deck defaults",
            model="gpt-image-1",
            output=NativeConceptCode.IMAGE,
            prompt="A test prompt",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="defaults_pipe",
            blueprint=blueprint,
        )
        assert isinstance(pipe, PipeImgGen)

    def test_blueprint_without_model_choice_does_not_raise(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """If the blueprint has no `model` choice, validation is skipped (deck default applies later)."""
        load_empty_library()
        blueprint = PipeImgGenBlueprint(
            description="No model choice — uses deck default",
            output=NativeConceptCode.IMAGE,
            prompt="A test prompt",
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,  # would be unsupported on legacy, but no model is bound here
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="no_model_pipe",
            blueprint=blueprint,
        )
        assert isinstance(pipe, PipeImgGen)
