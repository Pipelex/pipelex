"""`copy_kit_templates`, the one walk `pipelex init` and the first boot both lay the kit's templates down with."""

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
