"""Load-path integration for fetch-on-miss: an address-referenced dependency missing from the
installed methods is fetched (mocked to a local fixture package), installed into the (redirected)
global methods directory, and loaded so pipe resolution proceeds — and a miss with fetch disabled
raises the diagnostic instead of passing silently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.package.manifest.parser import parse_methods_toml

from pipelex.cli.installed_methods import PROVENANCE_FILENAME
from pipelex.interpreter_hub import get_library_manager
from pipelex.methods.exceptions import MethodFetchDisabledError
from pipelex.methods.fetching import FetchedMethodPackage
from pipelex.methods.method_ref import parse_method_ref
from pipelex.mthds_parsing.parser import MthdsParser

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

DEP_ALIAS = "github.com/pipelex-tests/fom-dep-methods/scoring"
COMMIT_SHA = "c" * 40

DEP_MANIFEST = """\
[package]
name = "scoring"
address = "github.com/pipelex-tests/fom-dep-methods"
version = "0.1.0"
description = "Scoring dependency for the fetch-on-miss load test"

[exports.fom_scoring]
pipes = ["fom_compute_score"]
"""

DEP_BUNDLE = """\
domain    = "fom_scoring"
main_pipe = "fom_compute_score"

[concept.FomWeightedScore]
description = "A weighted score result"

[pipe.fom_compute_score]
type        = "PipeLLM"
description = "Compute a weighted score"
output      = "FomWeightedScore"
prompt      = "Compute a weighted score for: {{ item }}"

[pipe.fom_compute_score.inputs]
item = "Text"
"""

CONSUMER_BUNDLE = """\
domain = "fom_consumer"

[concept.FomAnalysisResult]
description = "Analysis result combining scoring"

[pipe.fom_analyze_item]
type = "PipeSequence"
description = "Analyze an item using the scoring dependency"
output = "FomAnalysisResult"
steps = [
  { pipe = "__DEP_ALIAS__->fom_scoring.fom_compute_score" },
  { pipe = "fom_summarize" },
]

[pipe.fom_analyze_item.inputs]
item = "Text"

[pipe.fom_summarize]
type        = "PipeLLM"
description = "Summarize the analysis"
output      = "FomAnalysisResult"
prompt      = "Summarize the analysis for: {{ item }}"

[pipe.fom_summarize.inputs]
item = "Text"
""".replace("__DEP_ALIAS__", DEP_ALIAS)


@pytest.fixture(name="global_methods_dir")
def global_methods_dir_fixture(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point the global and project methods directories at empty tmp locations."""
    global_dir = tmp_path / "global-methods"
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", global_dir)
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    return global_dir


def _make_fetched_dep(tmp_path: Path) -> FetchedMethodPackage:
    """Build the dependency package on disk and wrap it as a fetch result."""
    package_dir = tmp_path / "fetched-dep"
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(DEP_MANIFEST, encoding="utf-8")
    (package_dir / "scoring.mthds").write_text(DEP_BUNDLE, encoding="utf-8")
    return FetchedMethodPackage(
        ref=parse_method_ref(DEP_ALIAS),
        full_address=DEP_ALIAS,
        commit_sha=COMMIT_SHA,
        clone_dir=tmp_path,
        package_dir=package_dir,
        manifest=parse_methods_toml(DEP_MANIFEST),
    )


class TestAddressDependencyFetchOnMiss:
    def test_load_fetches_missing_dependency_and_resolution_proceeds(self, global_methods_dir: Path, tmp_path: Path, mocker: MockerFixture) -> None:
        """A missed address dependency is fetched, installed, and loaded — the aliased pipe resolves."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        fetched = _make_fetched_dep(tmp_path)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=fetched)

        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=CONSUMER_BUNDLE)
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

            assert {pipe.code for pipe in loaded_pipes} == {"fom_analyze_item", "fom_summarize"}
            assert DEP_ALIAS in library.dependency_libraries
            aliased_pipe = library.pipe_library.get_required_pipe(pipe_code=f"{DEP_ALIAS}->fom_scoring.fom_compute_score")
            assert aliased_pipe.code == "fom_compute_score"
            assert fetch_mock.call_count == 1

            installed_dir = global_methods_dir / "scoring"
            assert (installed_dir / "scoring.mthds").is_file()
            assert (installed_dir / PROVENANCE_FILENAME).is_file()
        finally:
            library_manager.teardown(library_id=library_id)

    @pytest.mark.usefixtures("global_methods_dir")
    def test_load_miss_with_fetch_disabled_raises_the_diagnostic(self, mocker: MockerFixture) -> None:
        """With fetch-on-miss disabled, the former silent-miss warning is now a raised diagnostic."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package")

        library_manager = get_library_manager()
        library_id, _library = library_manager.open_library()
        try:
            blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=CONSUMER_BUNDLE)
            with pytest.raises(MethodFetchDisabledError) as exc_info:
                library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
        finally:
            library_manager.teardown(library_id=library_id)

        message = str(exc_info.value)
        assert DEP_ALIAS in message
        assert "fetch-on-miss is disabled" in message
        fetch_mock.assert_not_called()
