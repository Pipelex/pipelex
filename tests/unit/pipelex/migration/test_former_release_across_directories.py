"""The cleanup of a former release over the home and a project directory, read as the boot reads them.

The boot merges one base `routing_profiles.toml`, the project's when it has one and the home's otherwise, with the
home's override and then the project's. A profile one directory defines can therefore be made active by a file in the
other, and a cleanup that read each directory alone would delete the profile and leave the `active` naming it, so the
boot would fail on a profile it cannot find after a cleanup that reported success. The cleanup plans over the
sequences the boot reads, and checks after writing that nothing it can see still stops the boot.
"""

import shutil
from pathlib import Path

import pytest

from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.migration.former_release import (
    detect_former_release_across,
    former_release_boot_blockers,
    inference_merge_sequences,
    kit_default_routing_profile_name,
    kit_routing_profile_library_path,
)
from pipelex.migration.former_release_cleanup import clean_former_release
from pipelex.migration.plan import FileBlockedReason
from pipelex.system.configuration.config_loader import (
    BACKENDS_FILE_NAME,
    BACKENDS_OVERRIDE_FILE_NAME,
    INFERENCE_DIR_NAME,
    ROUTING_PROFILES_FILE_NAME,
    ROUTING_PROFILES_OVERRIDE_FILE_NAME,
    ConfigLoader,
)
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from pipelex.tools.misc.toml_utils import load_toml_from_path

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")
ENABLED_BACKENDS = ["openai", "anthropic"]
BACKENDS_TEXT = '[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[anthropic]\nenabled = true\napi_key = "${ANTHROPIC_API_KEY}"\n'
RETIRED_PROFILE_TEXT = '\n[profiles.{name}]\ndescription = "mine"\ndefault = "pipelex_gateway"\n'


def _write(*, path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _kit_routing_text() -> str:
    return kit_routing_profile_library_path().read_text(encoding="utf-8")


def _inference(*, config_dir: Path) -> Path:
    return config_dir / INFERENCE_DIR_NAME


def _boot_routing_sequence(*, home: Path, project: Path) -> list[Path]:
    """The routing sequence the boot reads, spelled out here rather than derived: the base, then each override."""
    project_base = _inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME
    base = project_base if project_base.is_file() else _inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME
    return [
        base,
        _inference(config_dir=home) / ROUTING_PROFILES_OVERRIDE_FILE_NAME,
        _inference(config_dir=project) / ROUTING_PROFILES_OVERRIDE_FILE_NAME,
    ]


def _boot_backends_sequence(*, home: Path, project: Path) -> list[Path]:
    project_base = _inference(config_dir=project) / BACKENDS_FILE_NAME
    base = project_base if project_base.is_file() else _inference(config_dir=home) / BACKENDS_FILE_NAME
    return [base, _inference(config_dir=home) / BACKENDS_OVERRIDE_FILE_NAME, _inference(config_dir=project) / BACKENDS_OVERRIDE_FILE_NAME]


def _active_profile_the_boot_loads(*, home: Path, project: Path) -> str:
    """The name of the profile the boot activates: it raises when the library names a profile it does not define."""
    routing_paths = _boot_routing_sequence(home=home, project=project)
    assert not former_release_boot_blockers(
        backends_library_paths=_boot_backends_sequence(home=home, project=project), routing_profile_library_paths=routing_paths
    )
    return load_active_routing_profile(routing_profile_library_paths=routing_paths, enabled_backends=ENABLED_BACKENDS).name


def _profile_the_home_boot_loads(*, home: Path) -> RoutingProfile:
    """The profile a boot started outside any project activates: the home's base and override alone."""
    routing_paths = [_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME, _inference(config_dir=home) / ROUTING_PROFILES_OVERRIDE_FILE_NAME]
    assert not former_release_boot_blockers(
        backends_library_paths=[_inference(config_dir=home) / BACKENDS_FILE_NAME, _inference(config_dir=home) / BACKENDS_OVERRIDE_FILE_NAME],
        routing_profile_library_paths=routing_paths,
    )
    return load_active_routing_profile(routing_profile_library_paths=routing_paths, enabled_backends=ENABLED_BACKENDS)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".pipelex"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path / "project" / ".pipelex"


class TestFormerReleaseAcrossDirectories:
    def test_a_home_override_activating_a_retired_profile_the_project_defines_stops_naming_it(self, home: Path, project: Path) -> None:
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME, text=_kit_routing_text())
        home_override = _write(path=_inference(config_dir=home) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='active = "my_gw"\n')
        _write(path=_inference(config_dir=project) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(path=_inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME, text=_kit_routing_text() + RETIRED_PROFILE_TEXT.format(name="my_gw"))

        rehearsal = clean_former_release(config_dirs=[home, project], dry_run=True)
        assert home_override in [file.file_path for file in rehearsal.files], "the override in the other directory is part of the plan"

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert not cleanup.needs_attention
        assert "active" not in load_toml_from_path(home_override)
        assert _active_profile_the_boot_loads(home=home, project=project) == kit_default_routing_profile_name()
        assert all(findings.is_clean for findings in detect_former_release_across(config_dirs=[home, project]))

    def test_a_project_override_activating_a_retired_profile_the_home_defines_stops_naming_it(self, home: Path, project: Path) -> None:
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME, text=_kit_routing_text() + RETIRED_PROFILE_TEXT.format(name="custom"))
        project_override = _write(path=_inference(config_dir=project) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='active = "custom"\n')

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert not cleanup.needs_attention
        assert "active" not in load_toml_from_path(project_override)
        assert _active_profile_the_boot_loads(home=home, project=project) == kit_default_routing_profile_name()

    def test_a_project_with_a_base_of_its_own_keeps_its_choice_when_the_home_is_cleaned(self, home: Path, project: Path) -> None:
        """The home's base is not what this project boots on, and cleaning it moves nothing the project chose."""
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(
            path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME,
            text=_kit_routing_text().replace(f'active = "{kit_default_routing_profile_name()}"', 'active = "custom"')
            + RETIRED_PROFILE_TEXT.format(name="custom"),
        )
        _write(path=_inference(config_dir=project) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        project_routing = _write(
            path=_inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME,
            text=_kit_routing_text() + '\n[profiles.custom]\ndescription = "the project\'s own"\ndefault = "openai"\n',
        )
        _write(path=_inference(config_dir=project) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='active = "custom"\n')
        project_routing_before = project_routing.read_bytes()

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert not cleanup.needs_attention
        assert project_routing.read_bytes() == project_routing_before
        assert _active_profile_the_boot_loads(home=home, project=project) == "custom"
        assert load_toml_from_path(_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME)["active"] == kit_default_routing_profile_name()

    def test_a_write_that_leaves_the_boot_stopped_needs_attention_and_says_why(self, home: Path, project: Path) -> None:
        """The safety net: after writing, what still stops the boot is reported, never a success."""
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT + "\n[pipelex_gateway]\nenabled = false\n")
        _write(
            path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME,
            text=_kit_routing_text().replace(f'active = "{kit_default_routing_profile_name()}"', 'active = "ghost"'),
        )

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert [file.was_applied for file in cleanup.files] == [True]
        assert cleanup.needs_attention
        assert len(cleanup.still_blocking) == 1
        assert "'ghost'" in cleanup.still_blocking[0]

    def test_a_dry_run_checks_the_files_as_it_would_leave_them(self, home: Path, project: Path) -> None:
        """A dry run reports what its writes would leave stopping the boot, and writes nothing to find out."""
        backends = _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT + "\n[pipelex_gateway]\nenabled = false\n")
        _write(
            path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME,
            text=_kit_routing_text().replace(f'active = "{kit_default_routing_profile_name()}"', 'active = "ghost"'),
        )
        backends_before = backends.read_bytes()

        rehearsal = clean_former_release(config_dirs=[home, project], dry_run=True)

        assert len(rehearsal.still_blocking) == 1
        assert "'ghost'" in rehearsal.still_blocking[0]
        assert rehearsal.needs_attention
        assert backends.read_bytes() == backends_before

    def test_a_dry_run_does_not_report_what_its_own_writes_would_fix(self, home: Path, project: Path) -> None:
        shutil.copytree(V0_72_CONFIG_DIR, home)

        rehearsal = clean_former_release(config_dirs=[home, project], dry_run=True)

        assert rehearsal.files
        assert rehearsal.still_blocking == []
        assert not rehearsal.needs_attention

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_a_run_with_nothing_left_to_clean_still_says_what_stops_the_boot(self, home: Path, project: Path, dry_run: bool) -> None:
        """A cleanup half done — from another project, or a file it could not write — leaves nothing a former release
        left, and a boot still stopped: the retry is not clean, and says why.
        """
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME, text=_kit_routing_text())
        _write(path=_inference(config_dir=project) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='active = "team_gateway"\n')

        retry = clean_former_release(config_dirs=[home, project], dry_run=dry_run)

        assert retry.files == []
        assert not retry.is_clean
        assert retry.needs_attention
        assert any("'team_gateway'" in problem for problem in retry.still_blocking)

    @pytest.mark.parametrize("project_active", ["custom", "all_openai"])
    def test_a_profile_one_boot_still_extends_keeps_its_description_in_the_other(self, home: Path, project: Path, project_active: str) -> None:
        """The home's override adds routes to `custom`, which the home defines and the project's own base defines with a
        Gateway default: the project's definition loses its default and keeps its description, so both boots start.
        """
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(
            path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME,
            text='active = "custom"\n\n[profiles.custom]\ndescription = "home custom"\ndefault = "openai"\n',
        )
        _write(path=_inference(config_dir=home) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='[profiles.custom.routes]\n"claude-*" = "anthropic"\n')
        _write(
            path=_inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME,
            text=f'active = "{project_active}"\n\n[profiles.all_openai]\ndescription = "o"\ndefault = "openai"\n\n'
            '[profiles.custom]\ndescription = "project custom"\ndefault = "pipelex_gateway"\n',
        )

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert not cleanup.needs_attention
        assert _profile_the_home_boot_loads(home=home).name == "custom"
        assert _active_profile_the_boot_loads(home=home, project=project) == project_active
        project_library = load_toml_from_path(_inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME)
        assert project_library["profiles"]["custom"] == {"description": "project custom"}

    def test_a_home_profile_a_project_override_retargets_stays_for_the_project_while_the_home_moves_off_it(self, home: Path, project: Path) -> None:
        """v0.72's home activates `all_pipelex_gateway`; the project's override retargets it to OpenAI. The project's boot
        keeps starting on it, through an `active` of its own, and the boot outside the project moves to the kit's profile
        instead of being left on a profile with nothing to route by.
        """
        shutil.copytree(V0_72_CONFIG_DIR, home)
        project_override = _write(
            path=_inference(config_dir=project) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='[profiles.all_pipelex_gateway]\ndefault = "openai"\n'
        )

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert not cleanup.needs_attention
        assert load_toml_from_path(project_override)["active"] == "all_pipelex_gateway"
        home_boot = _profile_the_home_boot_loads(home=home)
        assert home_boot.name == kit_default_routing_profile_name()
        assert home_boot.fallback_order
        assert _active_profile_the_boot_loads(home=home, project=project) == "all_pipelex_gateway"
        project_boot = load_active_routing_profile(
            routing_profile_library_paths=_boot_routing_sequence(home=home, project=project), enabled_backends=ENABLED_BACKENDS
        )
        assert project_boot.default == "openai"

    @pytest.mark.parametrize("project_has_an_override", [False, True])
    def test_a_shared_override_naming_a_profile_only_one_boot_has_is_never_moved_under_the_other(
        self, home: Path, project: Path, project_has_an_override: bool
    ) -> None:
        """The home's override activates the user's own `all_pipelex_gateway`, routed to OpenAI and defined in the home's
        base; the project's base has no such profile. Deleting that `active` would switch the boot outside the project to
        another profile: it stays. The project is given its own `active` when it has an override to hold it, and the
        shared file is otherwise left for a hand edit naming the conflict.
        """
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(
            path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME,
            text='active = "all_openai"\n\n[profiles.all_openai]\ndescription = "o"\ndefault = "openai"\n\n'
            '[profiles.all_pipelex_gateway]\ndescription = "mine"\ndefault = "openai"\n',
        )
        home_override = _write(path=_inference(config_dir=home) / ROUTING_PROFILES_OVERRIDE_FILE_NAME, text='active = "all_pipelex_gateway"\n')
        _write(
            path=_inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME,
            text='active = "all_openai"\n\n[profiles.all_openai]\ndescription = "o"\ndefault = "openai"\n',
        )
        project_override = _inference(config_dir=project) / ROUTING_PROFILES_OVERRIDE_FILE_NAME
        if project_has_an_override:
            _write(path=project_override, text="# my project's own settings\n")
        home_override_before = home_override.read_bytes()

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        assert home_override.read_bytes() == home_override_before
        assert _profile_the_home_boot_loads(home=home).name == "all_pipelex_gateway"
        if project_has_an_override:
            assert not cleanup.needs_attention
            assert load_toml_from_path(project_override)["active"] == "all_openai"
            assert _active_profile_the_boot_loads(home=home, project=project) == "all_openai"
        else:
            assert [(file.file_path, file.blocked_reason) for file in cleanup.files] == [(home_override, FileBlockedReason.NEEDS_A_HAND_EDIT)]
            assert str(project_override) in (cleanup.files[0].blocked_detail or "")
            assert cleanup.still_blocking
            assert not project_override.exists()

    def test_the_sequences_are_the_ones_the_config_loader_reads(self, home: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """One derivation of what a boot reads: the cleanup's sequences, on a real home and project, are the loader's."""
        _write(path=_inference(config_dir=home) / BACKENDS_FILE_NAME, text=BACKENDS_TEXT)
        _write(path=_inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME, text=_kit_routing_text())
        _write(path=project.parent / "pyproject.toml", text="[project]\nname = 'x'\n")
        _write(path=_inference(config_dir=project) / ROUTING_PROFILES_FILE_NAME, text=_kit_routing_text())
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
        monkeypatch.chdir(project.parent)
        loader = ConfigLoader()
        config_dirs = loader.existing_config_dirs
        assert config_dirs == [home, project]

        routing_sequences = inference_merge_sequences(
            config_dirs=config_dirs, file_name=ROUTING_PROFILES_FILE_NAME, override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME
        )
        backends_sequences = inference_merge_sequences(
            config_dirs=config_dirs, file_name=BACKENDS_FILE_NAME, override_file_name=BACKENDS_OVERRIDE_FILE_NAME
        )

        assert routing_sequences[-1] == loader.routing_profiles_file_paths()
        assert backends_sequences[-1] == loader.backends_file_paths()
        assert routing_sequences[0] == [
            _inference(config_dir=home) / ROUTING_PROFILES_FILE_NAME,
            _inference(config_dir=home) / ROUTING_PROFILES_OVERRIDE_FILE_NAME,
        ]
