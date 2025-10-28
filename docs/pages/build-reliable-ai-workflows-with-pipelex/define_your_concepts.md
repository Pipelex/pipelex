# Defining Your Concepts

Concepts are the foundation of reliable AI workflows. They define what flows through your pipes—not just as data types, but as meaningful pieces of knowledge with clear boundaries and validation rules.

## Writing Concept Definitions

Every concept starts with a natural language definition. This definition serves two audiences: developers who build with your pipeline, and the LLMs that process your knowledge.

### Basic Concept Definition

The simplest way to define a concept is with a descriptive sentence:

```plx
[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Employee = "A person employed by an organization"
ProductReview = "A customer's evaluation of a product or service"
```

Those concepts will be Text-based by default. If you want to use sutrctured output, you need to create a Python class for the concept, or declare the structure directly in the concept definition. 

**Key principles for concept definitions:**

1. **Define what it is, not what it's for**
   ```plx
   # ❌ Wrong: includes usage context
   TextToSummarize = "Text that needs to be summarized"
   
   # ✅ Right: defines the essence
   Article = "A written composition on a specific topic"
   ```

2. **Use singular forms**
   ```plx
   # ❌ Wrong: plural form
   Invoices = "Commercial documents from sellers"
   
   # ✅ Right: singular form
   Invoice = "A commercial document issued by a seller to a buyer"
   ```

3. **Avoid unnecessary adjectives**
   ```plx
   # ❌ Wrong: includes subjective qualifier
   LongArticle = "A lengthy written composition"
   
   # ✅ Right: neutral description
   Article = "A written composition on a specific topic"
   ```

### Organizing Related Concepts

Group concepts that naturally belong together in the same domain. A domain acts as a namespace for a set of related concepts and pipes, helping you organize and reuse your pipeline components. You can learn more about them in [Kick off a Pipelex Workflow Project](kick-off-a-pipelex-workflow-project.md#what-are-domains).

```plx
# finance.plx
domain = "finance"
description = "Financial document processing"

[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Receipt = "Proof of payment for goods or services"
PurchaseOrder = "A buyer's formal request to purchase goods or services"
PaymentTerms = "Conditions under which payment is to be made"
LineItem = "An individual item or service listed in a financial document"
```

## How to Structure Your Concepts

Once you've defined your concepts semantically, you may need to add structure if they have specific fields. Pipelex offers three approaches:

### 1. No Structure (Concept Only)

For concepts that only refine native concepts without adding fields, just declare them with a description. They default to text-based content.

```plx
[concept]
ProductReview = "A customer's evaluation of a product or service"
```

### 2. Inline TOML Structures (Recommended)

Define structured concepts directly in your `.plx` files using TOML syntax. This is the fastest and simplest approach for most use cases.

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
total_amount = { type = "number", description = "Total invoice amount", required = true }
vendor_name = "The name of the vendor"
```

Behind the scenes, Pipelex generates a complete Pydantic model with validation.

### 3. Python StructuredContent Classes

Create explicit Python classes when you need custom validation, computed properties, or advanced features.

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Invoice(StructuredContent):
    invoice_number: str
    total_amount: float = Field(ge=0, description="Total invoice amount")
    vendor_name: str
```

**For detailed guidance on choosing and implementing these approaches, see [Structuring Concepts](structuring-concepts.md).**

## Adding Structure with Python Models

This section covers the Python class approach for structured concepts. For a simpler alternative using inline TOML syntax, see [Structuring Concepts](structuring-concepts.md).

While text definitions help LLMs understand your concepts, Python models ensure structured, validated outputs when you need custom validation, computed properties, or advanced features.

### Creating a Python Structured Model

For concepts that need custom logic, create a Python class that inherits from `StructuredContent`:

```python
# finance.py
from datetime import datetime
from pydantic import Field
from pipelex.core.stuffs.structured_content import StructuredContent

class Invoice(StructuredContent):
    invoice_number: str
    issue_date: datetime
    due_date: datetime
    vendor_name: str
    customer_name: str
    total_amount: float = Field(ge=0, description="Total invoice amount")
    currency: str = Field(default="USD", description="Three-letter currency code")
```

The model name must match the concept name exactly: `Invoice` concept → `Invoice` class.

Python classes are automatically discovered and registered by Pipelex.

!!! warning "Module Execution During Auto-Discovery"
    When Pipelex discovers `StructuredContent` classes, it imports the module containing them. **Any code at the module level (outside functions/classes) will be executed during import.** This can have unintended side effects.
    
    **Best practice:** Keep your `StructuredContent` classes in dedicated modules (e.g., `*_struct.py` files) with minimal module-level code, or ensure module-level code is safe to execute during discovery.

### With Custom Validation

Use Pydantic's validation features for complex rules:

```python
from pydantic import field_validator
from pipelex.core.stuffs.structured_content import StructuredContent

class Employee(StructuredContent):
    name: str
    email: str
    department: str
    years_of_experience: int = Field(ge=0, le=50, description="Years of work experience")
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v.lower()
```

### Linking Concepts to Models

The connection between `.plx` definitions and Python models happens automatically through naming:

```plx
# hr.plx
domain = "hr"

[concept]
Employee = "A person employed by an organization"
Meeting = "A scheduled gathering of people for discussion"
Department = "An organizational unit within a company"  # No Python model => text-based
```

```python
# hr.py
from pipelex.core.stuffs.structured_content import StructuredContent
from datetime import datetime

class Employee(StructuredContent):
    name: str
    email: str
    department: str
    hire_date: datetime

class Meeting(StructuredContent):
    title: str
    scheduled_date: datetime
    duration_minutes: int
    attendees: list[str]

# Note: Department concept has no Python model, so it's text-based
```

**For more examples, advanced features, and guidance on when to use Python classes vs inline structures, see [Structuring Concepts](structuring-concepts.md).**

## Concept Refinement and Inheritance

Sometimes concepts build on each other. A `Contract` is a kind of `Document`. A `NonCompeteClause` is a specific part of a `Contract`. Pipelex lets you express these relationships.

### Declaring Concept Refinement

Use the `refines` field to indicate when one concept is a more specific version of another:

```plx
[concept]
Document = "A written or printed record"

[concept.Contract]
description = "A legally binding agreement between parties"
refines = "Text"

[concept.ContractLogo]
description = "A logo associated with a contract"
refines = "Image"
```

### Why Refinement Matters

Concept refinement helps in two ways:

1. **Semantic clarity**: Makes relationships between concepts explicit
2. **Pipeline flexibility**: Pipes accepting general concepts can work with refined ones
3. **Validation**: You can only refine Native concepts **for now** (Text, Image, PDF, TextAndImages, Number, Page)

For example, a pipe that processes `Document` can also process `Contract` or `EmploymentContract`:

```plx
[pipe.extract_key_points]
type = "PipeLLM"
description = "Extract main points from any document"
inputs = { doc = "Document" }  # Can accept Document, Contract, or EmploymentContract
output = "KeyPoints"
```

## Native Concepts and Their Structures

Pipelex includes several built-in native concepts that cover common data types in AI workflows. These concepts come with predefined structures and are automatically available in all pipelines.

### Available Native Concepts

Here are all the native concepts you can use out of the box:

| Concept | Description | Content Class Name |
|---------|-------------|---------------|
| `Text` | A text | `TextContent` |
| `Image` | An image | `ImageContent` |
| `PDF` | A PDF document | `PDFContent` |
| `TextAndImages` | A text combined with images | `TextAndImagesContent` |
| `Number` | A number | `NumberContent` |
| `Page` | The content of a document page with text, images, and optional page view | `PageContent` |
| `Dynamic` | A dynamic concept that can adapt to context | `DynamicContent` |
| `LlmPrompt` | A prompt for an LLM | *No specific implementation* |
| `Anything` | A concept that can represent any type of content | *No specific implementation* |

### Native Concept Structures

Each native concept has a corresponding Python structure that defines its data model:

#### TextContent
```python
class TextContent(StuffContent):
    text: str
```

#### ImageContent
```python
class ImageContent(StuffContent):
    url: str
    source_prompt: Optional[str] = None
    caption: Optional[str] = None
    base_64: Optional[str] = None
```

#### PDFContent
```python
class PDFContent(StuffContent):
    url: str
```

#### NumberContent
```python
class NumberContent(StuffContent):
    number: Union[int, float]
```

#### TextAndImagesContent
```python
class TextAndImagesContent(StuffContent):
    text: Optional[TextContent]
    images: Optional[List[ImageContent]]
```

#### PageContent
```python
class PageContent(StructuredContent):
    text_and_images: TextAndImagesContent
    page_view: Optional[ImageContent] = None
```

#### DynamicContent
```python
class DynamicContent(StuffContent):
    # Dynamic content that can adapt to context
    # Structure is flexible and determined at runtime
    pass
```

**Note**: `LlmPromptContent` and `AnythingContent` are referenced in the native concept definitions but do not have actual implementations in the current codebase. They are handled through the generic content system.

### Using Native Concepts

Native concepts can be used directly in your pipeline definitions without any additional setup:

```plx
[pipe.analyze_document]
type = "PipeLLM"
description = "Analyze a PDF document"
inputs = { document = "PDF" }
output = "Text"
prompt = "Analyze this document and provide a summary"

[pipe.process_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = "Describe what you see in this image"

[pipe.extract_from_page]
type = "PipeLLM"
description = "Extract information from a document page"
inputs = { page_content = "Page" }
output = "ExtractedInfo"
prompt = "Extract key information from this page content"
```

### Refining Native Concepts

You can create more specific concepts by refining native ones:

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"
refines = "PDF"

[concept.ProductPhoto]
description = "A photograph of a product for marketing purposes"
refines = "Image"

[concept.ContractPage]
description = "A page from a legal contract document"
refines = "Page"
```

When you refine a native concept, your refined concept inherits the structure of the native concept but can be used in more specific contexts. This allows for better semantic clarity while maintaining compatibility with pipes that accept the base native concept.

With well-defined concepts—both in natural language and code—your pipelines gain clarity, reliability, and maintainability. Next, we'll see how to build pipes that transform these concepts.