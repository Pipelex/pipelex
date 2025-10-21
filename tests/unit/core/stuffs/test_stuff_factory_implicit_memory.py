import os
from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.client.protocol import StuffContentOrData
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_concept_library
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from tests.unit.core.stuffs.data import ERROR_TEST_CASES, SEARCH_DOMAIN_TEST_CASES, TEST_CASES


@pytest.fixture(scope="class")
def setup_test_concept():
    # Register the class in the class registry
    ClassRegistryUtils.register_classes_in_file(
        file_path=os.path.join(os.path.dirname(__file__), "data.py"),
        base_class=StructuredContent,
        is_include_imported=False,
    )

    # Create and register the test concept
    concept_library = get_concept_library()

    # Create the concept
    concept = ConceptFactory.make(
        concept_code="MyConcept",
        domain="test_domain",
        description="Test concept for unit tests",
        structure_class_name="MyConcept",
    )
    # Register it in the library
    concept_library.add_new_concept(concept=concept)

    # Create a concept that is not native.Text but initiable by str
    concept_not_native_text = ConceptFactory.make(
        domain="test_domain",
        concept_code="MyConceptNotNativeText",
        description="Test concept for unit tests",
        structure_class_name="MyConceptNotNativeText",
        refines="native.Text",
    )
    concept_library.add_new_concept(concept=concept_not_native_text)

    # Create AnotherConcept for search domain tests
    concept_another = ConceptFactory.make(
        concept_code="AnotherConcept",
        domain="test_domain",
        description="Test concept for search domains",
        structure_class_name="AnotherConcept",
    )
    concept_library.add_new_concept(concept=concept_another)

    yield concept

    # Cleanup after test
    concept_library.remove_concepts_by_concept_strings(
        concept_strings=["test_domain.MyConcept", "test_domain.MyConceptNotNativeText", "test_domain.AnotherConcept"]
    )


class TestStuffFactoryImplicitMemory:
    """Test StuffFactory with pipeline inputs input formats.

    This covers cases where stuff_content_or_data is:
    - Case 1: Direct content (no 'concept' key)
      - String (1.1)
      - List of strings (1.2)
      - TextContent object - native (1.2b)
      - List of TextContent objects - native (1.2c)
      - StuffContent object - custom (1.3 / 1.3a)
      - ListContent of StuffContent objects (1.3b, formerly 1.5)
      - List of StuffContent objects (1.4)
    - Case 2: Dict with 'concept' AND 'content' keys (plain dict or DictStuff)
      - String content (2.1, 2.1b, 2.1c)
      - List of strings (2.2, 2.2b)
      - StuffContent object (2.3)
      - List of StuffContent objects (2.4)
      - Dict content (2.5)
      - List of dicts (2.6)
    """

    @pytest.mark.parametrize(
        ("test_name", "stuff_content_or_data", "stuff_name", "stuff_code", "expected_stuff"),
        TEST_CASES,
    )
    def test_implicit_memory_case(
        self,
        setup_test_concept: Any,
        test_name: str,
        stuff_content_or_data: StuffContentOrData,
        stuff_name: str | None,
        stuff_code: str,
        expected_stuff: Stuff,
    ):
        log.info(f"Testing case: {test_name}")
        log.debug(f"setup_test_concept: {setup_test_concept}")

        result = StuffFactory.make_stuff_from_stuff_content_or_data(
            name=stuff_name,
            code=stuff_code,
            stuff_content_or_data=stuff_content_or_data,
        )
        pretty_print(result, title=f"Result for test case: {test_name}")
        pretty_print(expected_stuff, title=f"Expected stuff for test case: {test_name}")

        assert result == expected_stuff, f"Failed for test case: {test_name}"


class TestStuffFactoryImplicitMemoryWithSearchDomains:
    """Test StuffFactory with search_domains parameter.

    This tests that search_domains correctly resolves concepts.
    """

    @pytest.mark.parametrize(
        ("test_name", "stuff_content_or_data", "stuff_name", "stuff_code", "search_domains", "expected_stuff"),
        SEARCH_DOMAIN_TEST_CASES,
    )
    def test_search_domain_case(
        self,
        setup_test_concept: Any,
        test_name: str,
        stuff_content_or_data: StuffContentOrData,
        stuff_name: str | None,
        stuff_code: str,
        search_domains: list[str],
        expected_stuff: Stuff,
    ):
        log.info(f"Testing search domain case: {test_name}")
        log.debug(f"setup_test_concept: {setup_test_concept}")
        result = StuffFactory.make_stuff_from_stuff_content_or_data(
            name=stuff_name,
            code=stuff_code,
            stuff_content_or_data=stuff_content_or_data,
            search_domains=search_domains,
        )

        pretty_print(result, title=f"Result for test case: {test_name}")
        pretty_print(expected_stuff, title=f"Expected stuff for test case: {test_name}")

        assert result == expected_stuff, f"Failed for test case: {test_name}"


class TestStuffFactoryImplicitMemoryErrors:
    """Test StuffFactory error cases.

    This tests that the factory properly raises exceptions for invalid inputs.
    """

    @pytest.mark.parametrize(
        ("test_name", "stuff_content_or_data", "stuff_name", "stuff_code", "search_domains", "expected_exception", "error_match"),
        ERROR_TEST_CASES,
    )
    def test_error_case(
        self,
        setup_test_concept: Any,
        test_name: str,
        stuff_content_or_data: StuffContentOrData,
        stuff_name: str | None,
        stuff_code: str,
        search_domains: list[str] | None,
        expected_exception: type[Exception],
        error_match: str,
    ):
        log.info(f"Testing error case: {test_name}")
        log.debug(f"setup_test_concept: {setup_test_concept}")

        with pytest.raises(expected_exception, match=error_match):
            StuffFactory.make_stuff_from_stuff_content_or_data(
                name=stuff_name,
                code=stuff_code,
                stuff_content_or_data=stuff_content_or_data,
                search_domains=search_domains,
            )
