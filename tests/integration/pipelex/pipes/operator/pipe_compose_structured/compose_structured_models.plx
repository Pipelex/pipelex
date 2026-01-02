domain = "compose_structured_test"
description = "Concepts for testing PipeCompose with construct (StructuredContent output)"

[concept]
Address = "Address for nested structure testing"
Deal = "Deal for working memory input testing"
SalesSummary = "Sales summary for construct composition testing"
SimpleReport = "Simple report for fixed value testing"
Company = "Company with nested address for testing nested composition"
Order = "Order for invoice testing"
Customer = "Customer for invoice testing"
InvoiceDocument = "Invoice document for nested construct testing"

# Content type conversion testing concepts
MarkdownText = "TextContent subclass with format metadata"
ReportWithStrField = "Report with str field for TextContent to str conversion"
ReportWithTextContent = "Report with TextContent field to keep TextContent object"
ReportWithMarkdown = "Report with MarkdownText field to keep subclass object"
TeamMember = "Team member for list testing"
TeamReport = "Team report with list[TeamMember] field for list extraction"
TeamReportWithListContent = "Team report with ListContent field to keep ListContent object"

# Subclassing and class equivalence testing concepts
RichTextContent = "TextContent subclass with formatting metadata"
ReportWithBaseTextContent = "Report expecting base TextContent accepts subclasses"
Person = "Person model for class equivalence testing"
Employee = "Employee model structurally equivalent to Person"
Manager = "Manager subclass of Person with extra field"
TeamWithPersons = "Team expecting list[Person] tests item subclassing"
TeamWithEmployees = "Team expecting list[Employee] tests item class equivalence"
TeamWithListContentPersons = "Team expecting ListContent[Person] tests item subclassing"
Product = "Product model for mixed list testing"
DiscountedProduct = "Product subclass with discount field"
Catalog = "Catalog expecting list[Product] tests subclass items"

