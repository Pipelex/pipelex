from pathlib import Path
from typing import Any

import pytest
from mthds.method_tree.lister import list_method_tree
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.errors.problem import ProblemView
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.pipeline.method_entry import read_method_candidates, select_method_entry, select_named_pipe
from pipelex.validation_error_types import PipeValidationErrorType


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
        ("files", "expected", "expected_code", "expected_params"),
        [
            (
                {
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe=None),
                    "b/b.mthds": _bundle(domain="entry_b", pipe_code="second", main_pipe=None),
                },
                "none of its bundles declares a main_pipe ('a.mthds', 'b/b.mthds')",
                CoreCode.REQUEST_PIPE_UNSPECIFIED,
                # With no main pipe declared anywhere, every pipe the method declares is one to choose from.
                {"candidates": ["entry_a.first", "entry_b.second"]},
            ),
            (
                {
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first"),
                    "b/b.mthds": _bundle(domain="entry_b", pipe_code="second", main_pipe="second"),
                },
                "several of its bundles declare a main_pipe: 'a.mthds' declares 'first', 'b/b.mthds' declares 'second'",
                CoreCode.REQUEST_PIPE_UNSPECIFIED,
                {"candidates": ["entry_a.first", "entry_b.second"]},
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
                CoreCode.REQUEST_PIPE_UNSPECIFIED,
                {"candidates": ["entry_a.first"]},
            ),
            (
                {
                    "METHODS.toml": _manifest(main_pipe="missing", exports={"entry_a": ["missing"]}),
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first"),
                },
                "declares the main_pipe 'missing', exported by 'entry_a', which none of its bundles defines in that domain: 'a.mthds'.",
                CoreCode.METHOD_PIPE_UNRESOLVED,
                # The declaration holding the reference stands for the pipe, and no declared pipe is near the one missing.
                {"pipe": "main_pipe", "missing": "missing", "candidates": []},
            ),
            (
                {
                    "METHODS.toml": _manifest(main_pipe="first", exports={"entry_a": ["first"], "entry_b": ["first"]}),
                    "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe=None),
                    "b/b.mthds": _bundle(domain="entry_b", pipe_code="first", main_pipe=None),
                },
                "declares the main_pipe 'first', which several of its bundles define: 'a.mthds' in domain 'entry_a', 'b/b.mthds' in domain 'entry_b'",
                CoreCode.METHOD_REF_AMBIGUOUS,
                {"ref": "first", "candidates": ["entry_a.first", "entry_b.first"]},
            ),
            (
                {"notes.md": "# Notes\n"},
                "holds no .mthds bundle, so it has no pipe to start at",
                CoreCode.METHOD_INVALID,
                None,
            ),
        ],
        ids=[
            "no_main_pipe",
            "several_main_pipes",
            "manifest_without_main_pipe",
            "manifest_main_pipe_undefined",
            "manifest_main_pipe_twice",
            "no_bundle",
        ],
    )
    def test_a_method_with_no_single_entry_is_refused_naming_its_bundles_by_tree_path(
        self, tmp_path: Path, files: dict[str, str], expected: str, expected_code: CoreCode, expected_params: dict[str, Any] | None
    ) -> None:
        _write(directory=tmp_path, files=files)

        with pytest.raises(MethodEntryError) as exc_info:
            select_method_entry(tree=list_method_tree(tmp_path))

        assert expected in exc_info.value.message
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == expected_code
        assert problem.domain != ProblemDomain.OPERATOR
        # The refusal gives every parameter its code requires: the pipes to choose from, the missing one, the ambiguous one.
        assert problem.to_wire().get("params") == expected_params

    def test_a_manifest_that_does_not_validate_is_an_entry_refusal(self, tmp_path: Path) -> None:
        """A manifest the lister can read but the standard refuses, here one with no address, gives no entry."""
        _write(
            directory=tmp_path,
            files={"METHODS.toml": '[package]\nversion = "1.0.0"\n', "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe="first")},
        )

        with pytest.raises(MethodEntryError, match=r"The METHODS\.toml of the method at .* cannot be read"):
            select_method_entry(tree=list_method_tree(tmp_path))

    def test_a_bundle_whose_pipes_do_not_validate_still_says_where_its_method_starts(self, tmp_path: Path) -> None:
        """The rule reads the declarations alone, so `fix` can still reach a method whose pipes it has to repair."""
        _write(
            directory=tmp_path,
            files={
                "broken.mthds": 'domain = "entry_broken"\nmain_pipe = "first"\n\n[pipe.first]\ntype = "PipeNope"\n',
                "steps.mthds": _bundle(domain="entry_steps", pipe_code="extract", main_pipe=None),
            },
        )

        entry = select_method_entry(tree=list_method_tree(tmp_path))

        assert entry.pipe_ref == "entry_broken.first"
        assert entry.tree_path == "broken.mthds"

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ('domain = \nmain_pipe = "first"\n', "TOML syntax error at line 1"),
            ('domain = 3\nmain_pipe = "first"\n', "Domain code '3' is not a valid domain code"),
            ('domain = "entry_a"\nmain_pipe = ["first"]\n', "Input should be a valid string"),
            ('domain = "entry_a"\npipe = 3\n', "Input should be a valid dictionary"),
        ],
        ids=["not_toml", "domain_not_a_string", "main_pipe_not_a_string", "pipe_not_a_table"],
    )
    def test_a_bundle_whose_declarations_cannot_be_read_is_refused_as_its_parse_refuses_it(self, tmp_path: Path, content: str, expected: str) -> None:
        _write(directory=tmp_path, files={"a.mthds": content})

        with pytest.raises(MthdsParserError) as exc_info:
            select_method_entry(tree=list_method_tree(tmp_path))

        assert expected in str(exc_info.value)

    @pytest.mark.parametrize("main_pipe", ["dom.pipe", "camelCase", ""], ids=["qualified_ref", "camel_case", "empty_string"])
    def test_a_main_pipe_that_is_no_pipe_code_is_refused_at_entry_selection_naming_its_bundle(self, tmp_path: Path, main_pipe: str) -> None:
        """The bundle's parse holds `main_pipe` to the pipe code syntax, and so does the rule: an empty string declares no pipe and is no absence."""
        _write(
            directory=tmp_path,
            files={
                "a.mthds": _bundle(domain="entry_a", pipe_code="first", main_pipe=None).replace(
                    "\n\n[pipe.", f'\nmain_pipe = "{main_pipe}"\n\n[pipe.', 1
                ),
                "b.mthds": _bundle(domain="entry_b", pipe_code="second", main_pipe="second"),
            },
        )

        with pytest.raises(MthdsParserError) as exc_info:
            select_method_entry(tree=list_method_tree(tmp_path))

        assert f"Invalid main pipe syntax '{main_pipe}'" in exc_info.value.message
        items = exc_info.value.validation_errors or []
        assert [item.error_type for item in items] == [PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX]
        assert [Path(item.source or "").name for item in items] == ["a.mthds"]

    @pytest.mark.parametrize(
        ("pipe_ref", "expected_tree_path", "expected_pipe_ref"),
        [
            ("extract", "steps/extract.mthds", "entry_steps.extract"),
            ("entry_report.summarize", "report.mthds", "entry_report.summarize"),
            ("entry_steps.summarize", "steps/extract.mthds", "entry_steps.summarize"),
        ],
        ids=["bare_code", "qualified_ref", "qualified_ref_of_a_shared_code"],
    )
    def test_a_named_pipe_is_found_in_the_bundle_defining_it(
        self, tmp_path: Path, pipe_ref: str, expected_tree_path: str, expected_pipe_ref: str
    ) -> None:
        _write(
            directory=tmp_path,
            files={
                "steps/extract.mthds": _bundle(domain="entry_steps", pipe_code="extract", main_pipe=None)
                + _bundle(domain="entry_steps", pipe_code="summarize", main_pipe=None).split("\n", 2)[2],
                "report.mthds": _bundle(domain="entry_report", pipe_code="summarize", main_pipe="summarize"),
            },
        )
        tree = list_method_tree(tmp_path)

        entry = select_named_pipe(candidates=read_method_candidates(tree=tree), pipe_ref=pipe_ref, method_label="here")

        assert entry.tree_path == expected_tree_path
        assert entry.pipe_ref == expected_pipe_ref

    @pytest.mark.parametrize(
        ("pipe_ref", "expected"),
        [
            ("missing", "No bundle of the method here defines the pipe 'missing'. Its bundles: 'report.mthds', 'steps/extract.mthds'."),
            (
                "summarize",
                (
                    "Several bundles of the method here define the pipe 'summarize': 'report.mthds' in domain 'entry_report', "
                    "'steps/extract.mthds' in domain 'entry_steps'. Name the pipe as domain.pipe_code."
                ),
            ),
            ("scoring->scoring.compute", "The pipe 'scoring->scoring.compute' belongs to a package the method here depends on"),
            ("entry_steps..summarize", "'entry_steps..summarize' does not name a pipe of the method here"),
        ],
        ids=["undefined", "ambiguous_bare_code", "dependency_pipe", "not_a_pipe_ref"],
    )
    def test_a_named_pipe_no_single_bundle_defines_is_refused(self, tmp_path: Path, pipe_ref: str, expected: str) -> None:
        _write(
            directory=tmp_path,
            files={
                "steps/extract.mthds": _bundle(domain="entry_steps", pipe_code="summarize", main_pipe=None),
                "report.mthds": _bundle(domain="entry_report", pipe_code="summarize", main_pipe="summarize"),
            },
        )
        tree = list_method_tree(tmp_path)

        with pytest.raises(MethodEntryError) as exc_info:
            select_named_pipe(candidates=read_method_candidates(tree=tree), pipe_ref=pipe_ref, method_label="here")

        assert expected in exc_info.value.message
