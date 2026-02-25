import pytest
from pytest_mock import MockerFixture

from pipelex.core.stuffs.structured_content import StructuredContent
from tests.unit.pipelex.core.stuffs.structured_content.test_data import (
    AddressContent,
    CompanyContent,
    PersonContent,
    SampleStructuredContent,
    TestData,
)


class TestStructuredContentRenders:
    """Tests for StructuredContent render methods."""

    def test_rendered_markdown_minimal(self):
        """Verify rendered_markdown returns markdown-formatted content."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.rendered_markdown()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_MINIMAL

    def test_rendered_markdown_full(self):
        """Verify rendered_markdown includes all populated fields."""
        content = SampleStructuredContent(
            name=TestData.SAMPLE_NAME,
            value=TestData.SAMPLE_VALUE,
            description=TestData.SAMPLE_DESCRIPTION,
        )
        result = content.rendered_markdown()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_FULL

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.rendered_for_prompt()
        # rendered_for_prompt calls rendered_markdown
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_MINIMAL

    def test_rendered_html_minimal(self):
        """Verify rendered_html returns HTML table format."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.rendered_html()
        assert result == TestData.EXPECTED_RENDERED_HTML_MINIMAL

    def test_rendered_html_full(self):
        """Verify rendered_html includes all populated fields."""
        content = SampleStructuredContent(
            name=TestData.SAMPLE_NAME,
            value=TestData.SAMPLE_VALUE,
            description=TestData.SAMPLE_DESCRIPTION,
        )
        result = content.rendered_html()
        assert result == TestData.EXPECTED_RENDERED_HTML_FULL

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_MINIMAL

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML_MINIMAL

    def test_rendered_html_nested_address(self):
        """Verify rendered_html works for a simple nested StructuredContent."""
        address = AddressContent(
            street=TestData.NESTED_ADDRESS_STREET,
            city=TestData.NESTED_ADDRESS_CITY,
        )
        result = address.rendered_html()
        assert result == TestData.EXPECTED_ADDRESS_HTML

    def test_rendered_html_nested_person_with_address(self):
        """Verify rendered_html recursively renders nested StructuredContent fields."""
        address = AddressContent(
            street=TestData.NESTED_ADDRESS_STREET,
            city=TestData.NESTED_ADDRESS_CITY,
        )
        person = PersonContent(
            name=TestData.NESTED_PERSON_NAME,
            age=TestData.NESTED_PERSON_AGE,
            address=address,
        )
        result = person.rendered_html()
        assert result == TestData.EXPECTED_PERSON_HTML

    def test_rendered_html_nested_company_with_employees(self):
        """Verify rendered_html recursively renders list of nested StructuredContent."""
        address = AddressContent(
            street=TestData.NESTED_ADDRESS_STREET,
            city=TestData.NESTED_ADDRESS_CITY,
        )
        person = PersonContent(
            name=TestData.NESTED_PERSON_NAME,
            age=TestData.NESTED_PERSON_AGE,
            address=address,
        )
        company = CompanyContent(
            company_name=TestData.NESTED_COMPANY_NAME,
            employees=[person],
        )
        result = company.rendered_html()
        assert result == TestData.EXPECTED_COMPANY_ONE_EMPLOYEE_HTML

    def test_rendered_html_calls_count_for_nested_person(self, mocker: MockerFixture):
        """Verify rendered_html is called recursively for nested StructuredContent.

        PersonContent has 1 nested AddressContent, so rendered_html should be called:
        - 1 time for PersonContent
        - 1 time for AddressContent (nested)
        Total: 2 calls
        """
        address = AddressContent(
            street=TestData.NESTED_ADDRESS_STREET,
            city=TestData.NESTED_ADDRESS_CITY,
        )
        person = PersonContent(
            name=TestData.NESTED_PERSON_NAME,
            age=TestData.NESTED_PERSON_AGE,
            address=address,
        )

        call_count = 0
        original_rendered_html = StructuredContent.rendered_html

        def counting_rendered_html(self_arg: StructuredContent) -> str:
            nonlocal call_count
            call_count += 1
            return original_rendered_html(self_arg)

        mocker.patch.object(StructuredContent, "rendered_html", counting_rendered_html)

        person.rendered_html()

        assert call_count == 2

    def test_rendered_html_calls_count_for_company_with_one_employee(self, mocker: MockerFixture):
        """Verify rendered_html is called recursively for nested list of StructuredContent.

        CompanyContent has 1 PersonContent in employees list, PersonContent has 1 AddressContent.
        rendered_html should be called:
        - 1 time for CompanyContent
        - 1 time for PersonContent (in list)
        - 1 time for AddressContent (nested in PersonContent)
        Total: 3 calls
        """
        address = AddressContent(
            street=TestData.NESTED_ADDRESS_STREET,
            city=TestData.NESTED_ADDRESS_CITY,
        )
        person = PersonContent(
            name=TestData.NESTED_PERSON_NAME,
            age=TestData.NESTED_PERSON_AGE,
            address=address,
        )
        company = CompanyContent(
            company_name=TestData.NESTED_COMPANY_NAME,
            employees=[person],
        )

        call_count = 0
        original_rendered_html = StructuredContent.rendered_html

        def counting_rendered_html(self_arg: StructuredContent) -> str:
            nonlocal call_count
            call_count += 1
            return original_rendered_html(self_arg)

        mocker.patch.object(StructuredContent, "rendered_html", counting_rendered_html)

        company.rendered_html()

        assert call_count == 3

    def test_rendered_html_calls_count_for_company_with_two_employees(self, mocker: MockerFixture):
        """Verify rendered_html is called for each item in a list of StructuredContent.

        CompanyContent has 2 PersonContent in employees list, each PersonContent has 1 AddressContent.
        rendered_html should be called:
        - 1 time for CompanyContent
        - 2 times for PersonContent (2 employees in list)
        - 2 times for AddressContent (1 nested in each PersonContent)
        Total: 5 calls
        """
        address1 = AddressContent(street="123 Main St", city="Springfield")
        person1 = PersonContent(name="John Doe", age=30, address=address1)

        address2 = AddressContent(street="456 Oak Ave", city="Shelbyville")
        person2 = PersonContent(name="Jane Smith", age=25, address=address2)

        company = CompanyContent(
            company_name="Acme Corp",
            employees=[person1, person2],
        )

        call_count = 0
        original_rendered_html = StructuredContent.rendered_html

        def counting_rendered_html(self_arg: StructuredContent) -> str:
            nonlocal call_count
            call_count += 1
            return original_rendered_html(self_arg)

        mocker.patch.object(StructuredContent, "rendered_html", counting_rendered_html)

        company.rendered_html()

        assert call_count == 5
