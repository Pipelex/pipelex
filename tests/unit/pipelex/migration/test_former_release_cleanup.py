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

from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.fix_ops.file_transaction import PendingFileUpdate, commit_file_updates
from pipelex.kit.paths import RETIRED_SERVICE_FILE_NAME, get_kit_configs_dir
from pipelex.migration import former_release_cleanup as former_release_cleanup_module
from pipelex.migration.backup import backup_path_for, existing_backups_of
from pipelex.migration.former_release import (
    MODEL_SPECS_SECTION_KEY,
    FormerReleaseFinding,
    detect_former_release,
    kit_default_routing_profile_name,
)
from pipelex.migration.former_release_cleanup import CleanedText, FormerReleaseFileAction, clean_former_release
from pipelex.migration.plan import FileBlockedReason
from pipelex.suggested_fix import DeleteKeyOp
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
    (RETIRED_SERVICE_FILE_NAME, FormerReleaseFileAction.REMOVE),
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
        assert changes[RETIRED_SERVICE_FILE_NAME] == ["removed the record of the Pipelex Gateway's terms acceptance"]

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
                'active = "all_pipelex_gateway"\n\n[profiles.all_openai]\ndescription = "o"\ndefault = "openai"\n\n[notes]\nseen = true\n\n'
                '[profiles.all_anthropic]\ndescription = "a"\ndefault = "anthropic"\n',
                id="profiles_spread_between_tables",
            ),
        ],
    )
    def test_a_hand_shaped_base_is_given_the_kit_default_profile(self, tmp_path: Path, routing_text: str) -> None:
        config_dir = tmp_path / ".pipelex"
        (config_dir / INFERENCE_DIR_NAME).mkdir(parents=True)
        (config_dir / ROUTING).write_text(routing_text, encoding="utf-8")

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        # The shape is the cleanup's to handle; a table the routing library does not know, like the `notes` one, is
        # the boot's to refuse, and the check after the write reports it rather than calling the machine fixed.
        assert not cleanup.blocked_files
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
        assert not (config_dir / RETIRED_SERVICE_FILE_NAME).exists()

    def test_a_symlinked_file_of_its_own_is_removed_as_a_link_and_what_it_names_is_kept(self, tmp_path: Path) -> None:
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        dotfiles_copy = tmp_path / "dotfiles" / RETIRED_SERVICE_FILE_NAME
        dotfiles_copy.parent.mkdir()
        (config_dir / RETIRED_SERVICE_FILE_NAME).rename(dotfiles_copy)
        (config_dir / RETIRED_SERVICE_FILE_NAME).symlink_to(dotfiles_copy)

        clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not (config_dir / RETIRED_SERVICE_FILE_NAME).is_symlink()
        assert not (config_dir / RETIRED_SERVICE_FILE_NAME).exists()
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

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_inline_profiles_are_left_for_a_hand_edit_rather_than_activating_a_profile_they_lack(self, tmp_path: Path, dry_run: bool) -> None:
        """The kit's profile cannot be added to an inline `profiles` table, so `active` is not moved to it either."""
        config_dir = tmp_path / ".pipelex"
        routing_path = config_dir / ROUTING
        routing_path.parent.mkdir(parents=True)
        routing_path.write_text(
            'active = "all_pipelex_gateway"\n'
            'profiles = { all_pipelex_gateway = { description = "g", default = "pipelex_gateway" }, '
            'mine = { description = "m", default = "openai" } }\n',
            encoding="utf-8",
        )
        before = routing_path.read_bytes()

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=dry_run, moment=MOMENT)

        assert [(file.file_path, file.blocked_reason) for file in cleanup.files] == [(routing_path, FileBlockedReason.NEEDS_A_HAND_EDIT)]
        assert kit_default_routing_profile_name() in (cleanup.files[0].blocked_detail or "")
        assert cleanup.needs_attention
        assert routing_path.read_bytes() == before

    def test_an_override_retargeting_a_profile_to_a_retired_backend_loses_that_default_and_nothing_else(self, tmp_path: Path) -> None:
        """The profile is the user's, defined in the base with routes of its own: only the override's choice of backend goes."""
        config_dir = tmp_path / ".pipelex"
        base_path = config_dir / ROUTING
        override_path = config_dir / INFERENCE_DIR_NAME / ROUTING_PROFILES_OVERRIDE_FILE_NAME
        base_path.parent.mkdir(parents=True)
        base_path.write_text(
            'active = "custom"\n\n[profiles.custom]\ndescription = "my tuned routes"\ndefault = "openai"\n\n'
            '[profiles.custom.routes]\n"claude-*" = "anthropic"\n"gpt-5*" = "openai"\n',
            encoding="utf-8",
        )
        override_path.write_text('[profiles.custom]\ndefault = "pipelex_gateway"\n', encoding="utf-8")
        base_before = base_path.read_bytes()

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not cleanup.needs_attention
        assert [(file.file_path, file.changes) for file in cleanup.files] == [
            (override_path, ["removed 'default', which named 'pipelex_gateway', from the routing profile 'custom'"])
        ]
        assert base_path.read_bytes() == base_before
        assert override_path.read_text(encoding="utf-8") == "", "a table left with nothing to override goes with its key"
        profile = load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["openai", "anthropic"])
        assert (profile.name, profile.default, profile.routes) == ("custom", "openai", {"claude-*": "anthropic", "gpt-5*": "openai"})
        assert detect_former_release(config_dir=config_dir).is_clean

    def test_a_note_of_the_users_about_a_gateway_of_their_own_stays(self, tmp_path: Path) -> None:
        """Only the former release's own wording marks a head comment as its own; a user's note about another gateway is theirs."""
        config_dir = tmp_path / ".pipelex"
        backends_path = config_dir / BACKENDS
        backends_path.parent.mkdir(parents=True)
        user_note = (
            "# Team note: all OpenAI traffic goes through our corporate API gateway (see wiki).\n# Do not change the endpoint without asking infra.\n"
        )
        backends_path.write_text(
            f'{user_note}\n[openai]\nenabled = true\napi_key = "${{OPENAI_API_KEY}}"\n\n[pipelex_gateway]\nenabled = false\n', encoding="utf-8"
        )

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert [file.changes for file in cleanup.files] == [["removed the 'pipelex_gateway' backend"]]
        text = backends_path.read_text(encoding="utf-8")
        assert text.startswith(user_note)
        assert "pipelex_gateway" not in text

    def test_a_catch_all_route_to_the_gateway_is_deleted_as_the_literal_key_it_is(self, tmp_path: Path) -> None:
        """`"*"` is a route a user writes to send every other model somewhere; to the cleanup it is a key like any other."""
        config_dir = tmp_path / ".pipelex"
        routing_path = config_dir / ROUTING
        routing_path.parent.mkdir(parents=True)
        routing_path.write_text(
            'active = "mine"\n\n[profiles.mine]\ndescription = "everything through the gateway except claude"\ndefault = "openai"\n\n'
            '[profiles.mine.routes]\n"*" = "pipelex_gateway"\n"claude-*" = "anthropic"\n',
            encoding="utf-8",
        )

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not cleanup.needs_attention
        assert [file.changes for file in cleanup.files] == [["removed the route of '*' to 'pipelex_gateway' from the routing profile 'mine'"]]
        profile = load_active_routing_profile(routing_profile_library_paths=[routing_path], enabled_backends=["openai", "anthropic"])
        assert (profile.name, profile.default, profile.routes) == ("mine", "openai", {"claude-*": "anthropic"})

    def test_a_profile_named_like_the_wildcard_is_the_only_one_removed(self, tmp_path: Path) -> None:
        """A profile spelled `"*"` names itself, never every profile of the file."""
        config_dir = tmp_path / ".pipelex"
        routing_path = config_dir / ROUTING
        routing_path.parent.mkdir(parents=True)
        routing_path.write_text(
            'active = "mine"\n\n[profiles."*"]\ndescription = "odd"\ndefault = "pipelex_gateway"\n\n'
            '[profiles.mine]\ndescription = "mine"\ndefault = "openai"\n',
            encoding="utf-8",
        )

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not cleanup.needs_attention
        assert list(load_toml_from_path(routing_path)["profiles"]) == ["mine"]

    def test_a_change_the_cleanup_cannot_express_blocks_its_file_and_never_the_run(self, tmp_path: Path, mocker: "MockerFixture") -> None:
        """One odd file is reported for a hand edit, and every other file is still cleaned: nothing crosses the per-file boundary."""
        config_dir = _copy_v0_72(tmp_path=tmp_path)
        routing_path = config_dir / ROUTING
        routing_before = routing_path.read_bytes()
        real_cleaned_text = former_release_cleanup_module.cleaned_text

        def _refused_for_the_routing_file(*, text: str, findings: list[FormerReleaseFinding], kit_default: str, is_override: bool) -> CleanedText:
            if findings[0].file_path == routing_path:
                DeleteKeyOp(table_path=[], key="*")
            return real_cleaned_text(text=text, findings=findings, kit_default=kit_default, is_override=is_override)

        mocker.patch.object(former_release_cleanup_module, "cleaned_text", side_effect=_refused_for_the_routing_file)

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert [file.file_path for file in cleanup.blocked_files] == [routing_path]
        assert cleanup.blocked_files[0].blocked_reason is FileBlockedReason.NEEDS_A_HAND_EDIT
        assert routing_path.read_bytes() == routing_before
        assert (config_dir / BACKENDS).read_bytes() == (V0_72_CLEANED_DIR / BACKENDS).read_bytes()

    def test_a_users_notes_mentioning_the_gateway_at_the_head_stay(self, tmp_path: Path) -> None:
        """Only the paragraphs the former release itself shipped go from the head of a document; a user's note naming the Gateway stays."""
        config_dir = tmp_path / ".pipelex"
        backends_path = config_dir / BACKENDS
        routing_path = config_dir / ROUTING
        backends_path.parent.mkdir(parents=True)
        backends_note = "# My backends. Note to self: I stopped using pipelex_gateway in March, keys are in 1Password.\n"
        routing_note = "# Kept for history: the old pipelex_gateway profile was my default until v0.72.\n"
        backends_path.write_text(
            f'{backends_note}[openai]\nenabled = true\napi_key = "${{OPENAI_API_KEY}}"\nmodel_specs_section = "openai"\n\n'
            '[anthropic]\nenabled = true\napi_key = "${ANTHROPIC_API_KEY}"\n',
            encoding="utf-8",
        )
        routing_path.write_text(
            f'active = "mine"\n\n{routing_note}[profiles.mine]\ndescription = "mine"\ndefault = "openai"\n\n'
            '[profiles.old]\ndescription = "old"\ndefault = "pipelex_gateway"\n',
            encoding="utf-8",
        )

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=False, moment=MOMENT)

        assert not cleanup.needs_attention
        assert len(cleanup.applied_files) == 2
        assert backends_path.read_text(encoding="utf-8").startswith(backends_note)
        assert routing_note in routing_path.read_text(encoding="utf-8")
        assert all("removed a comment" not in change for file in cleanup.files for change in file.changes)

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_a_rewrite_that_would_stop_a_boot_that_starts_is_never_written(self, tmp_path: Path, mocker: "MockerFixture", dry_run: bool) -> None:
        """The last check before writing reads the new texts as the boot would: a rewrite the plan did not foresee leaving a
        boot that starts today without its profile is left for a hand edit, whatever produced it.
        """
        config_dir = tmp_path / ".pipelex"
        routing_path = config_dir / ROUTING
        routing_path.parent.mkdir(parents=True)
        kit_routing = (Path(str(get_kit_configs_dir())) / ROUTING).read_text(encoding="utf-8")
        routing_path.write_text(kit_routing + '\n[profiles.old]\ndescription = "old"\ndefault = "pipelex_gateway"\n', encoding="utf-8")
        routing_before = routing_path.read_bytes()

        def _a_cleanup_bug(**kwargs: object) -> CleanedText:
            return CleanedText(text=f'active = "{kwargs["kit_default"]}"\n', changes=["removed every routing profile"])

        mocker.patch.object(former_release_cleanup_module, "cleaned_text", side_effect=_a_cleanup_bug)

        cleanup = clean_former_release(config_dirs=[config_dir], dry_run=dry_run, moment=MOMENT)

        assert [(file.file_path, file.blocked_reason) for file in cleanup.blocked_files] == [(routing_path, FileBlockedReason.NEEDS_A_HAND_EDIT)]
        assert "would stop Pipelex from starting as it does now" in (cleanup.blocked_files[0].blocked_detail or "")
        assert routing_path.read_bytes() == routing_before
