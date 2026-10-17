"""Integration: ``resolve_crate_from_method_dir``, the host-facing resolve core over a method's written tree.

Pins the contract the HTTP crate routes build on: a tree a host wrote out and holds resolves to the normalized crate
with each bundle named by its tree path, an invalid tree or one holding no bundle raises the one shared
``ValidateBundleError``, and the library lifecycle honors the loaded-on-success / torn-down-on-failure contract.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.resolve_bundle import resolve_crate_from_method_dir
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
            validation_errors = exc_info.value.to_error_report().validation_errors or []
            assert validation_errors, "the shared builder must produce structured validation-error items"
            assert validation_errors[0].source == "broken.mthds"
        else:
            assert "holds no .mthds bundle" in exc_info.value.message
        opened_library_id, _ = open_library_spy.spy_return
        assert teardown_spy.call_args_list[-1].kwargs["library_id"] == opened_library_id
        assert get_current_library_id_or_none() == current_before
