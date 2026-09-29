"""A dependency package's structure classes go through the same concept stage as the main package's.

A concept whose structure holds another concept gets a generated class with a forward reference to the other
concept's class, which the loader resolves after loading the concepts. The dependency loader used to skip that
step, and the concept-cycle check with it: a dependency concept holding a list of another of its concepts loaded
"not fully defined" and failed at first use, and a dependency whose concepts formed a cycle loaded without complaint.
"""

from pathlib import Path

import pytest
from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest

from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.library_manager import LibraryManager
from pipelex.system.registries.class_registry_access import get_class_registry

DEP_ALIAS = "invented_notes_dep"
DEP_ADDRESS = "github.com/invented/notes-lib"

# `NoteSearch` holds a list of `Note`, a forward reference the concept stage must resolve.
DEP_NOTES_MTHDS = """\
domain = "invented_notes"
description = "An invented notes library"

[concept.Note]
description = "One invented note"

[concept.Note.structure]
title = { type = "text", description = "The note's title", required = true }

[concept.NoteSearch]
description = "The notes a search found"

[concept.NoteSearch.structure]
notes = { type = "list", item_type = "concept", item_concept_ref = "invented_notes.Note", description = "The notes found", required = true }
"""

# The same two concepts, with `Note` pointing back at `NoteSearch`: a cycle the main path refuses.
DEP_CYCLIC_NOTES_MTHDS = """\
domain = "invented_notes"
description = "An invented notes library whose concepts form a cycle"

[concept.Note]
description = "One invented note, which points back at the search that found it"

[concept.Note.structure]
title = { type = "text", description = "The note's title", required = true }
found_by = { type = "concept", concept_ref = "invented_notes.NoteSearch", description = "The search that found it" }

[concept.NoteSearch]
description = "The notes a search found"

[concept.NoteSearch.structure]
notes = { type = "list", item_type = "concept", item_concept_ref = "invented_notes.Note", description = "The notes found", required = true }
"""

# `Note` holds a concept of the package's own dependency, which a dependency load never loads.
DEP_WITH_ITS_OWN_DEPENDENCY_MTHDS = """\
domain = "invented_notes"
description = "An invented notes library that depends on another package"

[concept.Note]
description = "One invented note, citing a source from another package"

[concept.Note.structure]
title = { type = "text", description = "The note's title", required = true }
source = { type = "concept", concept_ref = "github.com/invented/sources-lib/sources->invented_sources.Source", description = "Where it came from" }

[concept.Tag]
description = "A tag"

[concept.Tag.structure]
label = { type = "text", description = "The tag's label", required = true }
"""


def _get_library_manager() -> LibraryManager:
    """The hub's manager, whose libraries the class registry resolves against, so each test's classes die with its library."""
    library_manager = get_library_manager()
    assert isinstance(library_manager, LibraryManager)
    return library_manager


def _make_resolved_dep(*, tmp_path: Path, mthds_content: str) -> ResolvedDependency:
    mthds_file = tmp_path / "notes.mthds"
    mthds_file.write_text(mthds_content, encoding="utf-8")
    return ResolvedDependency(
        alias=DEP_ALIAS,
        address=DEP_ADDRESS,
        manifest=MethodsManifest(address=DEP_ADDRESS, version="1.0.0", description="An invented notes library"),
        package_root=tmp_path,
        mthds_files=[mthds_file],
        # None => no export filter, every pipe is public.
        exported_pipe_codes=None,
    )


class TestDependencyStructureClasses:
    def test_a_concept_holding_a_list_of_another_is_fully_defined(self, tmp_path: Path) -> None:
        """A dependency's `NoteSearch` resolves its forward reference to `Note`, so it validates and renders a schema."""
        library_manager = _get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                    library=library,
                    resolved_dep=_make_resolved_dep(tmp_path=tmp_path, mthds_content=DEP_NOTES_MTHDS),
                    package_address=DEP_ADDRESS,
                )
                note_search_concept = library.dependency_libraries[DEP_ALIAS].concept_library.get_required_concept(
                    concept_ref="invented_notes.NoteSearch"
                )
                note_search_class = get_class_registry().get_required_base_model(name=note_search_concept.structure_class_name)

                note_search = note_search_class.model_validate({"notes": [{"title": "Invented note one"}]})
                schema = note_search_class.model_json_schema()
        finally:
            library_manager.teardown(library_id=library_id)

        assert note_search_class.__pydantic_complete__
        assert note_search.model_dump()["notes"] == [{"title": "Invented note one"}]
        assert "notes" in schema["properties"]

    def test_concepts_forming_a_cycle_are_refused(self, tmp_path: Path) -> None:
        """A dependency whose concepts form a cycle is refused with the message the main path gives."""
        library_manager = _get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id), pytest.raises(LibraryLoadingError, match=r"Cycle detected in concept references"):
                library_manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                    library=library,
                    resolved_dep=_make_resolved_dep(tmp_path=tmp_path, mthds_content=DEP_CYCLIC_NOTES_MTHDS),
                    package_address=DEP_ADDRESS,
                )
        finally:
            library_manager.teardown(library_id=library_id)

    def test_a_concept_naming_its_own_dependency_does_not_refuse_the_load(self, tmp_path: Path) -> None:
        """A dependency's own dependencies are never loaded, so a concept naming one of theirs is left for first use, not refused."""
        library_manager = _get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                    library=library,
                    resolved_dep=_make_resolved_dep(tmp_path=tmp_path, mthds_content=DEP_WITH_ITS_OWN_DEPENDENCY_MTHDS),
                    package_address=DEP_ADDRESS,
                )
                tag_concept = library.dependency_libraries[DEP_ALIAS].concept_library.get_required_concept(concept_ref="invented_notes.Tag")
                tag_class = get_class_registry().get_required_base_model(name=tag_concept.structure_class_name)
                tag = tag_class.model_validate({"label": "Invented tag"})
        finally:
            library_manager.teardown(library_id=library_id)

        assert tag.model_dump() == {"label": "Invented tag"}
