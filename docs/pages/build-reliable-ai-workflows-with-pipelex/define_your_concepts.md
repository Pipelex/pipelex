# Defining Your Concepts

Concepts are the foundation of reliable knowledge pipelines. They define what flows through your pipes—not just as data types, but as meaningful pieces of knowledge with clear boundaries and validation rules.

## Writing Concept Definitions

Every concept starts with a natural language definition. This definition serves two audiences: developers who build with your pipeline, and the LLMs that process your knowledge.

### Basic Concept Definition

The simplest way to define a concept is with a descriptive sentence:

```toml
[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Employee = "A person employed by an organization"
ProductReview = "A customer's evaluation of a product or service"
```

**Key principles for concept definitions:**

1. **Define what it is, not what it's for**
   ```toml
   # ❌ Wrong: includes usage context
   TextToSummarize = "Text that needs to be summarized"
   
   # ✅ Right: defines the essence
   Article = "A written composition on a specific topic"
   ```

2. **Use singular forms**
   ```toml
   # ❌ Wrong: plural form
   Invoices = "Commercial documents from sellers"
   
   # ✅ Right: singular form
   Invoice = "A commercial document issued by a seller to a buyer"
   ```

3. **Avoid unnecessary adjectives**
   ```toml
   # ❌ Wrong: includes subjective qualifier
   LongArticle = "A lengthy written composition"
   
   # ✅ Right: neutral definition
   Article = "A written composition on a specific topic"
   ```

### Organizing Related Concepts

Group concepts that naturally belong together in the same domain. A domain acts as a namespace for a set of related concepts and pipes, helping you organize and reuse your pipeline components. You can learn more about them in [Kick off a Knowledge Pipeline Project](kick-off-a-knowledge-pipeline-project.md#what-are-domains).

```toml
# pipelex_libraries/pipelines/finance.toml
domain = "finance"
description = "Financial document processing"

[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Receipt = "Proof of payment for goods or services"
PurchaseOrder = "A buyer's formal request to purchase goods or services"
PaymentTerms = "Conditions under which payment is to be made"
LineItem = "An individual item or service listed in a financial document"
```

## Adding Structure with Python Models

While text definitions help LLMs understand your concepts, Python models ensure structured, validated outputs. This combination gives you the best of both worlds: AI flexibility with software reliability.

**Important**: If you don't create a Python class for a concept, it defaults to text-based content. Only create Python models when you need structured output with specific fields.

### Creating Your First Structured Model

For each concept that needs structured output, create a corresponding Python class:

```python
# pipelex_libraries/pipelines/finance.py
from datetime import datetime
from typing import List, Optional
from pydantic import Field
from pipelex.core.stuffs.stuff_content import StructuredContent

class Invoice(StructuredContent):
    invoice_number: str
    issue_date: datetime
    due_date: datetime
    vendor_name: str
    customer_name: str
    total_amount: float = Field(ge=0, description="Total invoice amount")
    currency: str = Field(default="USD", description="Three-letter currency code")
    line_items: List[str] = Field(default_factory=list)
```

The model name must match the concept name exactly: `Invoice` concept → `Invoice` class.

### Basic Validation Examples

Use Pydantic's validation features to ensure data quality:

```python
from pydantic import field_validator
from pipelex.core.stuffs.stuff_content import StructuredContent

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

class ProductReview(StructuredContent):
    product_name: str
    reviewer_name: str
    rating: int = Field(ge=1, le=5, description="Rating from 1 to 5 stars")
    review_text: str
    verified_purchase: bool = False
```

### Working with Optional Fields

Not all data is always available. Use Optional fields with sensible defaults:

```python
from typing import Optional
from datetime import datetime
from pipelex.core.stuffs.stuff_content import StructuredContent

class Meeting(StructuredContent):
    title: str
    scheduled_date: datetime
    duration_minutes: int = Field(ge=15, le=480, description="Meeting duration")
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    is_recurring: bool = False
```

### Linking Concepts to Models

The connection between TOML definitions and Python models happens automatically through naming:

```toml
# pipelex_libraries/pipelines/hr.toml
domain = "hr"

[concept]
Employee = "A person employed by an organization"
Meeting = "A scheduled gathering of people for discussion"
PerformanceReview = "An evaluation of an employee's work performance"
Department = "An organizational unit within a company"  # No Python model => text-based
```

```python
# pipelex_libraries/pipelines/hr.py
from pipelex.core.stuffs.stuff_content import StructuredContent
from datetime import datetime
from typing import List, Optional

# Only define models for concepts that need structure
class Employee(StructuredContent):
    name: str
    email: str
    department: str
    hire_date: datetime

class Meeting(StructuredContent):
    title: str
    scheduled_date: datetime
    duration_minutes: int
    attendees: List[str]

class PerformanceReview(StructuredContent):
    employee_name: str
    review_period: str
    rating: int = Field(ge=1, le=5)
    strengths: List[str]
    areas_for_improvement: List[str]

# Note: Department concept has no Python model, so it's text-based
```

## Concept Refinement and Inheritance

Sometimes concepts build on each other. A `Contract` is a kind of `Document`. A `NonCompeteClause` is a specific part of a `Contract`. Pipelex lets you express these relationships.

### Declaring Concept Refinement

Use the `refines` field to indicate when one concept is a more specific version of another:

```toml
[concept]
Document = "A written or printed record"

[concept.Contract]
definition = "A legally binding agreement between parties"
refines = "Document"

[concept.EmploymentContract]
definition = "A contract between an employer and employee"
refines = "Contract"

[concept.NonCompeteClause]
definition = "A contract clause restricting competitive activities"
refines = "ContractClause"
```

### Why Refinement Matters

Concept refinement helps in two ways:

1. **Semantic clarity**: Makes relationships between concepts explicit
2. **Pipeline flexibility**: Pipes accepting general concepts can work with refined ones

For example, a pipe that processes `Document` can also process `Contract` or `EmploymentContract`:

```toml
[pipe.extract_key_points]
PipeLLM = "Extract main points from any document"
inputs = { doc = "Document" }  # Can accept Document, Contract, or EmploymentContract
output = "KeyPoints"
```

### Practical Refinement Example

Here's a complete example showing concept refinement in action:

```toml
# pipelex_libraries/pipelines/content.toml
domain = "content"

[concept]
Text = "Written content in natural language"

[concept.Article]
definition = "A written composition on a specific topic"
refines = "Text"

[concept.NewsArticle]
definition = "An article reporting current events"
refines = "Article"

[concept.OpinionPiece]
definition = "An article expressing personal views"
refines = "Article"

[pipe.summarize_text]
PipeLLM = "Create a summary of any text"
inputs = { content = "Text" }  # Works with Text, Article, NewsArticle, etc.
output = "Summary"

[pipe.extract_facts]
PipeLLM = "Extract factual claims from news"
inputs = { article = "NewsArticle" }  # Specifically requires news articles
output = "FactualClaims"
```

### Structure Inheritance in Python

While TOML refinement is primarily semantic, you can mirror these relationships in Python when both concepts need structure:

```python
# pipelex_libraries/pipelines/content.py
from pipelex.core.stuffs.stuff_content import StructuredContent
from datetime import datetime
from typing import Optional, List

# Base Article with structure
class Article(StructuredContent):
    title: str
    content: str
    author: str
    word_count: int = Field(ge=1)

# NewsArticle inherits and extends Article's structure
class NewsArticle(Article):
    publication_date: datetime
    news_category: str
    sources: List[str] = Field(default_factory=list)
    breaking_news: bool = False

# OpinionPiece also inherits and extends
class OpinionPiece(Article):
    opinion_type: str  # e.g., "editorial", "column", "review"
    disclaimer: Optional[str] = None

# Note: Text, Summary, and FactualClaims have no Python models,
# so they remain text-based concepts
```

With well-defined concepts—both in natural language and code—your pipelines gain clarity, reliability, and maintainability. Next, we'll see how to build pipes that transform these concepts.
