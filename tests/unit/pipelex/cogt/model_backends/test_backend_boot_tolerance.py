"""A stale backend directory boots with a warning instead of stopping the world.

This is the fourth loader to join boot tolerance, and it is the one the tolerance was built for:
`#1104` deleted `prompting_target` from the model-spec blueprint, `pipelex init` never overwrites an
existing file, so the key survives in `inference/backends/*.toml` on every machine that was set up
before the change — where it is fatal twice over. In `[defaults]` it is copied wholesale into every
model of the file and fails all of them with `extra_forbidden`; on one model it is rejected by name
as `NOT_HEADER_SHAPED`, which has been fatal in lenient mode too since the rogue-headers guard.

The two standing properties are the same as for the other three surfaces, and most of what follows
holds one of them:

- **Only what the ledger explains is tolerated.** A key the user chose to have still stops the boot,
  in both lenient modes, with exactly the error it produced before. Tolerance widens what starts, it
  never widens what is accepted.
- **Boot never writes.** Only `pipelex migrate` does, which is why the warning keeps coming back
  until it is run.

The stale documents here are made by planting the key back into a copy of **the kit's own backend
directory** — the files `pipelex init` puts on a machine — rather than by copying anything from this
laptop, and the planting raises if it matches nothing, so a kit file that stops carrying the anchor
turns these tests red instead of quietly testing an unplanted document.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryError, InferenceBackendLibraryValidationError
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import (
    BACKENDS_DIR_NAME,
    BACKENDS_FILE_NAME,
    CONFIG_DIR_NAME,
    INFERENCE_DIR_NAME,
    ROUTING_PROFILES_FILE_NAME,
)
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# Two backends, both with a literal key: what is under test is the *shape* of the per-backend files,
# and a `${VAR}` here would make every case below depend on the machine's environment instead.
BACKENDS_TOML = """
[openai]
enabled = true
api_key = "sk-not-a-real-key"

[portkey]
enabled = true
api_key = "sk-not-a-real-key-either"
"""

# The previous release's kit copies of `backends.toml` and `routing_profiles.toml`, as `pipelex init` left
# them on every machine set up with it, plus the per-backend file that kit shipped for an enabled backend
# the current kit no longer carries: a missing per-backend file is fatal for an enabled backend.
PREVIOUS_RELEASE_KIT_DIR = Path("tests/data/inference/previous_release_kit")

# The disabled table in the previous kit, a backend the current kit no longer carries, under a neutral
# name: its variables are never set here, so a load that substituted them before checking `enabled`
# would fail the strict case, and its keys the blueprint does not define must not be validated either.
PREVIOUS_RELEASE_DISABLED_BACKEND = "retired_preview"
PREVIOUS_RELEASE_DISABLED_BACKEND_VARS = ("RETIRED_PREVIEW_ENDPOINT", "RETIRED_PREVIEW_API_KEY")

# The enabled table in the previous kit whose per-backend file declares no model, and the line enabling it.
PREVIOUS_RELEASE_EMPTY_ENABLED_BACKEND = "pipelex_gateway"
PREVIOUS_RELEASE_GATEWAY_ENABLED_LINE = "enabled = true                         # Enable after accepting terms via `pipelex init config`"

# The key `#1104` deleted, and the two shapes it survives in. The value is immaterial to every
# assertion below — what matters is that the blueprint no longer has anywhere to put it.
RETIRED_KEY = "prompting_target"


def kit_backends_dir() -> Path:
    return Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME


def plant_in_defaults(*, path: Path) -> None:
    """Put the retired key back into a file's `[defaults]` block, where it breaks every model in it."""
    text = path.read_text(encoding="utf-8")
    anchor = "[defaults]\n"
    if anchor not in text:
        msg = f"'{path.name}' no longer has a [defaults] block to plant into — the fixture is testing nothing."
        raise AssertionError(msg)
    path.write_text(text.replace(anchor, f'{anchor}{RETIRED_KEY} = "openai"\n', 1), encoding="utf-8")


def plant_on_model(*, path: Path, table_header: str, key: str = RETIRED_KEY, value: str = '"gemini"') -> None:
    """Put a key back on one model table, exactly as a pre-`#1104` file carried it."""
    text = path.read_text(encoding="utf-8")
    anchor = f"{table_header}\n"
    if anchor not in text:
        msg = f"'{path.name}' no longer has a {table_header} table to plant into — the fixture is testing nothing."
        raise AssertionError(msg)
    path.write_text(text.replace(anchor, f"{anchor}{key} = {value}\n", 1), encoding="utf-8")


@pytest.fixture
def machine(tmp_path: Path, mocker: MockerFixture) -> Path:
    """A machine whose global configuration directory holds a fresh copy of the kit's backend files.

    The home directory is faked so that `config_manager.existing_config_dirs` — the one derivation of
    the walk, and what decides whether the warning may name `pipelex migrate` — answers with this
    directory rather than the developer's own.
    """
    fake_home = tmp_path / "home"
    global_dir = fake_home / CONFIG_DIR_NAME
    inference_dir = global_dir / INFERENCE_DIR_NAME
    inference_dir.mkdir(parents=True)
    shutil.copytree(kit_backends_dir(), inference_dir / BACKENDS_DIR_NAME)

    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)

    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)

    return global_dir


class TestAStaleBackendDirectory:
    def _backends_dir(self, machine: Path) -> Path:
        return machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME

    def _write_library(self, machine: Path, *, body: str = BACKENDS_TOML) -> Path:
        library_path = machine / INFERENCE_DIR_NAME / "backends.toml"
        library_path.write_text(body, encoding="utf-8")
        return library_path

    def _make_stale(self, machine: Path) -> tuple[Path, Path]:
        """`prompting_target` back where an upgrade leaves it: in one file's defaults, on another's models."""
        backends_dir = self._backends_dir(machine)
        openai_file = backends_dir / "openai.toml"
        portkey_file = backends_dir / "portkey.toml"
        plant_in_defaults(path=openai_file)
        plant_on_model(path=portkey_file, table_header="[gpt-4o]")
        plant_on_model(path=portkey_file, table_header='["gemini-2.5-pro"]')
        return openai_file, portkey_file

    def _load(self, machine: Path, *, lenient: bool) -> InferenceBackendLibrary:
        library_path = self._write_library(machine)
        library = InferenceBackendLibrary.make_empty()
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=[library_path],
            backends_dir_path=str(self._backends_dir(machine)),
            lenient=lenient,
        )
        return library

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_healthy_directory_loads_and_says_nothing(self, machine: Path, lenient: bool) -> None:
        """The control. Without it every case below would pass on a library that loaded nothing."""
        library = self._load(machine, lenient=lenient)

        assert set(library.root) == {"openai", "portkey"}
        assert library.take_stale_configuration_warning() is None

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_stale_directory_loads_the_same_models_the_current_files_would(self, machine: Path, lenient: bool) -> None:
        """The whole point: what boots is the migrated configuration, not a degraded one.

        Comparing against the library the untouched kit files produce is what makes "everything else
        intact" a real claim — every model, every cost, every request header, from both files.
        """
        pristine = self._load(machine, lenient=lenient)
        self._make_stale(machine)

        recovered = self._load(machine, lenient=lenient)

        assert recovered.root == pristine.root

    @pytest.mark.parametrize("lenient", [True, False])
    def test_it_parks_one_warning_naming_every_stale_file_and_the_remedy(self, machine: Path, lenient: bool) -> None:
        openai_file, portkey_file = self._make_stale(machine)

        library = self._load(machine, lenient=lenient)

        warning = library.take_stale_configuration_warning()
        assert warning is not None
        assert str(openai_file) in warning
        assert str(portkey_file) in warning
        assert "Drop prompting_target from every backend definition" in warning
        assert "Run `pipelex migrate`" in warning
        assert "Nothing was written" in warning
        assert library.take_stale_configuration_warning() is None, "a warning is handed over once"

    def test_the_warning_carries_no_value_read_from_the_users_file(self, machine: Path) -> None:
        """Ledger text only, the same rule the migration report obeys."""
        self._make_stale(machine)

        library = self._load(machine, lenient=False)

        warning = library.take_stale_configuration_warning()
        assert warning is not None
        assert "gemini" not in warning
        assert "gpt-4o" not in warning

    def test_nothing_is_written_to_disk(self, machine: Path) -> None:
        """Boot never writes — no rewrite, and no backup beside the file either."""
        self._make_stale(machine)
        backends_dir = self._backends_dir(machine)
        before = {path.name: path.read_bytes() for path in sorted(backends_dir.iterdir())}

        self._load(machine, lenient=False)

        assert {path.name: path.read_bytes() for path in sorted(backends_dir.iterdir())} == before

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_key_the_user_chose_to_have_is_still_fatal(self, machine: Path, lenient: bool) -> None:
        """Tolerance is not leniency. The ledger explains what *we* removed and nothing else."""
        plant_on_model(path=self._backends_dir(machine) / "openai.toml", table_header="[gpt-4o]", key="foo", value="1")

        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            self._load(machine, lenient=lenient)

        assert "'foo'" in str(exc_info.value)

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_file_the_ledger_only_half_explains_raises_the_users_own_error(self, machine: Path, lenient: bool, mocker: MockerFixture) -> None:
        """The branch where the replay does real work and still does not get there.

        This file carries both the key the ledger removes and one it has never heard of, and the
        user's own key sits on the *earlier* model — so the error the load produces is about `foo`,
        the replay then fires for real (there is a `prompting_target` further down to remove), and
        the re-validation fails anyway. What the user sees is still their own error, naming the key
        they can act on; "migration did not help" would name nothing.
        """
        openai_file = self._backends_dir(machine) / "openai.toml"
        plant_on_model(path=openai_file, table_header="[gpt-4o]", key="foo", value="1")
        plant_on_model(path=openai_file, table_header='["gpt-5.5"]')
        retry = mocker.spy(InferenceBackendLibrary, "_local_model_specs_the_ledger_can_explain")

        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            self._load(machine, lenient=lenient)

        assert "'foo'" in str(exc_info.value)
        assert retry.call_count == 1, "the retry was attempted"
        assert retry.spy_return is None, "and it declined, rather than the error never reaching it"

    def test_a_healthy_directory_never_reaches_the_migration_engine(self, machine: Path, mocker: MockerFixture) -> None:
        """The retry runs on the failure path only, so a current machine pays nothing for it."""
        retry = mocker.spy(InferenceBackendLibrary, "_local_model_specs_the_ledger_can_explain")

        self._load(machine, lenient=False)

        assert retry.call_count == 0


def replace_once(*, path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected exactly one {old!r} in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


class TestThePreviousReleaseKit:
    """A machine set up by the previous release is told what to change, then boots once it has.

    As that release left it, its `backends.toml` enables the Pipelex Gateway over a comment-only file and
    its active routing profile sends every model there: that is refused, naming the backend, rather than
    booted with every model silently missing from the deck. Once the user disables that table and picks
    another profile, as the changelog says, the rest loads: the disabled table of a backend the current kit no longer carries, which carries a key
    the backend blueprint does not define, is skipped before its variables are substituted or its file is
    read, and only the active routing profile is validated against the enabled backends.
    """

    @pytest.fixture
    def inference_dir(self, tmp_path: Path) -> Path:
        inference_dir = tmp_path / INFERENCE_DIR_NAME
        inference_dir.mkdir()
        shutil.copy(PREVIOUS_RELEASE_KIT_DIR / BACKENDS_FILE_NAME, inference_dir / BACKENDS_FILE_NAME)
        shutil.copy(PREVIOUS_RELEASE_KIT_DIR / ROUTING_PROFILES_FILE_NAME, inference_dir / ROUTING_PROFILES_FILE_NAME)
        backends_dir = inference_dir / BACKENDS_DIR_NAME
        shutil.copytree(kit_backends_dir(), backends_dir)
        shutil.copytree(PREVIOUS_RELEASE_KIT_DIR / BACKENDS_DIR_NAME, backends_dir, dirs_exist_ok=True)
        assert not (backends_dir / f"{PREVIOUS_RELEASE_DISABLED_BACKEND}.toml").exists(), "the disabled backend must have no file to read"
        return inference_dir

    @pytest.fixture
    def environment(self, inference_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dummy value for every variable the enabled tables reference, and none for the disabled table's."""
        library_text = (inference_dir / BACKENDS_FILE_NAME).read_text(encoding="utf-8")
        referenced_vars = set(re.findall(r"\$\{([A-Z0-9_]+)\}", library_text))
        assert set(PREVIOUS_RELEASE_DISABLED_BACKEND_VARS) <= referenced_vars, "the fixture no longer exercises the disabled table"
        for var_name in referenced_vars - set(PREVIOUS_RELEASE_DISABLED_BACKEND_VARS):
            monkeypatch.setenv(var_name, f"dummy-{var_name.lower()}")
        for var_name in PREVIOUS_RELEASE_DISABLED_BACKEND_VARS:
            monkeypatch.delenv(var_name, raising=False)

    @pytest.mark.usefixtures("environment")
    @pytest.mark.parametrize("lenient", [True, False])
    def test_as_left_its_enabled_gateway_serving_no_model_is_refused(self, inference_dir: Path, lenient: bool) -> None:
        library = InferenceBackendLibrary.make_empty()
        with pytest.raises(InferenceBackendLibraryValidationError) as refused:
            library.load(
                secrets_provider=EnvSecretsProvider(),
                backends_library_paths=[inference_dir / BACKENDS_FILE_NAME],
                backends_dir_path=str(inference_dir / BACKENDS_DIR_NAME),
                lenient=lenient,
            )

        assert refused.value.backend_name == PREVIOUS_RELEASE_EMPTY_ENABLED_BACKEND
        assert "declares no model" in str(refused.value)

    @pytest.mark.usefixtures("environment")
    @pytest.mark.parametrize("lenient", [True, False])
    def test_its_backends_and_active_routing_profile_load_once_remedied(self, inference_dir: Path, lenient: bool) -> None:
        replace_once(path=inference_dir / BACKENDS_FILE_NAME, old=PREVIOUS_RELEASE_GATEWAY_ENABLED_LINE, new="enabled = false")
        replace_once(path=inference_dir / ROUTING_PROFILES_FILE_NAME, old='active = "all_pipelex_gateway"', new='active = "all_openai"')
        library = InferenceBackendLibrary.make_empty()
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=[inference_dir / BACKENDS_FILE_NAME],
            backends_dir_path=str(inference_dir / BACKENDS_DIR_NAME),
            lenient=lenient,
        )

        enabled_backends = library.all_enabled_backends()
        assert PREVIOUS_RELEASE_DISABLED_BACKEND not in library.root
        assert {"openai", "anthropic", "internal"} <= set(enabled_backends)
        assert library.take_stale_configuration_warning() is None

        routing_profile = load_active_routing_profile(
            routing_profile_library_paths=[inference_dir / ROUTING_PROFILES_FILE_NAME],
            enabled_backends=enabled_backends,
            lenient=lenient,
        )

        assert routing_profile.default in enabled_backends
        assert routing_profile.default != PREVIOUS_RELEASE_DISABLED_BACKEND
