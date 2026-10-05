"""A dependency package's own in-body refs are qualified to its own domain, under the alias it is loaded as.

The dependency loader builds its own crate and its own child library — it does not go through
`load_from_crate` — so it is a second, independent crate-to-pipes path, and the qualification pass
has to be wired into both. A miss on this one is invisible to every test that loads a single-domain
library, where a bare ref and an owner-qualified ref name the same pipe — which is why this module
exists.

The ref stored on the built pipe is `alias->domain.code`, the key the consumer's library holds the
dependency's pipe under, so every reader of the ref reaches the package's own pipe and never a
consumer pipe of the same `domain.code`. That the ref resolves end to end, at load and in a dry run,
is pinned by `tests/integration/pipelex/libraries/test_dependency_pipe_scope.py`.
"""

from pathlib import Path

from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager import LibraryManager

# A dependency whose sequence names its own helper by bare code — the shape a package is authored in.
DEP_WITH_BARE_REF_MTHDS = """\
domain = "charts_dep"
description = "Dependency whose entry pipe calls its own helper by bare code"

[pipe.render_chart]
type = "PipeSequence"
description = "Render a chart."
inputs = { data = "Text" }
output = "Text"
steps = [{ pipe = "prepare_series", result = "series" }]

[pipe.prepare_series]
type = "PipeLLM"
description = "Prepare the series."
inputs = { data = "Text" }
output = "Text"
prompt = "Prepare $data"
"""

# A second domain in the same package, declaring the SAME helper code. Without this the test could
# not tell owner-domain qualification from the crate-wide search it replaced.
DEP_SIBLING_DOMAIN_MTHDS = """\
domain = "tables_dep"
description = "A sibling domain declaring the same helper code"

[pipe.prepare_series]
type = "PipeLLM"
description = "The tables domain's own preparer."
inputs = { data = "Text" }
output = "Text"
prompt = "Prepare $data differently"
"""


class TestDependencyRefQualification:
    def _load_dependency(self, *, mocker: MockerFixture, tmp_path: Path, file_contents: list[tuple[str, str]]):
        library_manager = get_library_manager()
        library = LibraryFactory.make_empty()
        mocker.patch.object(library_manager, "get_current_library", return_value=library)

        mthds_files: list[Path] = []
        for file_name, content in file_contents:
            mthds_file = tmp_path / file_name
            mthds_file.write_text(content, encoding="utf-8")
            mthds_files.append(mthds_file)

        manager = LibraryManager()
        manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            library=library,
            package_address="github.com/org/charts-dep",
            resolved_dep=ResolvedDependency(
                alias="charts_dep",
                address="github.com/org/charts-dep",
                manifest=MethodsManifest(
                    address="github.com/org/charts-dep",
                    version="1.0.0",
                    description="A charting dep package",
                ),
                package_root=tmp_path,
                mthds_files=mthds_files,
                exported_pipe_codes=None,
            ),
        )
        return library

    def test_dependency_in_body_ref_is_qualified_to_its_own_domain(self, mocker: MockerFixture, tmp_path: Path):
        library = self._load_dependency(
            mocker=mocker,
            tmp_path=tmp_path,
            file_contents=[("charts.mthds", DEP_WITH_BARE_REF_MTHDS), ("tables.mthds", DEP_SIBLING_DOMAIN_MTHDS)],
        )

        child_library = library.dependency_libraries["charts_dep"]
        render_chart = child_library.pipe_library.get_required_pipe("charts_dep.render_chart")

        # Its own domain's helper — not the sibling's, and not a bare code the strict lookup would
        # never resolve — under the alias, the key the consumer's library holds it under.
        assert render_chart.pipe_dependencies() == {"charts_dep->charts_dep.prepare_series"}
        assert library.pipe_library.get_required_pipe(pipe_code="charts_dep->charts_dep.prepare_series").domain_code == "charts_dep"
