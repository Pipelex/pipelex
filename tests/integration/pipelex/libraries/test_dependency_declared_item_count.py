from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.core.pipes.exceptions import DeclaredItemCountLimitError
from pipelex.interpreter_hub import get_library_manager
from pipelex.mthds_parsing.parser import MthdsParser
from tests.integration.pipelex.libraries.cases import ProbePackageCases
from tests.integration.pipelex.libraries.installed_packages import isolate_installed_methods, vendor_probe

# The probe package exporting a pipe that produces five texts, beside its unreachable `orphan` declaring far more, which
# no load builds.
_DECLARING_MANIFEST = ProbePackageCases.MANIFEST_EXPORTING_EVERYTHING.replace(
    'pipes = ["entry", "helper"]', 'pipes = ["entry", "helper", "make_five"]'
)
_DECLARING_BUNDLE = (
    ProbePackageCases.DEP_BUNDLE.replace('output      = "Text"\nmodel', 'output      = "Text[900]"\nmodel')
    + """
[pipe.make_five]
type        = "PipeLLM"
description = "Make five texts"
inputs      = { data = "Text" }
output      = "Text[5]"
prompt      = "Five texts about $data"
"""
)


def _load_consumer_with_the_package(*, tmp_path: Path, mocker: MockerFixture) -> None:
    """Load the probe's consumer, whose package ships beside it, into a fresh library, then tear it down."""
    isolate_installed_methods(mocker=mocker, root=tmp_path)
    methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods", manifest=_DECLARING_MANIFEST, bundle=_DECLARING_BUNDLE)
    library_manager = get_library_manager()
    library_id, _library = library_manager.open_library()
    try:
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=ProbePackageCases.CONSUMER_BUNDLE)
        library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint], methods_dirs=[methods_dir])
    finally:
        library_manager.teardown(library_id=library_id)


class TestDependencyDeclaredItemCount:
    def test_a_dependency_pipe_within_the_maximum_loads(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count", 5)
        _load_consumer_with_the_package(tmp_path=tmp_path, mocker=mocker)

    def test_a_dependency_pipe_past_the_maximum_is_refused_before_it_is_built(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A package's pipes the load builds are held to the maximum in force, as the main crate's are."""
        build_spy = mocker.spy(get_library_manager().__class__, "_ensure_declared_item_counts_allowed")

        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count", 4)
        with pytest.raises(PipelexError) as exc_info:
            _load_consumer_with_the_package(tmp_path=tmp_path, mocker=mocker)

        refusal = exc_info.value if isinstance(exc_info.value, DeclaredItemCountLimitError) else exc_info.value.__cause__
        assert isinstance(refusal, DeclaredItemCountLimitError), repr(exc_info.value)
        assert refusal.count == 5
        assert refusal.limit == 4
        assert refusal.slot == "the output of the pipe 'make_five'"
        # The unreachable orphan, declaring 900, is never what refuses the load: only the pipes the load builds are checked.
        checked_refs = {pipe_ref for call in build_spy.call_args_list for pipe_ref in call.kwargs["pipes"]}
        assert not any(pipe_ref.endswith("orphan") for pipe_ref in checked_refs)
