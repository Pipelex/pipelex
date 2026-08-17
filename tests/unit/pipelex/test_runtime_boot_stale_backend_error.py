"""When the backend loader's retry declines, the error still says *old* rather than only *wrong*.

The fourth surface reaches a user through two paths, and until this test only one of them knew it
was a surface. `InferenceBackendLibrary.load` replays the ledger in memory and boots with a warning
when that works — but when it does not, the refusal travels as `InferenceBackendLibraryValidationError`
and `RuntimeBoot` turns it into a message of its own instead of going through the shared
`raise_config_setup_error`. That message named no surface, so the scan never ran, and a machine whose
backend file was *both* stale and carrying something we cannot explain was told only about the second
half — while the very same staleness on `pipelex.toml` produced the migration block.

The two halves under test:

- **A surface's failure carries its migration block.** The contract's rule is that every configuration
  surface's loader reports through `report_validation_error`; this is the fourth surface honouring it.
- **And then nothing offers to start over.** The tail that sends a user to `pipelex init config` — a
  command described in the same breath as resetting files to their defaults — must not be printed
  beside a block that just promised `pipelex migrate` keeps their values. The model deck, which has no
  ledger and gets no block, keeps that tail exactly as it was.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from pipelex.cogt.exceptions import InferenceBackendLibraryValidationError
from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.runtime_boot import BootComponent, RuntimeBoot
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, CONFIG_DIR_NAME, INFERENCE_DIR_NAME

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RETIRED_KEY = "prompting_target"
REGENERATE_TAIL = "pipelex init config"


def _refusal(*, extra_key: str) -> InferenceBackendLibraryValidationError:
    """The refusal the loader raises, with the pydantic error the boot message reads off `__cause__`."""
    try:
        InferenceModelSpecBlueprint.model_validate({"sdk": "openai_responses", extra_key: "openai"})
    except ValidationError as validation_error:
        refusal = InferenceBackendLibraryValidationError("model spec refused")
        refusal.__cause__ = validation_error
        return refusal
    msg = f"'{extra_key}' was accepted by the blueprint — this fixture is testing nothing."
    raise AssertionError(msg)


class TestAStaleBackendFileTheLedgerCannotFullyExplain:
    @pytest.fixture
    def machine(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        """A global configuration directory holding the kit's backend files, one of them left behind.

        The home is faked so that the scan walks this directory rather than the developer's own — it
        is `config_manager.existing_config_dirs` on both ends, the one derivation.
        """
        fake_home = tmp_path / "home"
        inference_dir = fake_home / CONFIG_DIR_NAME / INFERENCE_DIR_NAME
        inference_dir.mkdir(parents=True)
        shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME, inference_dir / BACKENDS_DIR_NAME)

        stale_file = inference_dir / BACKENDS_DIR_NAME / "openai.toml"
        text = stale_file.read_text(encoding="utf-8")
        anchor = "[defaults]\n"
        if anchor not in text:
            msg = "'openai.toml' no longer has a [defaults] block to plant into — the fixture is testing nothing."
            raise AssertionError(msg)
        stale_file.write_text(text.replace(anchor, f'{anchor}{RETIRED_KEY} = "openai"\n', 1), encoding="utf-8")

        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        return stale_file

    def test_the_message_names_the_stale_file_and_the_migration_that_explains_it(self, machine: Path) -> None:
        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=_refusal(extra_key="foo"),
        )

        assert "'foo'" in message, "the user's own key is still what the error is about"
        assert str(machine) in message
        assert "Drop prompting_target from every backend definition" in message
        assert "pipelex migrate" in message

    def test_it_stops_offering_to_start_over_once_it_has_offered_to_migrate(self, machine: Path) -> None:
        """Two remedies, one of which discards the file, is worse advice than either alone."""
        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=_refusal(extra_key="foo"),
        )

        assert str(machine) in message, "the tail is dropped because a block was found, not because none was looked for"
        assert REGENERATE_TAIL not in message

    def test_a_component_with_no_ledger_is_unchanged(self, machine: Path) -> None:
        """The model deck shares this message and is not a surface: no scan, no block, same tail as before."""
        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.MODEL_DECK,
            validation_exc=_refusal(extra_key="foo"),
        )

        assert REGENERATE_TAIL in message
        assert "pipelex migrate" not in message
        assert str(machine) not in message

    def test_a_backend_file_with_nothing_stale_about_it_keeps_the_plain_message(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """No scan result, no block — naming the surface must not invent one."""
        fake_home = tmp_path / "home"
        (fake_home / CONFIG_DIR_NAME).mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=_refusal(extra_key="foo"),
        )

        assert "'foo'" in message
        assert "pipelex migrate" not in message
        assert REGENERATE_TAIL in message
