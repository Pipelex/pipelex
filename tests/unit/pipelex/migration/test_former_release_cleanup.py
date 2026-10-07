"""The cleanup of what a former release left: goldens, backups, dry runs, overrides, and a write that cannot be made.

The v0.72 directory under `tests/data/migration/former_release/v0_72/` is that release's kit, copied from its wheel;
`v0_72_cleaned/` holds what its two rewritten documents must be, byte for byte, once cleaned. Everything else the
release left is a file of its own, which the cleanup removes and keeps a copy of.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.fix_ops.file_transaction import PendingFileUpdate, commit_file_updates
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.backup import backup_path_for, existing_backups_of
from pipelex.migration.former_release import (
    MODEL_SPECS_SECTION_KEY,
    SERVICE_FILE_NAME,
    detect_former_release,
    kit_default_routing_profile_name,
)
from pipelex.migration.former_release_cleanup import FormerReleaseFileAction, clean_former_release
from pipelex.migration.plan import FileBlockedReason
from pipelex.system.configuration.config_loader import (
    BACKENDS_DIR_NAME,
    BACKENDS_FILE_NAME,
    BACKENDS_OVERRIDE_FILE_NAME,
    INFERENCE_DIR_NAME,
    ROUTING_PROFILES_FILE_NAME,
    ROUTING_PROFILES_OVERRIDE_FILE_NAME,
)
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")
V0_72_CLEANED_DIR = Path("tests/data/migration/former_release/v0_72_cleaned")
PREVIOUS_RELEASE_KIT_DIR = Path("tests/data/inference/previous_release_kit")

MOMENT = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)

BACKENDS = f"{INFERENCE_DIR_NAME}/{BACKENDS_FILE_NAME}"
ROUTING = f"{INFERENCE_DIR_NAME}/{ROUTING_PROFILES_FILE_NAME}"
BACKEND_FILES = f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}"

# What the cleanup does to the v0.72 directory, file by file, in the order it reports them.
V0_72_ACTIONS = [
    (BACKENDS, FormerReleaseFileAction.REWRITE),
    (f"{BACKEND_FILES}/pipelex_gateway.toml", FormerReleaseFileAction.REMOVE),
    (f"{BACKEND_FILES}/pipelex_manifold.toml", FormerReleaseFileAction.REMOVE),
    (f"{BACKEND_FILES}/pipelex_gateway_models.md", FormerReleaseFileAction.REMOVE),
    (f"{BACKEND_FILES}/pipelex_gateway_models_plain.md", FormerReleaseFileAction.REMOVE),
    (SERVICE_FILE_NAME, FormerReleaseFileAction.REMOVE),
    (ROUTING, FormerReleaseFileAction.REWRITE),
]


def _copy_v0_72(*, tmp_path: Path) -> Path:
    config_dir = tmp_path / ".pipelex"
    shutil.copytree(V0_72_CONFIG_DIR, config_dir)
    return config_dir


def _snapshot(*, directory: Path) -> dict[str, bytes]:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


class TestCleanFormerRelease:
    def test_a_v0_72_directory_is_cleaned_to_its_goldens_with_one_backup_per_file(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        before = _snapshot(directory=config_dir)

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert [(file.file_path.relative_to(config_dir).as_posix(), file.action) for file in cleanup.files] == V0_72_ACTIONS
        assert not cleanup.needs_attention
        assert all(file.was_applied and file.changes for file in cleanup.files)
        for relative_path in (BACKENDS, ROUTING):
            assert (config_dir / relative_path).read_bytes() == (V0_72_CLEANED_DIR / relative_path).read_bytes(), relative_path
        for relative_path, action in V0_72_ACTIONS:
            original = config_dir / relative_path
            backup = backup_path_for(path=original, moment=MOMENT)
            assert backup.read_bytes() == before[relative_path], f"the backup of {relative_path} is not the original"
            assert existing_backups_of(path=original) == [backup]
            assert original.exists() == (action == FormerReleaseFileAction.REWRITE)
        assert detect_former_release(config_dir=config_dir).is_clean

    def test_the_cleaned_routing_profiles_make_the_kit_default_active(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)

        clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        routing = load_toml_from_path(config_dir / ROUTING)
        kit_routing = load_toml_from_path(Path(str(get_kit_configs_dir())) / ROUTING)
        kit_default = kit_default_routing_profile_name()
        assert routing["active"] == kit_default
        assert routing["profiles"][kit_default] == kit_routing["profiles"][kit_default]
        assert next(iter(routing["profiles"])) == kit_default, "the profile the file makes active comes first, as in the kit"

    def test_a_dry_run_reports_the_same_cleanup_and_writes_nothing(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        before = _snapshot(directory=config_dir)

        rehearsal = clean_former_release(config_dirs=[config_dir], dry_run=True, moment=MOMENT)

        assert _snapshot(directory=config_dir) == before
        assert rehearsal.dry_run
        assert [(file.file_path.relative_to(config_dir).as_posix(), file.action) for file in rehearsal.files] == V0_72_ACTIONS
        assert not any(file.was_applied or file.backup_path for file in rehearsal.files)

        applied = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)
        assert [file.changes for file in rehearsal.files] == [file.changes for file in applied.files]

    def test_a_second_run_finds_nothing_to_do(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)
        after_first = _snapshot(directory=config_dir)

        second = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=datetime(2026, 10, 8, tzinfo=UTC))

        assert second.is_clean
        assert _snapshot(directory=config_dir) == after_first

    def test_the_changes_name_what_was_removed_and_where_the_active_profile_went(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=True)

        changes = {file.file_path.relative_to(config_dir).as_posix(): file.changes for file in cleanup.files}
        assert changes[BACKENDS] == ["removed the 'pipelex_gateway' backend", "removed the 'pipelex_manifold' backend"]
        kit_default = kit_default_routing_profile_name()
        assert changes[ROUTING] == [
            f"added the routing profile '{kit_default}', as this release ships it",
            f"moved the active routing profile from 'all_pipelex_gateway' to '{kit_default}'",
            "removed the routing profile 'all_pipelex_gateway'",
            "removed the routing profile 'all_pipelex_manifold'",
            "removed the routing profile 'example_routing_using_patterns'",
            "removed the route of 'gpt-5.4-nano' to 'pipelex_gateway' from the routing profile 'example_routing_using_specific_models'",
            "removed the route of 'claude-4-sonnet' to 'pipelex_gateway' from the routing profile 'example_routing_using_specific_models'",
            "removed the route of 'gemini-2.5-flash-lite' to 'pipelex_gateway' from the routing profile 'example_routing_using_specific_models'",
            "removed the route of 'grok-3' to 'pipelex_gateway' from the routing profile 'example_routing_using_specific_models'",
            "removed a comment about the Pipelex Gateway",
        ]
        assert changes[SERVICE_FILE_NAME] == ["removed the record of the Pipelex Gateway's terms acceptance"]

    def test_an_override_loses_its_retired_active_profile_and_its_base_moves(self, tmp_path: Path) -> None:
        """An override that named the Gateway's profile stops naming any, so its base, moved to the kit default, applies."""
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        inference_dir = config_dir / INFERENCE_DIR_NAME
        (inference_dir / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('# my choice\nactive = "all_pipelex_gateway"\n', encoding="utf-8")
        (inference_dir / BACKENDS_OVERRIDE_FILE_NAME).write_text("[pipelex_gateway]\nenabled = true\n\n[openai]\nenabled = true\n", encoding="utf-8")

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not cleanup.needs_attention
        assert (inference_dir / ROUTING_PROFILES_OVERRIDE_FILE_NAME).read_text(encoding="utf-8") == ""
        assert (inference_dir / BACKENDS_OVERRIDE_FILE_NAME).read_text(encoding="utf-8") == "[openai]\nenabled = true\n"
        assert load_toml_from_path(inference_dir / ROUTING_PROFILES_FILE_NAME)["active"] == kit_default_routing_profile_name()
        assert detect_former_release(config_dir=config_dir).is_clean

    def test_a_base_already_holding_the_kit_default_profile_is_given_no_second_one(self, tmp_path: Path) -> None:
        """The current kit with `active` left on the Gateway's profile: moving it back is the whole cleanup."""
        kit_routing = Path(str(get_kit_configs_dir())) / ROUTING
        kit_text = kit_routing.read_text(encoding="utf-8")
        kit_default = kit_default_routing_profile_name()
        config_dir = tmp_path / ".pipelex"
        (config_dir / INFERENCE_DIR_NAME).mkdir(parents=True)
        active_line = f'active = "{kit_default}"'
        assert kit_text.count(active_line) == 1
        (config_dir / ROUTING).write_text(kit_text.replace(active_line, 'active = "all_pipelex_gateway"'), encoding="utf-8")

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert [file.changes for file in cleanup.files] == [[f"moved the active routing profile from 'all_pipelex_gateway' to '{kit_default}'"]]
        assert (config_dir / ROUTING).read_text(encoding="utf-8") == kit_text

    @pytest.mark.parametrize(
        "routing_text",
        [
            pytest.param('active = "all_pipelex_gateway"\n', id="no_profiles"),
            pytest.param(
                'active = "all_pipelex_gateway"\n\n[profiles.all_openai]\ndefault = "openai"\n\n[notes]\nseen = true\n\n'
                '[profiles.all_anthropic]\ndefault = "anthropic"\n',
                id="profiles_spread_between_tables",
            ),
        ],
    )
    def test_a_hand_shaped_base_is_given_the_kit_default_profile(self, tmp_path: Path, routing_text: str) -> None:
        config_dir = tmp_path / ".pipelex"
        (config_dir / INFERENCE_DIR_NAME).mkdir(parents=True)
        (config_dir / ROUTING).write_text(routing_text, encoding="utf-8")

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not cleanup.needs_attention
        kit_default = kit_default_routing_profile_name()
        routing = load_toml_from_path(config_dir / ROUTING)
        kit_routing = load_toml_from_path(Path(str(get_kit_configs_dir())) / ROUTING)
        assert routing["active"] == kit_default
        assert routing["profiles"][kit_default] == kit_routing["profiles"][kit_default]

    def test_a_model_specs_section_key_is_removed_and_its_backend_kept(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".pipelex"
        shutil.copytree(PREVIOUS_RELEASE_KIT_DIR, config_dir / INFERENCE_DIR_NAME)

        clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        backends = load_toml_from_path(config_dir / BACKENDS)
        assert "retired_preview" in backends
        assert not any(MODEL_SPECS_SECTION_KEY in table for table in backends.values() if isinstance(table, dict))
        assert detect_former_release(config_dir=config_dir).is_clean

    def test_a_file_that_cannot_be_written_is_left_as_it_was_and_its_siblings_are_cleaned(self, tmp_path: Path, mocker: "MockerFixture") -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        routing_path = config_dir / ROUTING
        original_routing = routing_path.read_bytes()

        def refuse_the_routing_file(updates: list[PendingFileUpdate]) -> None:
            if updates[0].snapshot.path == routing_path.resolve():
                raise PermissionError(13, "Permission denied")
            commit_file_updates(updates)

        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=refuse_the_routing_file)

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert cleanup.needs_attention
        assert [(file.file_path.name, file.blocked_reason) for file in cleanup.blocked_files] == [
            (ROUTING_PROFILES_FILE_NAME, FileBlockedReason.UNWRITABLE)
        ]
        assert routing_path.read_bytes() == original_routing
        assert existing_backups_of(path=routing_path) == [], "the copy taken for a write that did not happen is taken back"
        assert (config_dir / BACKENDS).read_bytes() == (V0_72_CLEANED_DIR / BACKENDS).read_bytes()
        assert not (config_dir / SERVICE_FILE_NAME).exists()

    def test_a_symlinked_file_of_its_own_is_removed_as_a_link_and_what_it_names_is_kept(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        dotfiles_copy = tmp_path / "dotfiles" / SERVICE_FILE_NAME
        dotfiles_copy.parent.mkdir()
        (config_dir / SERVICE_FILE_NAME).rename(dotfiles_copy)
        (config_dir / SERVICE_FILE_NAME).symlink_to(dotfiles_copy)

        clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not (config_dir / SERVICE_FILE_NAME).is_symlink()
        assert not (config_dir / SERVICE_FILE_NAME).exists()
        assert dotfiles_copy.is_file()

    def test_each_directory_is_cleaned_once_and_a_clean_one_reports_nothing(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        clean_dir = tmp_path / "current"
        shutil.copytree(Path(str(get_kit_configs_dir())), clean_dir)

        cleanup = clean_former_release(config_dirs=[config_dir, clean_dir, config_dir], dry_run=True)

        assert len(cleanup.files) == len(V0_72_ACTIONS)
        assert clean_former_release(config_dirs=[clean_dir], dry_run=False).is_clean

    @pytest.mark.parametrize("dry_run", [False, True])
    def test_a_directory_with_nothing_to_clean_gains_no_gitignore(self, tmp_path: Path, dry_run: bool) -> None:
        clean_dir = tmp_path / ".pipelex"
        (clean_dir / INFERENCE_DIR_NAME).mkdir(parents=True)

        clean_former_release(config_dirs=[clean_dir], dry_run=dry_run)

        assert not (clean_dir / ".gitignore").exists()
