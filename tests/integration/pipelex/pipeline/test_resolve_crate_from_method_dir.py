"""Integration: ``resolve_crate_from_method_dir``, the host-facing resolve core over a method's written tree.

Pins the contract the HTTP crate routes build on: a tree a host wrote out and holds resolves to the normalized crate
with each bundle named by its tree path, an invalid tree, one holding no bundle or one calling a package nothing shipped
raises the one shared ``ValidateBundleError``, and the library lifecycle honors the loaded-on-success /
torn-down-on-failure contract.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pipelex.methods.address_dependencies import ADDRESS_DEPENDENCY_REFUSAL_MARKER
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.resolve_bundle import resolve_crate_from_method_dir
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.pipeline.test_data import ResolveBundleTestData


@contextmanager
def _written_tree(*, destination: Path, files: dict[str, str]) -> Generator[Path, None, None]:
    """Write a tree out and hold it as written, as the API server does with the tree a request sends."""
    contents = {tree_path: content.encode("utf-8") for tree_path, content in files.items()}
    written = write_method_tree(contents=contents, destination=destination, expected_digest=digest_of_contents(contents))
    with WRITTEN_METHOD_TREES.holding(tree=written):
        yield destination


class TestResolveCrateFromMethodDir:
    def test_a_written_tree_resolves_with_bundles_named_by_tree_path(self, load_empty_library: Callable[[], str], tmp_path: Path):
        """Every bundle of the tree joins the crate under its tree path, and the library is left loaded and current."""
        load_empty_library()
        library_manager = get_library_manager()
        files = {
            "main.mthds": ResolveBundleTestData.MAIN_MTHDS,
            "steps/scoring.mthds": ResolveBundleTestData.STEPS_MTHDS,
            "README.md": "# Not a bundle\n",
        }
        with _written_tree(destination=tmp_path / "method", files=files) as method_dir:
            crate = resolve_crate_from_method_dir(method_dir=method_dir)
        library_id = get_current_library_id_or_none()
        try:
            assert crate.fingerprint
            assert crate.mthds_version == MTHDS_STANDARD_VERSION
            assert "pipeline.run_pipeline" in crate.pipes
            assert "pipeline.compute_score" in crate.pipes
            assert "native.Text" in crate.concepts, "referenced natives must be materialized into the normalized crate"
            assert crate.source_map.get("pipeline.run_pipeline") == "main.mthds"
            assert crate.source_map.get("pipeline.compute_score") == "steps/scoring.mthds"
            assert library_id is not None
        finally:
            clear_current_library()
            if library_id is not None:
                library_manager.teardown(library_id=library_id)

    @pytest.mark.parametrize(
        ("files", "expects_items"),
        [
            pytest.param({"broken.mthds": ResolveBundleTestData.INVALID_MTHDS}, True, id="invalid-bundle"),
            pytest.param({"notes.txt": "no bundle here"}, False, id="no-bundle"),
        ],
    )
    def test_a_tree_with_no_crate_raises_the_shared_verdict_and_tears_down(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
        tmp_path: Path,
        files: dict[str, str],
        expects_items: bool,
    ):
        """An invalid tree, or one holding no bundle, is the caller's verdict; the opened library is torn down."""
        load_empty_library()
        library_manager = get_library_manager()
        open_library_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        current_before = get_current_library_id_or_none()
        with _written_tree(destination=tmp_path / "method", files=files) as method_dir, pytest.raises(ValidateBundleError) as exc_info:
            resolve_crate_from_method_dir(method_dir=method_dir)

        if expects_items:
            validation_errors = exc_info.value.validation_error_items()
            assert validation_errors, "the shared builder must produce structured validation-error items"
            assert validation_errors[0].source == "broken.mthds"
            # Nothing of the verdict names the directory the host wrote the tree to, the operator's diagnostics included.
            report_text = str(exc_info.value.to_problem(view=ProblemView.OPERATOR).to_wire())
            assert str(tmp_path) not in report_text
            assert str(tmp_path.resolve()) not in report_text
        else:
            assert "holds no .mthds bundle" in exc_info.value.message
        opened_library_id, _ = open_library_spy.spy_return
        assert teardown_spy.call_args_list[-1].kwargs["library_id"] == opened_library_id
        assert get_current_library_id_or_none() == current_before

    def test_a_merge_error_names_the_bundles_by_their_tree_paths(self, load_empty_library: Callable[[], str], tmp_path: Path):
        """An error raised once the bundles parsed, such as one concept declared twice, names no directory of the host."""
        load_empty_library()
        files = {"first.mthds": ResolveBundleTestData.MAIN_MTHDS, "second.mthds": ResolveBundleTestData.MAIN_MTHDS}
        with _written_tree(destination=tmp_path / "method", files=files) as method_dir, pytest.raises(ValidateBundleError) as exc_info:
            resolve_crate_from_method_dir(method_dir=method_dir)

        assert "['first.mthds', 'second.mthds']" in exc_info.value.message
        report_text = str(exc_info.value.to_problem(view=ProblemView.OPERATOR).to_wire())
        assert str(tmp_path) not in report_text
        assert str(tmp_path.resolve()) not in report_text

    def test_an_address_dependency_nothing_shipped_is_refused_without_a_lookup_or_a_fetch(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
        tmp_path: Path,
    ):
        """A static resolution reads no method installed on the host and fetches nothing: it refuses the call."""
        load_empty_library()
        discovery = mocker.patch(
            "pipelex.libraries.library_manager.resolve_address_based_method",
            side_effect=AssertionError("a static resolution must not look up installed methods or fetch by address"),
        )
        files = {"host.mthds": ResolveBundleTestData.ADDRESS_DEPENDENCY_MTHDS}
        with _written_tree(destination=tmp_path / "method", files=files) as method_dir, pytest.raises(ValidateBundleError) as exc_info:
            resolve_crate_from_method_dir(method_dir=method_dir)

        discovery.assert_not_called()
        # The unresolved dependency `/v1/validate` reports, located on the pipe calling it, in the words of the contents
        # core's refusal, whose marker a hosted run tells it apart by.
        validation_errors = exc_info.value.validation_error_items()
        assert len(validation_errors) == 1, validation_errors
        item = validation_errors[0]
        assert item.error_type == PipeValidationErrorType.UNRESOLVED_PACKAGE_DEPENDENCY
        assert item.source == "host.mthds"
        assert f"{ADDRESS_DEPENDENCY_REFUSAL_MARKER} 'github.com/org/pkg'" in item.message
