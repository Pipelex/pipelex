"""A binding step walks a dependency package's concept through the package's own definitions, from the consumer and from the package.

A package's concepts reach the consumer's library only under the package's alias (`alias->domain.Code`), while each one reports
the plain `domain.Code` its package declares. So a binding whose root holds a package's concept, the output of one of its pipes in
a consumer's sequence or an input of the package's own sequence, must start its walk from the aliased key, and follow the package's
own fields from there, never a consumer concept spelled the same. The packages are invented and installed under a temporary
`.mthds/methods/`.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.library import Library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.libraries.installed_packages import install_package, isolate_installed_methods, write_consumer
from tests.integration.pipelex.libraries.test_data import LedgerPackageTestData

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

LEDGER_ALIAS = LedgerPackageTestData.DEP_ALIAS


def _derived_concept_refs(*, library: Library, pipe_key: str) -> list[str]:
    """The concepts the binding steps of the sequence held under `pipe_key` derive, in step order."""
    sequence = library.pipe_library.get_required_pipe(pipe_code=pipe_key)
    assert isinstance(sequence, PipeSequence)
    flow = sequence.build_typed_flow()
    return [flow.binding_specs[step_index].concept.concept_ref for step_index in sorted(flow.binding_specs)]


def _install_ledger(*, root: Path) -> None:
    install_package(
        root=root,
        method_name=LedgerPackageTestData.METHOD_NAME,
        manifest=LedgerPackageTestData.DEP_MANIFEST,
        bundles={"invented_ledger.mthds": LedgerPackageTestData.DEP_BUNDLE},
    )


class TestDependencyBindingSteps:
    @pytest.mark.parametrize(
        "consumer_bundles",
        [
            pytest.param({"books.mthds": LedgerPackageTestData.CONSUMER_BUNDLE}, id="the-package-s-concepts-alone"),
            pytest.param(
                {"books.mthds": LedgerPackageTestData.CONSUMER_BUNDLE, "own_ledger.mthds": LedgerPackageTestData.CONSUMER_NAMESAKE_BUNDLE},
                id="beside-consumer-concepts-of-the-same-spelling",
            ),
        ],
    )
    def test_bindings_over_a_package_concept_derive_from_the_package_s_structure(
        self, tmp_path: Path, mocker: MockerFixture, consumer_bundles: dict[str, str]
    ) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_ledger(root=tmp_path)
        consumer_files = write_consumer(root=tmp_path, bundles=consumer_bundles)
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            with scoped_current_library(library_id=library_id):
                derived: dict[str, list[str]] = {}
                for pipe_key in ("invented_books.check_invoice", f"{LEDGER_ALIAS}->invented_ledger.read_invoice"):
                    derived[pipe_key] = _derived_concept_refs(library=library, pipe_key=pipe_key)
        finally:
            library_manager.teardown(library_id=library_id)

        assert derived == {
            "invented_books.check_invoice": ["native.Text", "native.Number"],
            f"{LEDGER_ALIAS}->invented_ledger.read_invoice": ["native.Text", "native.Number"],
        }

    def test_consumer_concepts_beside_the_package_s_keep_their_own_structures(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The consumer's namesakes walk their own fields, and the consumer's field typed with the package's alias walks the package's."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_ledger(root=tmp_path)
        consumer_files = write_consumer(
            root=tmp_path,
            bundles={"books.mthds": LedgerPackageTestData.CONSUMER_BUNDLE, "own_ledger.mthds": LedgerPackageTestData.CONSUMER_NAMESAKE_BUNDLE},
        )
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            with scoped_current_library(library_id=library_id):
                own_invoice_refs = _derived_concept_refs(library=library, pipe_key="invented_ledger.read_own_invoice")
                filing_refs = _derived_concept_refs(library=library, pipe_key="invented_ledger.read_filing")
        finally:
            library_manager.teardown(library_id=library_id)

        assert own_invoice_refs == ["native.Number", "native.Text"]
        assert filing_refs == ["native.Text"]

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize("pipe_code", ["check_invoice", "relay_invoice"])
    async def test_a_binding_over_a_package_concept_runs(self, tmp_path: Path, mocker: MockerFixture, pipe_code: str) -> None:
        """Run live: the consumer's own bindings, and the package's sequence rebuilding its flow against the consumer's library."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_ledger(root=tmp_path)
        # The consumer's own directory, so the library directory holds the consumer's bundle alone and the package is found
        # installed under `.mthds/methods/` above it, never loaded as one of the consumer's bundles.
        consumer_dir = tmp_path / "books"
        consumer_dir.mkdir()
        write_consumer(root=consumer_dir, bundles={"books.mthds": LedgerPackageTestData.CONSUMER_BUNDLE})
        # What the run's library held when it was torn down: the packages it loaded, and whether it held the package's
        # `Invoice` under its plain spelling, which only a consumer bundle would put there.
        library_states: list[tuple[set[str], bool]] = []
        original_teardown = Library.teardown

        def recording_teardown(library: Library) -> None:
            library_states.append(
                (set(library.dependency_libraries), library.concept_library.is_concept_exists(concept_ref="invented_ledger.Invoice"))
            )
            original_teardown(library)

        mocker.patch.object(Library, "teardown", autospec=True, side_effect=recording_teardown)

        inputs: PipelineInputs = {"amount": {"concept": "native.Number", "content": {"number": 1250.5}}, "sender": "Atelier Morvan"}
        result = await PipelexMTHDSProtocol(library_dirs=[str(consumer_dir)], pipe_run_mode=PipeRunMode.LIVE).execute(
            pipe_code=f"invented_books.{pipe_code}",
            inputs=inputs,
        )

        assert ({LEDGER_ALIAS}, False) in library_states
        assert result.pipe_output.main_stuff.as_text.text == "Atelier Morvan: 1250.5 euros"
