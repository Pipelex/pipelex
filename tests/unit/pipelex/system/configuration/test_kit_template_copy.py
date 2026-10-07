"""`copy_kit_templates`, the one walk `pipelex init` and the first boot both lay the kit's templates down with."""

import sys
from pathlib import Path

import pytest

from pipelex.kit.template_copy import copy_kit_templates


def _write_files(directory: Path, *, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        target = directory / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _files_under(directory: Path) -> dict[str, str]:
    if not directory.exists():
        return {}
    return {path.relative_to(directory).as_posix(): path.read_text(encoding="utf-8") for path in directory.rglob("*") if path.is_file()}


_TEMPLATES = {
    "pipelex.toml": "kit pipelex\n",
    "skipped.toml": "never copied\n",
    "inference/backends.toml": "kit backends\n",
    "inference/deck/1_llm_deck.toml": "kit deck\n",
    "inference/deck/skipped.toml": "never copied either\n",
    "storage/data.toml": "under a skipped directory\n",
}
_SKIP_NAMES = frozenset({"skipped.toml", "storage"})


class TestKitTemplateCopy:
    @pytest.fixture
    def template_dir(self, tmp_path: Path) -> Path:
        template_dir = tmp_path / "kit"
        _write_files(template_dir, files=_TEMPLATES)
        return template_dir

    @pytest.mark.parametrize(
        ("existing", "overwrite", "expected_copied", "expected_after"),
        [
            pytest.param(
                {},
                False,
                ["inference/backends.toml", "inference/deck/1_llm_deck.toml", "pipelex.toml"],
                {"pipelex.toml": "kit pipelex\n", "inference/backends.toml": "kit backends\n", "inference/deck/1_llm_deck.toml": "kit deck\n"},
                id="empty_target_receives_every_file_not_skipped",
            ),
            pytest.param(
                {"inference/backends.toml": "mine\n", "notes.txt": "unrelated\n"},
                False,
                ["inference/deck/1_llm_deck.toml", "pipelex.toml"],
                {
                    "pipelex.toml": "kit pipelex\n",
                    "inference/backends.toml": "mine\n",
                    "inference/deck/1_llm_deck.toml": "kit deck\n",
                    "notes.txt": "unrelated\n",
                },
                id="a_file_the_target_holds_is_kept",
            ),
            pytest.param(
                {"inference/backends.toml": "mine\n", "notes.txt": "unrelated\n"},
                True,
                ["inference/backends.toml", "inference/deck/1_llm_deck.toml", "pipelex.toml"],
                {
                    "pipelex.toml": "kit pipelex\n",
                    "inference/backends.toml": "kit backends\n",
                    "inference/deck/1_llm_deck.toml": "kit deck\n",
                    "notes.txt": "unrelated\n",
                },
                id="overwrite_replaces_a_kit_file_and_leaves_the_rest",
            ),
        ],
    )
    def test_copy(
        self,
        template_dir: Path,
        tmp_path: Path,
        existing: dict[str, str],
        overwrite: bool,
        expected_copied: list[str],
        expected_after: dict[str, str],
    ) -> None:
        target_dir = tmp_path / "target"
        _write_files(target_dir, files=existing)

        copied = copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=overwrite)

        assert copied == expected_copied
        assert _files_under(target_dir) == expected_after

    def test_a_dry_run_writes_nothing_and_reports_what_a_real_run_would_copy(self, template_dir: Path, tmp_path: Path) -> None:
        target_dir = tmp_path / "target"
        _write_files(target_dir, files={"pipelex.toml": "mine\n"})

        copied = copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=False, dry_run=True)

        assert copied == ["inference/backends.toml", "inference/deck/1_llm_deck.toml"]
        assert _files_under(target_dir) == {"pipelex.toml": "mine\n"}
        assert not (target_dir / "inference").exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default")
    @pytest.mark.parametrize(
        ("overwrite", "link_is_kept"),
        [
            pytest.param(False, True, id="kept_without_overwrite"),
            pytest.param(True, False, id="replaced_as_a_link_with_overwrite"),
        ],
    )
    def test_a_link_at_a_file_s_destination_is_never_written_through(
        self, template_dir: Path, tmp_path: Path, overwrite: bool, link_is_kept: bool
    ) -> None:
        """Overwriting replaces the link itself, as `pipelex init` does, and the file it pointed to stays as it was."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        linked_file = tmp_path / "dotfiles" / "pipelex.toml"
        _write_files(linked_file.parent, files={linked_file.name: "the user's own\n"})
        (target_dir / "pipelex.toml").symlink_to(linked_file)

        copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=overwrite)

        assert linked_file.read_text(encoding="utf-8") == "the user's own\n"
        assert (target_dir / "pipelex.toml").is_symlink() == link_is_kept
        if not link_is_kept:
            assert (target_dir / "pipelex.toml").read_text(encoding="utf-8") == "kit pipelex\n"

    def test_a_copy_leaves_no_temporary_file_behind(self, template_dir: Path, tmp_path: Path) -> None:
        target_dir = tmp_path / "target"

        copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=False)

        assert sorted(path.relative_to(target_dir).as_posix() for path in target_dir.rglob("*") if path.is_file()) == [
            "inference/backends.toml",
            "inference/deck/1_llm_deck.toml",
            "pipelex.toml",
        ]
