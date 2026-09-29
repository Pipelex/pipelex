"""A consumer's structure field typed by an installed method package's concept resolves to that package's class.

The forward reference a consumer's generated class holds names the dependency's class, which the main path's
concept stage used to leave out of its namespace, so the consumer's class loaded "not fully defined".
"""

from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_concept_library, get_library_manager, scoped_current_library
from tests.integration.pipelex.libraries.test_data import InstalledNotesPackageTestData


def _write_consumer_and_its_dependency(*, root: Path) -> Path:
    """Install the notes package under `.mthds/methods/` beside the consumer's bundle, and return the consumer's bundle file."""
    dep_dir = root / ".mthds" / "methods" / InstalledNotesPackageTestData.METHOD_NAME
    dep_dir.mkdir(parents=True)
    (dep_dir / "METHODS.toml").write_text(InstalledNotesPackageTestData.DEP_MANIFEST, encoding="utf-8")
    (dep_dir / "invented_notes.mthds").write_text(InstalledNotesPackageTestData.DEP_BUNDLE, encoding="utf-8")
    consumer_bundle_file = root / "invented_consumer.mthds"
    consumer_bundle_file.write_text(InstalledNotesPackageTestData.CONSUMER_BUNDLE, encoding="utf-8")
    return consumer_bundle_file


class TestDependencyConceptFieldRefs:
    def test_consumer_field_typed_by_a_dependency_concept_is_fully_defined(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The consumer's `Digest` resolves its field to the dependency's `Note`, and the dependency's `NoteSearch` its list."""
        mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", tmp_path / "global-methods")
        mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)
        consumer_bundle_file = _write_consumer_and_its_dependency(root=tmp_path)
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=[consumer_bundle_file])

            assert InstalledNotesPackageTestData.DEP_ALIAS in library.dependency_libraries
            with scoped_current_library(library_id=library_id):
                concept_library = get_concept_library()
                digest_class = concept_library.get_structure_class(concept=concept_library.get_required_concept("invented_consumer.Digest"))
                note_search_class = concept_library.get_structure_class(
                    concept=concept_library.get_required_concept(f"{InstalledNotesPackageTestData.DEP_ALIAS}->invented_notes.NoteSearch")
                )

                digest = digest_class.model_validate({"note": {"title": "Invented note one"}, "summary": "It says one thing"})
                note_search = note_search_class.model_validate({"notes": [{"title": "Invented note one"}]})
        finally:
            library_manager.teardown(library_id=library_id)

        assert digest.model_dump()["note"] == {"title": "Invented note one"}
        assert note_search.model_dump()["notes"] == [{"title": "Invented note one"}]
