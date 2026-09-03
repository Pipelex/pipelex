"""`pipelex init` decides "managed gateway enabled" on the merged backends document, and says so when a write to the base cannot take.

The init writers edit the base `backends.toml` while the runtime reads it with `backends_override.toml`
merged over it. Two consequences are pinned here: the terms prompt fires for a managed gateway backend
enabled only by an override, and declining the terms — which disables every managed backend in the base —
warns when an override still pins one on, naming the files, instead of leaving the next boot to refuse for
terms the user just declined.

The question asked is the broad one, over every Pipelex-managed gateway backend rather than
`pipelex_gateway` by name, because the terms are the Pipelex service's: a manifold pinned back on by an
override puts the installation behind them exactly as the legacy gateway does.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from pipelex.cli.commands.init.backends import warn_if_managed_gateway_pinned_by_override
from pipelex.cli.commands.init.command import _check_gateway_terms_if_needed  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.model_backends.backend import MANIFOLD_MODEL_SPECS_SECTION

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

BASE_GATEWAY_OFF = "[pipelex_gateway]\nenabled = false\n"
OVERRIDE_GATEWAY_ON = "[pipelex_gateway]\nenabled = true\n"
BASE_MANIFOLD_OFF = f'[pipelex_manifold]\nenabled = false\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\n'
OVERRIDE_MANIFOLD_ON = "[pipelex_manifold]\nenabled = true\n"


def _write_backends(config_dir: Path, *, base: str, override: str | None) -> Path:
    inference_dir = config_dir / "inference"
    inference_dir.mkdir(parents=True)
    backends_toml_path = inference_dir / "backends.toml"
    backends_toml_path.write_text(base)
    if override is not None:
        (inference_dir / "backends_override.toml").write_text(override)
    return backends_toml_path


def _capturing_console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=False, width=200), buffer


class TestWarnIfManagedGatewayPinnedByOverride:
    def test_says_nothing_when_the_base_is_the_whole_story(self, tmp_path: Path) -> None:
        backends_toml_path = _write_backends(tmp_path, base=BASE_GATEWAY_OFF, override=None)
        console, buffer = _capturing_console()

        assert warn_if_managed_gateway_pinned_by_override(console=console, backends_toml_path=backends_toml_path) is False
        assert buffer.getvalue() == ""

    def test_names_the_override_that_still_enables_the_gateway(self, tmp_path: Path) -> None:
        backends_toml_path = _write_backends(tmp_path, base=BASE_GATEWAY_OFF, override=OVERRIDE_GATEWAY_ON)
        console, buffer = _capturing_console()

        assert warn_if_managed_gateway_pinned_by_override(console=console, backends_toml_path=backends_toml_path) is True
        assert "backends_override.toml" in buffer.getvalue()
        assert "still enabled" in buffer.getvalue()
        assert "pipelex_gateway" in buffer.getvalue()

    def test_it_asks_the_broad_question_so_a_manifold_pinned_on_is_named_too(self, tmp_path: Path) -> None:
        """The terms are the service's, not one dialect's — a manifold override puts the install behind them."""
        backends_toml_path = _write_backends(tmp_path, base=BASE_MANIFOLD_OFF, override=OVERRIDE_MANIFOLD_ON)
        console, buffer = _capturing_console()

        assert warn_if_managed_gateway_pinned_by_override(console=console, backends_toml_path=backends_toml_path) is True
        assert "pipelex_manifold" in buffer.getvalue()


class TestCheckGatewayTermsIfNeeded:
    def test_a_gateway_enabled_only_by_an_override_is_prompted_for_terms_and_warned_on_decline(self, tmp_path: Path, mocker: MockerFixture) -> None:
        backends_toml_path = _write_backends(tmp_path, base=BASE_GATEWAY_OFF, override=OVERRIDE_GATEWAY_ON)
        console, buffer = _capturing_console()
        mocker.patch("pipelex.cli.commands.init.command.load_pipelex_service_config_if_exists", return_value=None)
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_gateway_acceptance", return_value=False)
        mocker.patch("pipelex.cli.commands.init.command.display_gateway_declined_message")
        record_terms = mocker.patch("pipelex.cli.commands.init.command.update_service_terms_acceptance")
        mocker.patch.object(Path, "home", return_value=tmp_path / "home")

        _check_gateway_terms_if_needed(console=console, backends_toml_path=backends_toml_path)

        prompt.assert_called_once()
        record_terms.assert_called_once()
        assert record_terms.call_args.kwargs["accepted"] is False
        assert "backends_override.toml" in buffer.getvalue()

    def test_a_gateway_disabled_in_the_merged_document_is_not_prompted(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The reverse: enabled in the base, switched off by the override — no terms needed."""
        backends_toml_path = _write_backends(tmp_path, base=OVERRIDE_GATEWAY_ON, override=BASE_GATEWAY_OFF)
        console, _ = _capturing_console()
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_gateway_acceptance")

        _check_gateway_terms_if_needed(console=console, backends_toml_path=backends_toml_path)

        prompt.assert_not_called()
