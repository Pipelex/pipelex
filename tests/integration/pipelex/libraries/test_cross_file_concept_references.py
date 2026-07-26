"""Integration tests: same-domain concept references resolve across separate load batches.

These exercise the loader-level concept-reference check
(`validate_concept_references_in_blueprints`, called from `LibraryManager.load_from_blueprints`)
together with the pipe factory's library-aware same-domain concept guard. A concept declared in a
prior batch (e.g. a separate `load_from_blueprints` call, as a `-L` library directory produces)
must resolve when referenced by bare code from a later batch in the same domain.
"""

from collections.abc import Callable

import pytest

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.method_hub import get_library_manager

CONCEPT_MTHDS = """
domain = "crossref"
description = "Cross-reference domain"

[concept]
Summary = "A summary of a document"
"""

PIPE_BARE_REF_MTHDS = """
domain = "crossref"
description = "Cross-reference domain"

[pipe.make_summary]
type = "PipeLLM"
description = "Summarize a document"
inputs = { doc = "Text" }
output = "Summary"
model = "$quick-reasoning"
prompt = "Summarize $doc."
"""

PIPE_UNDECLARED_REF_MTHDS = """
domain = "crossref"
description = "Cross-reference domain"

[pipe.make_ghost]
type = "PipeLLM"
description = "Produce a ghost"
inputs = { doc = "Text" }
output = "Ghost"
model = "$quick-reasoning"
prompt = "Ghost $doc."
"""


class TestCrossFileConceptReferences:
    def test_cross_batch_bare_concept_reference_resolves(self, load_empty_library: Callable[[], str]):
        """A concept declared in batch 1 resolves when referenced by bare code from a separate batch 2."""
        library_id = load_empty_library()
        manager = get_library_manager()
        concept_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=CONCEPT_MTHDS)
        pipe_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=PIPE_BARE_REF_MTHDS)

        # Batch 1: declare the concept only.
        manager.load_from_blueprints(library_id=library_id, blueprints=[concept_blueprint])
        # Batch 2: a pipe referencing that concept by bare code, loaded in a separate call.
        loaded_pipes = manager.load_from_blueprints(library_id=library_id, blueprints=[pipe_blueprint])

        assert "make_summary" in {pipe.code for pipe in loaded_pipes}
        library = manager.get_library(library_id=library_id)
        assert "crossref.Summary" in library.concept_library.root

    def test_single_batch_bare_concept_reference_resolves(self, load_empty_library: Callable[[], str]):
        """The same concept + bare reference also resolve when loaded together in one batch."""
        library_id = load_empty_library()
        manager = get_library_manager()
        concept_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=CONCEPT_MTHDS)
        pipe_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=PIPE_BARE_REF_MTHDS)

        loaded_pipes = manager.load_from_blueprints(library_id=library_id, blueprints=[concept_blueprint, pipe_blueprint])

        assert "make_summary" in {pipe.code for pipe in loaded_pipes}

    def test_undeclared_concept_reference_raises_concept_library_error(self, load_empty_library: Callable[[], str]):
        """A bare reference to a concept declared in no batch raises ConceptLibraryError through the loader."""
        library_id = load_empty_library()
        manager = get_library_manager()
        pipe_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=PIPE_UNDECLARED_REF_MTHDS)

        with pytest.raises(ConceptLibraryError) as exc_info:
            manager.load_from_blueprints(library_id=library_id, blueprints=[pipe_blueprint])
        assert "Ghost" in str(exc_info.value)
