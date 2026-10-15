from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree

from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.pipeline.method_entry import select_method_entry


def _bundle(*, domain: str, pipe_code: str, main_pipe: str | None) -> str:
    main_pipe_line = f'main_pipe = "{main_pipe}"\n' if main_pipe else ""
    return f"""domain = "{domain}"
{main_pipe_line}
[pipe.{pipe_code}]
type        = "PipeLLM"
description = "Summarize the text"
inputs      = {{ text = "Text" }}
output      = "Text"
prompt      = "Summarize $text"
"""


def _manifest(*, main_pipe: str | None, exports: dict[str, list[str]]) -> str:
    main_pipe_line = f'main_pipe = "{main_pipe}"\n' if main_pipe else ""
    exports_text = "".join(f"\n[exports.{domain}]\npipes = {pipes!r}\n".replace("'", '"') for domain, pipes in exports.items())
    return f"""[package]
address = "github.com/pipelex-tests/entry"
version = "1.0.0"
description = "A method whose entry is selected"
{main_pipe_line}{exports_text}"""


def _write(*, directory: Path, files: dict[str, str]) -> Path:
    for tree_path, content in files.items():
        file_path = directory / tree_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    return directory


class TestMethodEntry:
    def test_a_method_with_no_manifest_starts_at_its_one_main_pipe(self, tmp_path: Path) -> None:
        """A bundle declaring no main_pipe is no rival: the one that declares it is where the method starts."""
        _write(
            directory=tmp_path,
            files={
                "steps/extract.mthds": _bundle(domain="entry_steps", pipe_code="extract", main_pipe=None),
                "report.mthds": _bundle(domain="entry_report", pipe_code="write_report", main_pipe="write_report"),
            },
        )

        entry = select_method_entry(tree=list_method_tree(tmp_path))

        assert entry.pipe_ref == "entry_report.write_report"
        assert entry.pipe_code == "write_report"
        assert entry.tree_path == "report.mthds"

    def test_a_manifest_names_the_entry_whatever_the_bundles_declare(self, tmp_path: Path) -> None:
        """With a METHODS.toml at the root, its main_pipe wins over every bundle's, however many declare one."""
        _write(
            directory=tmp_path,
            files={
                "METHODS.toml": _manifest(main_pipe="extract", exports={"entry_steps": ["extract"]}),
                "steps/extract.mthds": _bundle(domain="entry_steps", pipe_code="extract", main_pipe="extract"),
                "report.mthds": _bundle(domain="entry_report", pipe_code="write_report", main_pipe="write_report"),
            },
        )

        entry = select_method_entry(tree=list_method_tree(tmp_path))

        assert entry.pipe_ref == "entry_steps.extract"
        assert entry.tree_path == "steps/extract.mthds"

    @pytest.mark.parametrize(
        ("files", "expected"),
        [
            (
                {
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe=None),
                    "b/b.mthds": _bundle(domain="entry_b", pipe_code="second", main_pipe=None),
                },
                "none of its bundles declares a main_pipe ('a.mthds', 'b/b.mthds')",
            ),
            (
                {
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first"),
                    "b/b.mthds": _bundle(domain="entry_b", pipe_code="second", main_pipe="second"),
                },
                "several of its bundles declare a main_pipe: 'a.mthds' declares 'first', 'b/b.mthds' declares 'second'",
            ),
            (
                {
                    "METHODS.toml": _manifest(main_pipe=None, exports={}),
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first"),
                },
                (
                    "declares no main_pipe, so the method has no pipe to start at. Declare main_pipe under [package], or name the pipe to run. "
                    "Its bundles: 'a.mthds'."
                ),
            ),
            (
                {
                    "METHODS.toml": _manifest(main_pipe="missing", exports={"entry_a": ["missing"]}),
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first"),
                },
                "declares the main_pipe 'missing', exported by 'entry_a', which none of its bundles defines in that domain: 'a.mthds'.",
            ),
            (
                {"notes.md": "# Notes\n"},
                "holds no .mthds bundle, so it has no pipe to start at",
            ),
        ],
        ids=["no_main_pipe", "several_main_pipes", "manifest_without_main_pipe", "manifest_main_pipe_undefined", "no_bundle"],
    )
    def test_a_method_with_no_single_entry_is_refused_naming_its_bundles_by_tree_path(
        self, tmp_path: Path, files: dict[str, str], expected: str
    ) -> None:
        _write(directory=tmp_path, files=files)

        with pytest.raises(MethodEntryError) as exc_info:
            select_method_entry(tree=list_method_tree(tmp_path))

        assert expected in exc_info.value.message
        assert exc_info.value.to_error_report().error_domain == "input"

    def test_a_manifest_that_does_not_validate_is_an_entry_refusal(self, tmp_path: Path) -> None:
        """A manifest the lister can read but the standard refuses, here one with no address, gives no entry."""
        _write(
            directory=tmp_path,
            files={"METHODS.toml": '[package]\nversion = "1.0.0"\n', "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first")},
        )

        with pytest.raises(MethodEntryError, match=r"The METHODS\.toml of the method at .* cannot be read"):
            select_method_entry(tree=list_method_tree(tmp_path))
