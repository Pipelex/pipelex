"""Test StructuredContent models for PipeCompose construct testing."""

from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class Address(StructuredContent):
    """Address for nested structure testing."""

    street: str = Field(description="Street address")
    city: str = Field(description="City name")
    country: str = Field(description="Country name")


class Deal(StructuredContent):
    """Deal for working memory input testing."""

    customer_name: str = Field(description="Customer name")
    amount: float = Field(description="Deal amount")


class SalesSummary(StructuredContent):
    """Sales summary for construct composition testing."""

    report_title: str = Field(description="Title of the report")
    customer_name: str = Field(description="Customer name")
    deal_value: float = Field(description="Deal value")
    summary_text: str = Field(description="Generated summary text")


class SimpleReport(StructuredContent):
    """Simple report for fixed value testing."""

    title: str = Field(description="Report title")
    author: str = Field(description="Author name")
    score: float = Field(description="Report score")


class Company(StructuredContent):
    """Company with nested address for testing nested composition."""

    name: str = Field(description="Company name")
    headquarters: Address = Field(description="Company headquarters")


class Order(StructuredContent):
    """Order for invoice testing."""

    order_id: str = Field(description="Order ID")
    total_amount: float = Field(description="Total order amount")


class Customer(StructuredContent):
    """Customer for invoice testing."""

    name: str = Field(description="Customer name")
    address: Address = Field(description="Customer address")


class InvoiceDocument(StructuredContent):
    """Invoice document for nested construct testing."""

    invoice_number: str = Field(description="Invoice number")
    total: float = Field(description="Total amount")
    billing_address: Address = Field(description="Billing address")
