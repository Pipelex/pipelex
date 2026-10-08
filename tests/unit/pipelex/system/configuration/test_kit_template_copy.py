"""`copy_kit_templates`, the one walk `pipelex init` and the first boot both lay the kit's templates down with."""

import sys
from pathlib import Path

import pytest

from pipelex.kit.template_copy import copy_kit_templates, write_text_atomically


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
        ("overwrite", "expected_linked_content"),
        [
            pytest.param(False, "the user's own\n", id="kept_and_never_written_through_without_overwrite"),
            pytest.param(True, "kit pipelex\n", id="written_through_to_its_target_with_overwrite"),
        ],
    )
    def test_a_link_at_a_file_s_destination_survives(self, template_dir: Path, tmp_path: Path, overwrite: bool, expected_linked_content: str) -> None:
        """A configuration file linked from a dotfiles repository stays linked.

        The fill, which never overwrites, leaves the link and the file it points to alone; `init_config(reset=True)`,
        which every `pipelex init` and `pipelex-agent init` copy takes, rewrites the file it points to, whole,
        and leaves nothing else beside it.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        linked_file = tmp_path / "dotfiles" / "pipelex.toml"
        _write_files(linked_file.parent, files={linked_file.name: "the user's own\n"})
        (target_dir / "pipelex.toml").symlink_to(linked_file)

        copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=overwrite)

        assert (target_dir / "pipelex.toml").is_symlink()
        assert (target_dir / "pipelex.toml").readlink() == linked_file
        assert linked_file.read_text(encoding="utf-8") == expected_linked_content
        assert [path.name for path in linked_file.parent.iterdir()] == ["pipelex.toml"]

    @pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default")
    def test_overwrite_through_a_dangling_link_writes_its_target_when_that_directory_exists(self, template_dir: Path, tmp_path: Path) -> None:
        """What a plain copy did: the link's target is created, and the link now points at the template."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        linked_file = tmp_path / "dotfiles" / "pipelex.toml"
        linked_file.parent.mkdir()
        (target_dir / "pipelex.toml").symlink_to(linked_file)

        copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=True)

        assert (target_dir / "pipelex.toml").is_symlink()
        assert linked_file.read_text(encoding="utf-8") == "kit pipelex\n"

    @pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default")
    def test_overwrite_through_a_dangling_link_whose_directory_is_gone_raises(self, template_dir: Path, tmp_path: Path) -> None:
        """What a plain copy did as well: there is nowhere to write, and the caller is told so."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        linked_file = tmp_path / "gone" / "pipelex.toml"
        (target_dir / "pipelex.toml").symlink_to(linked_file)

        with pytest.raises(FileNotFoundError):
            copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=True)

        assert (target_dir / "pipelex.toml").is_symlink()
        assert not linked_file.parent.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default")
    @pytest.mark.parametrize(
        ("overwrite", "expected_in_linked_directory"),
        [
            pytest.param(False, [], id="never_entered_without_overwrite"),
            pytest.param(True, ["backends.toml", "deck/1_llm_deck.toml"], id="entered_with_overwrite"),
        ],
    )
    def test_a_linked_directory_is_entered_only_with_overwrite(
        self, template_dir: Path, tmp_path: Path, overwrite: bool, expected_in_linked_directory: list[str]
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        linked_directory = tmp_path / "dotfiles" / "inference"
        linked_directory.mkdir(parents=True)
        (target_dir / "inference").symlink_to(linked_directory, target_is_directory=True)

        copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=overwrite)

        assert (target_dir / "inference").is_symlink()
        assert sorted(path.relative_to(linked_directory).as_posix() for path in linked_directory.rglob("*") if path.is_file()) == (
            expected_in_linked_directory
        )

    def test_a_copy_leaves_no_temporary_file_behind(self, template_dir: Path, tmp_path: Path) -> None:
        target_dir = tmp_path / "target"

        copy_kit_templates(template_dir=template_dir, target_dir=target_dir, skip_names=_SKIP_NAMES, overwrite=False)

        assert sorted(path.relative_to(target_dir).as_posix() for path in target_dir.rglob("*") if path.is_file()) == [
            "inference/backends.toml",
            "inference/deck/1_llm_deck.toml",
            "pipelex.toml",
        ]

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits do not apply on Windows")
    def test_a_text_written_atomically_gets_the_mode_a_plain_write_gives_and_leaves_nothing_beside_it(self, tmp_path: Path) -> None:
        """A temporary file made private, as `mkstemp` makes one, would leave the renamed manifest readable by its owner only."""
        plainly_written = tmp_path / "plain.json"
        plainly_written.write_text("{}\n", encoding="utf-8")
        atomically_written = tmp_path / "atomic.json"

        write_text_atomically(destination=atomically_written, text="{}\n")

        assert atomically_written.read_text(encoding="utf-8") == "{}\n"
        assert atomically_written.stat().st_mode == plainly_written.stat().st_mode
        assert sorted(path.name for path in tmp_path.iterdir()) == ["atomic.json", "plain.json"]
