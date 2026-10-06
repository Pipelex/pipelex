"""A bundle of a dependency package that does not parse refuses the load, named by the package's address.

The bundles of a package the consumer calls by address load with it, and one that does not parse is a fault the
caller can see and report: a shipped package is the caller's own content, and a fetched or installed package's author
needs to learn the package is broken, not that it lacks the pipe called. The refusal is the parser's verdict, each
item's `source` the package's address and the bundle's path inside it, and nothing in it names a path on the host.

The packages are invented; every test isolates the installed store, and none reaches the network.
"""

import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import DisclosureMode
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.libraries.installed_packages import install_probe_globally, isolate_installed_methods, vendor_probe
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData

PROBE_ALIAS = ProbePackageTestData.DEP_ALIAS

# The probe package's bundle, made unparsable as TOML and as a blueprint.
UNPARSABLE_BUNDLES: dict[str, str] = {
    "toml syntax": 'domain = "probe_dep"\n\n[pipe.entry\ntype = "PipeLLM"\n',
    "invalid blueprint": ProbePackageTestData.DEP_BUNDLE.replace(
        'domain      = "probe_dep"', 'domain      = "probe_dep"\nmain_pipe   = "Not A Pipe Code!"'
    ),
}


def _assert_names_no_host_path(*, verdict: ValidateBundleError, tmp_path: Path) -> None:
    strict_dump = json.dumps(verdict.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT))
    for host_path in (str(tmp_path), str(tmp_path.resolve())):
        assert host_path not in strict_dump


class TestUnparsableDependencyBundle:
    @pytest.mark.parametrize("broken", list(UNPARSABLE_BUNDLES))
    def test_a_shipped_bundle_that_does_not_parse_refuses_the_load(self, tmp_path: Path, mocker: MockerFixture, broken: str) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods", bundle=UNPARSABLE_BUNDLES[broken])

        with pytest.raises(ValidateBundleError) as exc_info:
            acquire_library(library_id="", mthds_contents=[ProbePackageTestData.CONSUMER_BUNDLE], methods_dirs=[methods_dir])

        verdict = exc_info.value
        items = verdict.to_error_report().validation_errors or []
        assert items, verdict.message
        assert {item.source for item in items} == {f"{PROBE_ALIAS}/probe_dep.mthds"}
        assert PROBE_ALIAS in verdict.message
        _assert_names_no_host_path(verdict=verdict, tmp_path=tmp_path)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_installed_bundle_that_does_not_parse_refuses_the_load(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A fetched or installed package's author gets the same report: the parse failure, never a pipe the package lacks."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe_globally(root=tmp_path, bundle=UNPARSABLE_BUNDLES["toml syntax"])

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[ProbePackageTestData.CONSUMER_BUNDLE])

        verdict = exc_info.value
        items = verdict.to_error_report().validation_errors or []
        assert [(item.source, item.line) for item in items] == [(f"{PROBE_ALIAS}/probe_dep.mthds", 3)]
        _assert_names_no_host_path(verdict=verdict, tmp_path=tmp_path)
