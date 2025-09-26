from typing import Any, ClassVar, Dict

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import (
    ListContent,
    StructuredContent,
    StuffContent,
    TextContent,
)
from pipelex.core.stuffs.stuff_factory import StuffFactory, StuffFactoryError


class MockCustomContent(StructuredContent):
    title: str
    description: str


class TestData:
    TEXT_STRING: ClassVar[str] = "This is a test text"
    CONCEPT_NAME: ClassVar[str] = "TestConcept"
    SEARCH_DOMAINS: ClassVar[list[str]] = ["test", "native"]
    STUFF_NAME: ClassVar[str] = "test_stuff"
    STUFF_CODE: ClassVar[str] = "test123"

    # ListContent test data
    TEXT_LIST_ITEMS: ClassVar[list[TextContent]] = [
        TextContent(text="Item 1"),
        TextContent(text="Item 2"),
    ]
    EMPTY_LIST_CONTENT: ClassVar[ListContent[TextContent]] = ListContent(items=[])

    # Dictionary test data - native concept
    NATIVE_TEXT_DICT: ClassVar[Dict[str, Any]] = {"concept": NativeConceptEnum.TEXT, "content": {"text": "Native text content"}}

    # Dictionary test data - custom concept with concept field
    CUSTOM_CONCEPT_DICT: ClassVar[dict[str, Any]] = {
        "concept": "test.CustomConcept",
        "content": {"title": "Test Title", "description": "Test Description"},
    }

    # Dictionary test data - custom concept with concept_code field
    CUSTOM_CONCEPT_CODE_DICT: ClassVar[dict[str, Any]] = {"concept_code": "test.AnotherConcept", "content": {"data": "test data"}}

    # Dictionary test data - missing concept
    MISSING_CONCEPT_DICT: ClassVar[dict[str, Any]] = {"content": {"data": "test data"}}

    # Dictionary test data - missing content
    MISSING_CONTENT_DICT: ClassVar[dict[str, Any]] = {"concept": "test.SomeConcept"}


class TestMakeStuffFromStuffContentUsingSearchDomains:
    def test_listcontent_with_valid_items(self, mocker: MockerFixture):
        """Test ListContent with valid items."""
        list_content: ListContent[TextContent] = ListContent(items=TestData.TEXT_LIST_ITEMS)

        mock_stuff = mocker.Mock(spec=Stuff)
        mock_make = mocker.patch.object(StuffFactory, "make_stuff_using_concept_name_and_search_domains", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=list_content,
            search_domains=TestData.SEARCH_DOMAINS,
            stuff_code=TestData.STUFF_CODE,
        )

        assert result == mock_stuff
        mock_make.assert_called_once_with(
            concept_name="TextContent",
            search_domains=TestData.SEARCH_DOMAINS,
            content=list_content,
            name=TestData.STUFF_NAME,
            code=TestData.STUFF_CODE,
        )

    def test_listcontent_with_empty_items_raises_error(self):
        """Test ListContent with empty items raises StuffFactoryError."""
        with pytest.raises(StuffFactoryError, match="ListContent in compact memory has no items"):
            StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=TestData.STUFF_NAME,
                stuff_content_or_data=TestData.EMPTY_LIST_CONTENT,
                search_domains=TestData.SEARCH_DOMAINS,
            )

    def test_listcontent_make_stuff_failure_wraps_error(self, mocker: MockerFixture):
        """Test ListContent wraps StuffFactoryError from make_stuff_using_concept_name_and_search_domains."""
        list_content: ListContent[TextContent] = ListContent(items=TestData.TEXT_LIST_ITEMS)

        original_error = StuffFactoryError("Original error")
        mocker.patch.object(StuffFactory, "make_stuff_using_concept_name_and_search_domains", side_effect=original_error)

        with pytest.raises(StuffFactoryError, match="Could not make stuff for ListContent 'test_stuff': Original error"):
            StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=TestData.STUFF_NAME,
                stuff_content_or_data=list_content,
                search_domains=TestData.SEARCH_DOMAINS,
            )

    def test_stuffcontent_with_native_concept(self, mocker: MockerFixture):
        """Test StuffContent with native concept class name."""
        mock_provider = mocker.patch("pipelex.core.stuffs.stuff_factory.get_concept_provider").return_value
        mock_concept = mocker.Mock()
        mock_provider.get_native_concept.return_value = mock_concept

        text_content = TextContent(text="test")

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=text_content,
            search_domains=TestData.SEARCH_DOMAINS,
            stuff_code=TestData.STUFF_CODE,
        )

        assert result == mock_stuff
        mock_provider.get_native_concept.assert_called_once_with(native_concept=NativeConceptEnum.TEXT)

    def test_stuffcontent_with_non_native_concept(self, mocker: MockerFixture):
        """Test StuffContent with non-native concept properly extracts concept name."""
        custom_content = MockCustomContent(title="Test", description="Test desc")

        mock_stuff = mocker.Mock(spec=Stuff)
        mock_make = mocker.patch.object(StuffFactory, "make_stuff_using_concept_name_and_search_domains", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=custom_content,
            search_domains=TestData.SEARCH_DOMAINS,
        )

        assert result == mock_stuff
        mock_make.assert_called_once_with(
            concept_name="MockCustom",  # Should extract this from MockCustomContent
            search_domains=TestData.SEARCH_DOMAINS,
            content=custom_content,
            name=TestData.STUFF_NAME,
            code=None,
        )

    def test_list_with_valid_items(self, mocker: MockerFixture):
        """Test plain list with valid items."""
        test_list = [TextContent(text="Item 1"), TextContent(text="Item 2")]

        mock_stuff = mocker.Mock(spec=Stuff)
        mock_make = mocker.patch.object(StuffFactory, "make_stuff_using_concept_name_and_search_domains", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=test_list,
            search_domains=TestData.SEARCH_DOMAINS,
            stuff_code=TestData.STUFF_CODE,
        )

        assert result == mock_stuff
        # Verify the content is wrapped in ListContent
        call_args = mock_make.call_args[1]
        assert isinstance(call_args["content"], ListContent)
        assert call_args["content"].items == test_list
        assert call_args["concept_name"] == "TextContent"

    def test_list_with_empty_items_raises_error(self):
        """Test plain list with empty items raises StuffFactoryError."""
        with pytest.raises(StuffFactoryError, match="List in compact memory has no items"):
            StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=TestData.STUFF_NAME,
                stuff_content_or_data=[],
                search_domains=TestData.SEARCH_DOMAINS,
            )

    def test_list_make_stuff_failure_wraps_error(self, mocker: MockerFixture):
        """Test plain list wraps StuffFactoryError from make_stuff_using_concept_name_and_search_domains."""
        test_list = [TextContent(text="Item 1")]

        original_error = StuffFactoryError("Original error")
        mocker.patch.object(StuffFactory, "make_stuff_using_concept_name_and_search_domains", side_effect=original_error)

        with pytest.raises(StuffFactoryError, match="Could not make stuff for list of StuffContent 'test_stuff': Original error"):
            StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=TestData.STUFF_NAME,
                stuff_content_or_data=test_list,
                search_domains=TestData.SEARCH_DOMAINS,
            )

    def test_string_input(self, mocker: MockerFixture):
        """Test string input creates TextContent with TEXT concept."""
        mock_concept = mocker.Mock()
        mock_concept_factory = mocker.patch("pipelex.core.stuffs.stuff_factory.ConceptFactory")
        mock_concept_factory.make_native_concept.return_value = mock_concept

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=TestData.TEXT_STRING,
            search_domains=TestData.SEARCH_DOMAINS,
        )

        assert result == mock_stuff
        mock_concept_factory.make_native_concept.assert_called_once_with(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT])

    def test_dict_with_native_concept(self, mocker: MockerFixture):
        """Test dictionary with native concept."""
        mock_concept = mocker.Mock()
        mock_concept_factory = mocker.patch("pipelex.core.stuffs.stuff_factory.ConceptFactory")
        mock_concept_factory.make_native_concept.return_value = mock_concept

        mock_content = mocker.Mock(spec=StuffContent)
        mock_content_factory = mocker.patch("pipelex.core.stuffs.stuff_factory.StuffContentFactory")
        mock_content_factory.make_stuff_content_from_concept_with_fallback.return_value = mock_content

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=TestData.NATIVE_TEXT_DICT,
            search_domains=TestData.SEARCH_DOMAINS,
            stuff_code=TestData.STUFF_CODE,
        )

        assert result == mock_stuff
        mock_concept_factory.make_native_concept.assert_called_once()
        mock_content_factory.make_stuff_content_from_concept_with_fallback.assert_called_once()

    def test_dict_with_custom_concept_and_stuffcontent_value(self, mocker: MockerFixture):
        """Test dictionary with custom concept and StuffContent as content value."""
        mock_provider = mocker.patch("pipelex.core.stuffs.stuff_factory.get_concept_provider").return_value
        mock_concept = mocker.Mock()
        mock_provider.get_required_concept.return_value = mock_concept

        test_content = TextContent(text="test")
        test_dict = {"concept": "test.CustomConcept", "content": test_content}

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=test_dict,
            search_domains=TestData.SEARCH_DOMAINS,
            stuff_code=TestData.STUFF_CODE,
        )

        assert result == mock_stuff
        mock_provider.get_required_concept.assert_called_once_with(concept_string="test.CustomConcept")

    def test_dict_with_custom_concept_and_dict_value(self, mocker: MockerFixture):
        """Test dictionary with custom concept and dict as content value."""
        mock_provider = mocker.patch("pipelex.core.stuffs.stuff_factory.get_concept_provider").return_value
        mock_concept = mocker.Mock()
        mock_provider.get_required_concept.return_value = mock_concept

        mock_content = mocker.Mock(spec=StuffContent)
        mock_content_factory = mocker.patch("pipelex.core.stuffs.stuff_factory.StuffContentFactory")
        mock_content_factory.make_stuff_content_from_concept_with_fallback.return_value = mock_content

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=TestData.CUSTOM_CONCEPT_DICT,
            search_domains=TestData.SEARCH_DOMAINS,
            stuff_code=TestData.STUFF_CODE,
        )

        assert result == mock_stuff
        mock_provider.get_required_concept.assert_called_with(concept_string="test.CustomConcept")
        mock_content_factory.make_stuff_content_from_concept_with_fallback.assert_called_once_with(
            concept=mock_concept, value={"title": "Test Title", "description": "Test Description"},
        )

    def test_dict_with_concept_code_field(self, mocker: MockerFixture):
        """Test dictionary with concept_code field instead of concept."""
        mock_provider = mocker.patch("pipelex.core.stuffs.stuff_factory.get_concept_provider").return_value
        mock_concept = mocker.Mock()
        mock_provider.get_required_concept.return_value = mock_concept

        mock_content = mocker.Mock(spec=StuffContent)
        mock_content_factory = mocker.patch("pipelex.core.stuffs.stuff_factory.StuffContentFactory")
        mock_content_factory.make_stuff_content_from_concept_with_fallback.return_value = mock_content

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=TestData.CUSTOM_CONCEPT_CODE_DICT,
            search_domains=TestData.SEARCH_DOMAINS,
        )

        assert result == mock_stuff

    def test_dict_missing_concept_raises_error(self):
        """Test dictionary missing concept field raises StuffFactoryError."""
        with pytest.raises(StuffFactoryError, match="Stuff content data dict is badly formed: no concept code"):
            StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=TestData.STUFF_NAME,
                stuff_content_or_data=TestData.MISSING_CONCEPT_DICT,
                search_domains=TestData.SEARCH_DOMAINS,
            )

    def test_dict_missing_content_raises_error(self):
        """Test dictionary missing content field raises StuffFactoryError."""
        with pytest.raises(StuffFactoryError, match="Stuff content data dict is badly formed: 'content'"):
            StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=TestData.STUFF_NAME,
                stuff_content_or_data=TestData.MISSING_CONTENT_DICT,
                search_domains=TestData.SEARCH_DOMAINS,
            )

    def test_default_parameters(self, mocker: MockerFixture):
        """Test function with default parameters (no stuff_code)."""
        mock_concept = mocker.Mock()
        mock_concept_factory = mocker.patch("pipelex.core.stuffs.stuff_factory.ConceptFactory")
        mock_concept_factory.make_native_concept.return_value = mock_concept

        mock_stuff = mocker.Mock(spec=Stuff)
        mocker.patch.object(StuffFactory, "make_stuff", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=TestData.TEXT_STRING,
            search_domains=TestData.SEARCH_DOMAINS,
        )

        assert result == mock_stuff

    def test_empty_search_domains(self, mocker: MockerFixture):
        """Test function with empty search domains list."""
        list_content: ListContent[TextContent] = ListContent(items=TestData.TEXT_LIST_ITEMS)

        mock_stuff = mocker.Mock(spec=Stuff)
        mock_make = mocker.patch.object(StuffFactory, "make_stuff_using_concept_name_and_search_domains", return_value=mock_stuff)

        result = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
            name=TestData.STUFF_NAME,
            stuff_content_or_data=list_content,
            search_domains=[],
        )

        assert result == mock_stuff
        mock_make.assert_called_once_with(
            concept_name="TextContent",
            search_domains=[],
            content=list_content,
            name=TestData.STUFF_NAME,
            code=None,
        )
