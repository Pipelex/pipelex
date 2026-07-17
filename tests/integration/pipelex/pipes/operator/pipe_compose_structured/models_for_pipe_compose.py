"""Test StructuredContent models for PipeCompose construct testing."""

from datetime import date

from pydantic import Field

from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.mermaid_content import MermaidContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


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


# ============================================================================
# Models for content type conversion testing
# ============================================================================


class MarkdownText(TextContent):
    """A TextContent subclass with additional metadata for format tracking."""

    format_type: str = Field(default="markdown", description="The text format type")


class ReportWithStrField(StructuredContent):
    """Report with a str field - should receive TextContent.text extracted."""

    title: str = Field(description="Report title as plain string")
    author: str = Field(description="Author name as plain string")


class ReportWithTextContent(StructuredContent):
    """Report with TextContent field - should receive TextContent object as-is."""

    title_content: TextContent = Field(description="Report title as TextContent object")
    description: str = Field(description="Additional description")


class ReportWithMarkdown(StructuredContent):
    """Report with MarkdownText field - should receive MarkdownText subclass object as-is."""

    markdown_content: MarkdownText = Field(description="Markdown content as MarkdownText object")
    summary: str = Field(description="Plain text summary")


class TeamMember(StructuredContent):
    """Team member for list testing."""

    name: str = Field(description="Member name")
    role: str = Field(description="Member role")


class TeamReport(StructuredContent):
    """Team report with list[TeamMember] field - should receive extracted list items."""

    team_name: str = Field(description="Name of the team")
    members: list[TeamMember] = Field(description="List of team members")


class TeamReportWithListContent(StructuredContent):
    """Team report with ListContent field - should receive ListContent object as-is."""

    team_name: str = Field(description="Name of the team")
    members_list: ListContent[TeamMember] = Field(description="Team members as ListContent object")


# ============================================================================
# Models for subclassing and class equivalence testing
# ============================================================================


class RichTextContent(TextContent):
    """TextContent subclass with formatting metadata."""

    bold: bool = Field(default=False, description="Whether the text is bold")
    italic: bool = Field(default=False, description="Whether the text is italic")


class ReportWithBaseTextContent(StructuredContent):
    """Report expecting base TextContent, should accept TextContent subclasses."""

    content: TextContent = Field(description="Text content (accepts subclasses)")
    note: str = Field(description="Additional note")


class Person(StructuredContent):
    """Person model for class equivalence testing."""

    name: str = Field(description="Person's name")
    role: str = Field(description="Person's role")


class Employee(StructuredContent):
    """Employee model - structurally equivalent to Person (same fields)."""

    name: str = Field(description="Employee name")
    role: str = Field(description="Employee role")


class Manager(Person):
    """Manager subclass of Person with extra field."""

    department: str = Field(description="Department managed")


class TeamWithPersons(StructuredContent):
    """Team expecting list[Person], tests item subclassing."""

    team_name: str = Field(description="Name of the team")
    members: list[Person] = Field(description="List of persons")


class TeamWithEmployees(StructuredContent):
    """Team expecting list[Employee], tests item class equivalence."""

    team_name: str = Field(description="Name of the team")
    members: list[Employee] = Field(description="List of employees")


class TeamWithListContentPersons(StructuredContent):
    """Team expecting ListContent[Person], tests item subclassing in ListContent."""

    team_name: str = Field(description="Name of the team")
    members: ListContent[Person] = Field(description="ListContent of persons")


class Product(StructuredContent):
    """Product model for mixed list testing."""

    sku: str = Field(description="Product SKU")
    price: float = Field(description="Product price")


class DiscountedProduct(Product):
    """Product subclass with discount field."""

    discount_percent: float = Field(description="Discount percentage")


class Catalog(StructuredContent):
    """Catalog expecting list[Product], tests subclass items."""

    catalog_name: str = Field(description="Catalog name")
    products: list[Product] = Field(description="List of products")


# ============================================================================
# Models for direct StructuredContent object composition testing
# These test cases where FROM_VAR returns a StructuredContent object directly
# (not TextContent, not ListContent) and the target field expects a different type.
# ============================================================================


class PersonHolder(StructuredContent):
    """Container with a Person field, tests direct StructuredContent object composition."""

    holder_name: str = Field(description="Name of the holder")
    person: Person = Field(description="The held person")


class EmployeeHolder(StructuredContent):
    """Container with an Employee field, tests class equivalence for direct objects."""

    holder_name: str = Field(description="Name of the holder")
    employee: Employee = Field(description="The held employee")


class ManagerHolder(StructuredContent):
    """Container with a Manager field, tests subclass for direct objects."""

    holder_name: str = Field(description="Name of the holder")
    manager: Manager = Field(description="The held manager")


class Location(StructuredContent):
    """Location model with different fields than Person/Employee."""

    latitude: float = Field(description="Latitude coordinate")
    longitude: float = Field(description="Longitude coordinate")
    name: str = Field(description="Location name")


class LocationHolder(StructuredContent):
    """Container with a Location field, tests incompatible class conversion."""

    holder_name: str = Field(description="Name of the holder")
    location: Location = Field(description="The held location")


# ============================================================================
# Models for StuffContent subclass testing (ImageContent, DocumentContent, etc.)
# ============================================================================


class ImageGallery(StructuredContent):
    """Gallery with ImageContent fields."""

    gallery_name: str = Field(description="Name of the gallery")
    cover_image: ImageContent = Field(description="Cover image for the gallery")
    featured_image: ImageContent | None = Field(default=None, description="Optional featured image")


class DocumentArchive(StructuredContent):
    """Archive with DocumentContent fields."""

    archive_name: str = Field(description="Name of the archive")
    main_document: DocumentContent = Field(description="Main document")
    supplementary_doc: DocumentContent | None = Field(default=None, description="Optional supplementary document")


class Metrics(StructuredContent):
    """Metrics container with NumberContent fields."""

    metric_name: str = Field(description="Name of the metric set")
    primary_value: NumberContent = Field(description="Primary metric value")
    secondary_value: NumberContent | None = Field(default=None, description="Optional secondary value")


class PageReport(StructuredContent):
    """Report containing PageContent."""

    report_title: str = Field(description="Title of the report")
    main_page: PageContent = Field(description="Main page content")


class CodeSnippet(StructuredContent):
    """Container for MermaidContent."""

    snippet_name: str = Field(description="Name of the snippet")
    diagram: MermaidContent = Field(description="Mermaid diagram content")


class WebContent(StructuredContent):
    """Container for HtmlContent."""

    content_title: str = Field(description="Title of the web content")
    html_block: HtmlContent = Field(description="HTML content block")


class DataPayload(StructuredContent):
    """Container for JSONContent."""

    payload_name: str = Field(description="Name of the data payload")
    data: JSONContent = Field(description="JSON data content")


class MixedMediaReport(StructuredContent):
    """Report with multiple StuffContent types."""

    report_title: str = Field(description="Report title")
    cover_image: ImageContent = Field(description="Cover image")
    document: DocumentContent = Field(description="Associated document")
    view_count: NumberContent = Field(description="View count metric")


class ImageListGallery(StructuredContent):
    """Gallery with a list of ImageContent."""

    gallery_name: str = Field(description="Gallery name")
    images: list[ImageContent] = Field(description="List of images")


class DocumentBundle(StructuredContent):
    """Bundle with a list of DocumentContent."""

    bundle_name: str = Field(description="Bundle name")
    documents: list[DocumentContent] = Field(description="List of documents")


# ============================================================================
# Models for native scalar conversion testing
# These test whole-stuff copies into native-typed fields: the content wrapper
# must be unwrapped to the native value (TextContent -> str, NumberContent -> float,
# YesNoContent -> bool, DateContent -> date), including into Optional fields.
# ============================================================================


class NoteHolder(StructuredContent):
    """Holder with an optional str field - should receive TextContent.text extracted."""

    note: str | None = Field(default=None, description="The note, optional")


class TagsHolder(StructuredContent):
    """Holder with a required list[str] field - should receive item texts extracted."""

    tags: list[str] = Field(description="The tags")


class OptionalTagsHolder(StructuredContent):
    """Holder with an optional list[str] field - should receive item texts extracted."""

    tags: list[str] | None = Field(default=None, description="The tags, optional")


class NullableTagsHolder(StructuredContent):
    """Holder with a list of nullable str items - should receive item texts extracted."""

    tags: list[str | None] = Field(description="The tags, each possibly null")


class ScoreHolder(StructuredContent):
    """Holder with a float field - should receive NumberContent.number extracted."""

    score: float = Field(description="The score")


class ApprovalHolder(StructuredContent):
    """Holder with a bool field - should receive YesNoContent.yes_no extracted."""

    approved: bool = Field(description="Whether approved")


class DeadlineHolder(StructuredContent):
    """Holder with a date field - should receive DateContent.date extracted."""

    deadline: date = Field(description="The deadline date")
