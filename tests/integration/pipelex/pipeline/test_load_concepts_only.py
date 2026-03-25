"""Integration tests for load_concepts_only functions from MTHDS files."""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.hub import get_library_manager
from pipelex.pipeline.validate_bundle import (
    LoadConceptsOnlyResult,
    load_concepts_only,
    load_concepts_only_from_directory,
)


class TestLoadConceptsOnly:
    """Integration tests for loading concepts only (no pipes) from MTHDS files."""

    def test_load_concepts_only_single_file(self, load_empty_library: Callable[[], str]):
        """Test loading concepts from a single MTHDS file."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
email = { type = "text", description = "Customer email" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            result = load_concepts_only(mthds_file_path=mthds_path)

            assert isinstance(result, LoadConceptsOnlyResult)
            assert len(result.blueprints) == 1
            assert len(result.concepts) == 1
            assert result.concepts[0].code == "Customer"

    def test_load_concepts_only_skips_pipes(self, load_empty_library: Callable[[], str]):
        """Test that pipes are skipped when loading concepts only."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain with pipe"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = { type = "text", description = "Topic name" }

[pipe.generate_topic]
type = "PipeLLM"
description = "Generate a topic"
inputs = { subject = "Text" }
output = "Topic"
prompt = "Generate a topic about @subject"
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            result = load_concepts_only(mthds_file_path=mthds_path)

            # Concepts should be loaded
            assert len(result.concepts) == 1
            assert result.concepts[0].code == "Topic"

            # Verify pipes were NOT loaded by checking the library
            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            # The pipe library should not have the pipe loaded
            assert len(library.pipe_library.root) == 0

    def test_load_concepts_only_from_directory(self, load_empty_library: Callable[[], str]):
        """Test loading concepts from a directory with multiple MTHDS files."""
        load_empty_library()
        mthds_content_1 = """
domain = "crm"
description = "CRM domain"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
"""

        mthds_content_2 = """
domain = "accounting"
description = "Accounting domain"

[concept.Invoice]
description = "An invoice"

[concept.Invoice.structure]
amount = { type = "number", description = "Invoice amount" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "crm.mthds").write_text(mthds_content_1, encoding="utf-8")
            (Path(tmp_dir) / "accounting.mthds").write_text(mthds_content_2, encoding="utf-8")

            result = load_concepts_only_from_directory(directory=Path(tmp_dir))

            assert len(result.blueprints) == 2
            assert len(result.concepts) == 2

            concept_codes = [concept.code for concept in result.concepts]
            assert "Customer" in concept_codes
            assert "Invoice" in concept_codes

    def test_load_concepts_only_with_concept_references(self, load_empty_library: Callable[[], str]):
        """Test loading concepts that reference other concepts."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain with concept references"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }

[concept.Invoice]
description = "An invoice"

[concept.Invoice.structure]
customer = { type = "concept", concept_ref = "testapp.Customer", description = "The customer" }
total = { type = "number", description = "Invoice total" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            result = load_concepts_only(mthds_file_path=mthds_path)

            assert len(result.concepts) == 2

            # Verify the library has the concepts loaded
            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            customer = library.concept_library.get_required_concept("testapp.Customer")
            invoice = library.concept_library.get_required_concept("testapp.Invoice")

            assert customer is not None
            assert invoice is not None

    def test_load_concepts_only_detects_cycles(self, load_empty_library: Callable[[], str]):
        """Test that cycle detection still works when loading concepts only."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain with cycles"

[concept.ConceptA]
description = "A"

[concept.ConceptA.structure]
b_ref = { type = "concept", concept_ref = "testapp.ConceptB", description = "Ref to B" }

[concept.ConceptB]
description = "B"

[concept.ConceptB.structure]
a_ref = { type = "concept", concept_ref = "testapp.ConceptA", description = "Ref to A" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            with pytest.raises(Exception, match=r"[Cc]ycle"):
                load_concepts_only(mthds_file_path=mthds_path)

    def test_load_concepts_only_with_library_dirs(self, load_empty_library: Callable[[], str]):
        """Test loading concepts with library dependencies."""
        load_empty_library()
        # Library MTHDS with shared concepts
        library_mthds = """
domain = "shared"
description = "Shared library"

[concept.Address]
description = "An address"

[concept.Address.structure]
street = { type = "text", description = "Street" }
city = { type = "text", description = "City" }
"""

        # Main MTHDS that references the library concept
        main_mthds = """
domain = "main"
description = "Main domain"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Name" }
address = { type = "concept", concept_ref = "shared.Address", description = "The address" }
"""

        with tempfile.TemporaryDirectory() as lib_dir, tempfile.TemporaryDirectory() as main_dir:
            (Path(lib_dir) / "shared.mthds").write_text(library_mthds, encoding="utf-8")
            main_mthds_path = Path(main_dir) / "main.mthds"
            main_mthds_path.write_text(main_mthds, encoding="utf-8")

            result = load_concepts_only(
                mthds_file_path=main_mthds_path,
                library_dirs=[Path(lib_dir)],
            )

            # Main concepts should be loaded
            assert len(result.concepts) == 1
            assert result.concepts[0].code == "Customer"

            # Verify both shared and main concepts are in the library
            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            address = library.concept_library.get_required_concept("shared.Address")
            customer = library.concept_library.get_required_concept("main.Customer")

            assert address is not None
            assert customer is not None

    def test_load_concepts_only_with_mthds_content(self, load_empty_library: Callable[[], str]):
        """Test loading concepts from MTHDS content string."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain"

[concept.MyItem]
description = "An item"

[concept.MyItem.structure]
name = { type = "text", description = "Item name" }
"""

        result = load_concepts_only(mthds_contents=[mthds_content])

        assert len(result.blueprints) == 1
        assert len(result.concepts) == 1
        assert result.concepts[0].code == "MyItem"

    def test_load_concepts_only_with_refines(self, load_empty_library: Callable[[], str]):
        """Test loading concepts with refines relationships."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain with refines"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }

[concept.VIPCustomer]
description = "A VIP customer - inherits from Customer"
refines = "Customer"
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            result = load_concepts_only(mthds_file_path=mthds_path)

            assert len(result.concepts) == 2

            concept_codes = [concept.code for concept in result.concepts]
            assert "Customer" in concept_codes
            assert "VIPCustomer" in concept_codes

    def test_load_concepts_only_directory_skips_pipes(self, load_empty_library: Callable[[], str]):
        """Test that pipes are skipped when loading from directory."""
        load_empty_library()
        mthds_content = """
domain = "testapp"
description = "Test domain with pipe"

[concept.Result]
description = "A result"

[concept.Result.structure]
value = { type = "text", description = "Result value" }

[pipe.my_pipe]
type = "PipeLLM"
description = "A pipe that should be skipped"
inputs = { subject = "Text" }
output = "Result"
prompt = "Generate a result about @subject"
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(mthds_content, encoding="utf-8")

            result = load_concepts_only_from_directory(directory=Path(tmp_dir))

            # Concepts should be loaded
            assert len(result.concepts) == 1
            assert result.concepts[0].code == "Result"

            # Verify pipes were NOT loaded
            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            assert len(library.pipe_library.root) == 0
