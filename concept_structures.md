# Defining Concept Structures in Pipelex

## Introduction

Pipelex provides a powerful feature that allows you to define structured concepts directly within your `.plx` pipeline files using inline TOML syntax. This eliminates the need to create separate Python files for simple to moderately complex data structures, streamlining your workflow and keeping all pipeline definitions in one place.

**Quick Example:**

```plx
domain = "finance"
description = "Financial document processing"

[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
issue_date = { type = "date", description = "The date the invoice was issued", required = true }
total_amount = { type = "number", description = "The total invoice amount", required = true }
vendor_name = "The name of the vendor"
line_items = { type = "list", item_type = "text", description = "List of items in the invoice", required = false }
```

Behind the scenes, Pipelex automatically generates a fully-typed Pydantic model that inherits from `StructuredContent`, giving you structured LLM outputs with validation—all from TOML.

## How Inline Structures Work

When you define a concept structure inline, Pipelex performs the following steps automatically:

1. **Parsing**: The TOML parser reads `[concept.ConceptName.structure]` sections from your `.plx` file
2. **Blueprint Creation**: Each field definition is converted into a `ConceptStructureBlueprint` object that specifies the field's type, description, requirements, and defaults
3. **Code Generation**: The `StructureGenerator` class dynamically generates Python source code for a complete Pydantic class that inherits from `StructuredContent`
4. **Class Creation**: The generated Python code is executed to create an actual class at runtime
5. **Registration**: The new class is automatically registered in Pipelex's `class_registry`, making it available throughout your pipelines

This entire process is transparent to you—you write TOML, and Pipelex handles the rest.

## Syntax and Examples

### Simple Field Definitions

The simplest way to define a field is with a string description. This creates a required text field:

```plx
[concept.Person]
description = "Information about a person"

[concept.Person.structure]
name = "The person's full name"
email = "The person's email address"
```

### Detailed Field Definitions

For more control, use inline tables with explicit field properties:

```plx
[concept.Employee]
description = "Information about an employee"

[concept.Employee.structure]
employee_id = { type = "integer", description = "Unique employee identifier", required = true }
name = { type = "text", description = "Employee's full name", required = true }
hire_date = { type = "date", description = "Date of hire", required = true }
department = { type = "text", description = "Department name", required = false, default_value = "General" }
is_active = { type = "boolean", description = "Employment status", required = false, default_value = true }
salary = { type = "number", description = "Annual salary", required = false }
```

### Supported Field Types

Inline structures support the following field types:

- **text**: String values
- **integer**: Whole numbers
- **boolean**: True/false values
- **number**: Numeric values (integers or floats)
- **date**: Date and datetime values
- **list**: Arrays/lists of items (specify `item_type`)
- **dict**: Dictionary/map structures (specify `key_type` and `value_type`)

### Field Properties

Each field can specify:

- **type**: The data type (required for detailed definitions)
- **description**: Human-readable description of the field
- **required**: Whether the field is mandatory (default: `true`)
- **default_value**: Default value if not provided
- **choices**: For enum-like fields, a list of valid values
- **item_type**: For list fields, the type of list items
- **key_type** and **value_type**: For dict fields, the types of keys and values

### Complex Type Examples

**List Fields:**

```plx
[concept.Project]
description = "A software project"

[concept.Project.structure]
name = "Project name"
tags = { type = "list", item_type = "text", description = "Project tags", required = false }
team_members = { type = "list", item_type = "text", description = "Team member names", required = true }
```

**Dictionary Fields:**

```plx
[concept.Configuration]
description = "Application configuration"

[concept.Configuration.structure]
app_name = "Application name"
settings = { type = "dict", key_type = "text", value_type = "text", description = "Configuration settings", required = false }
```

**Choice Fields:**

```plx
[concept.Task]
description = "A task to be completed"

[concept.Task.structure]
title = "Task title"
priority = { choices = ["low", "medium", "high"], description = "Task priority level", required = true }
status = { choices = ["todo", "in_progress", "done"], description = "Current status", default_value = "todo" }
```

### Mixed Syntax Example

You can mix simple string definitions with detailed inline tables in the same structure:

```plx
[concept.Article]
description = "A blog article"

[concept.Article.structure]
title = "The article title"
author = "The author's name"
word_count = { type = "integer", description = "Number of words", required = false }
published_date = { type = "date", description = "Publication date", required = true }
tags = { type = "list", item_type = "text", description = "Article tags", required = false }
is_featured = { type = "boolean", description = "Whether article is featured", default_value = false }
```

## Advantages of Inline Structures

### Rapid Development

- **Single File**: Keep concepts, structures, and pipes all in one `.plx` file
- **No Context Switching**: No need to jump between `.plx` and `.py` files
- **Quick Iteration**: Modify structures instantly without managing separate Python files

### Simplicity

- **Declarative Syntax**: Straightforward TOML that's easy to read and write
- **No Boilerplate**: No need for Python imports, class definitions, or field declarations
- **Automatic Registration**: Generated classes are automatically discovered and registered

### Type Safety

- **Pydantic Models**: Behind the scenes, you get full Pydantic v2 models
- **Runtime Validation**: Automatic validation of structured outputs from LLMs
- **Type Hints**: Generated classes include proper type annotations

### Developer Experience

- **Less Code to Maintain**: Fewer files, less boilerplate
- **Clear and Readable**: TOML structure definitions are self-documenting
- **Perfect for Prototyping**: Ideal for getting started quickly
- **Good for Simple to Medium Complexity**: Handles most common use cases

## Current Limitations

### Concept Refinement Restrictions

Currently, inline structures can only be used for concepts that:

- Don't refine other concepts, OR
- Refine native concepts only: `Text`, `Image`, `PDF`, `TextAndImages`, `Number`, `Page`

You cannot use inline structures to refine custom (non-native) concepts. This limitation may be removed in future versions.

### Feature Constraints

Inline structures cannot provide:

- **Custom Methods**: No ability to define methods or computed properties
- **Complex Validation**: No custom validators or cross-field validation logic
- **Advanced Pydantic Features**:
  - `@field_validator` decorators
  - `@model_validator` decorators
  - Custom serializers/deserializers
  - `@property` methods
  - Class methods or static methods
- **Nested Custom Concepts**: Cannot reference other custom concepts as field types (coming soon - see roadmap below)
- **Inheritance Hierarchies**: Cannot create class inheritance beyond the base `StructuredContent`

### Tooling Limitations

- **IDE Support**: Limited autocomplete compared to explicit Python classes
- **Static Type Checking**: Type checkers like `mypy` or `pyright` won't validate inline structures as thoroughly (static code generation coming soon - see roadmap below)
- **Refactoring**: Less IDE refactoring support for inline structures
- **Documentation**: No docstrings or inline documentation beyond descriptions

## Future Roadmap

The Pipelex team is actively working on enhancing inline structures with powerful new capabilities:

### Nested Custom Concepts (Coming Soon)

Currently, inline structures only support native types and references to native concepts. Soon, you'll be able to reference other custom concepts as field types:

```plx
[concept.Address]
description = "A postal address"

[concept.Address.structure]
street = "Street address"
city = "City name"
postal_code = "Postal or ZIP code"

[concept.Company]
description = "A company with an address"

[concept.Company.structure]
name = "Company name"
headquarters = { type = "Address", description = "Company headquarters address", required = true }
```

This will enable building complex, nested data models entirely within `.plx` files.

## When to Use Explicit Python Classes

While inline structures are convenient, there are scenarios where creating an explicit Python `StructuredContent` class is the better choice.

### Use Python Classes When You Need:

#### 1. Complex Validation Logic

When your data requires custom validation that goes beyond field types:

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field, field_validator

class Invoice(StructuredContent):
    """A commercial invoice with validation."""
    
    total_amount: float = Field(ge=0, description="Total invoice amount")
    tax_amount: float = Field(ge=0, description="Tax amount")
    net_amount: float = Field(ge=0, description="Net amount before tax")
    
    @field_validator('tax_amount')
    @classmethod
    def validate_tax(cls, v, info):
        """Ensure tax doesn't exceed total."""
        total = info.data.get('total_amount', 0)
        if v > total:
            raise ValueError('Tax amount cannot exceed total amount')
        return v
    
    @field_validator('net_amount')
    @classmethod
    def validate_net_amount(cls, v, info):
        """Verify net_amount + tax_amount = total_amount."""
        total = info.data.get('total_amount', 0)
        tax = info.data.get('tax_amount', 0)
        expected = total - tax
        if abs(v - expected) > 0.01:  # Allow small floating point differences
            raise ValueError(f'Net amount should be {expected}, got {v}')
        return v
```

#### 2. Computed Properties

When you need derived values or methods:

```python
from datetime import datetime
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Subscription(StructuredContent):
    """A subscription with computed properties."""
    
    start_date: datetime = Field(description="Subscription start date")
    end_date: datetime = Field(description="Subscription end date")
    monthly_price: float = Field(ge=0, description="Monthly subscription price")
    
    @property
    def duration_days(self) -> int:
        """Calculate subscription duration in days."""
        return (self.end_date - self.start_date).days
    
    @property
    def total_cost(self) -> float:
        """Calculate total subscription cost."""
        months = self.duration_days / 30.0
        return months * self.monthly_price
    
    def is_active_on(self, date: datetime) -> bool:
        """Check if subscription is active on a given date."""
        return self.start_date <= date <= self.end_date
```

#### 3. Reusability Across Domains

When the structure needs to be shared:

```python
# shared_models.py
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Address(StructuredContent):
    """A reusable address structure."""
    
    street: str = Field(description="Street address")
    city: str = Field(description="City name")
    state: str = Field(description="State or province")
    postal_code: str = Field(description="Postal/ZIP code")
    country: str = Field(default="USA", description="Country")

# Can now be imported and used in multiple domains/projects
```

#### 4. Advanced Type Features

When you need sophisticated typing:

```python
from typing import Literal
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class ApiResponse(StructuredContent):
    """A flexible API response structure."""
    
    status: Literal["success", "error", "pending"]
    data: dict | None = Field(default=None, description="Response data")
    error_message: str | None = Field(default=None, description="Error details if status is error")
    metadata: dict[str, str | int | float] = Field(default_factory=dict, description="Additional metadata")
```

#### 5. Better Developer Experience

When your team prefers:

- Full IDE autocomplete and type hints
- Static type checking with `mypy` or `pyright`
- Comprehensive docstrings
- Explicit, self-documenting code
- Better refactoring support

## Using AI Agents to Create Python Classes

One of the major advantages of the modern development workflow is that **AI coding assistants make creating Python classes nearly as fast as writing TOML**. Tools like Cursor AI, GitHub Copilot, and other AI-powered IDEs understand Pipelex patterns and can generate proper `StructuredContent` classes instantly.

### The Best of Both Worlds

You don't have to choose between inline structures and Python classes from the start. Instead, follow this pragmatic approach:

1. **Prototype Fast**: Start with inline structures for rapid development
2. **Validate Quickly**: Test your pipelines and iterate on the structure
3. **Upgrade When Needed**: When complexity grows, convert to Python classes
4. **Let AI Help**: Use AI assistants to generate the Python code automatically

### Example Workflow

**Step 1: Start with inline structure**

```plx
[concept.UserProfile]
description = "A user profile"

[concept.UserProfile.structure]
username = "The user's username"
email = "The user's email address"
age = { type = "integer", description = "User's age", required = false }
```

**Step 2: Run and test your pipeline**

Iterate quickly, adjusting the structure as needed.

**Step 3: When you need validation, ask your AI assistant**

> "Convert this inline UserProfile structure to a Python StructuredContent class with email validation"

**Step 4: AI generates the class**

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field, field_validator
import re

class UserProfile(StructuredContent):
    """A user profile with validation."""
    
    username: str = Field(description="The user's username")
    email: str = Field(description="The user's email address")
    age: int | None = Field(default=None, description="User's age")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v
    
    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        """Validate age range."""
        if v is not None and (v < 0 or v > 150):
            raise ValueError('Age must be between 0 and 150')
        return v
```

**Step 5: Update your .plx file**

```plx
[concept]
UserProfile = "A user profile"  # Structure now defined in Python
```

The Python class is automatically discovered and registered by Pipelex.

### AI Assistant Capabilities

Modern AI coding assistants can:

- Generate complete `StructuredContent` classes from descriptions
- Add appropriate validators and validation logic
- Convert inline TOML structures to Python classes
- Suggest improvements and best practices
- Handle complex type annotations
- Add docstrings and documentation
- Follow Pydantic v2 patterns

This means you get the **development speed of inline structures** with the **power and flexibility of Python classes** when you need them.

## Migration Path

### From Inline Structure to Python Class

Here's a step-by-step guide to migrate from inline structures to explicit Python classes:

**1. Identify the concept to migrate**

Let's say you have this inline structure:

```plx
domain = "ecommerce"

[concept.Product]
description = "A product in the catalog"

[concept.Product.structure]
product_id = { type = "integer", description = "Unique product ID", required = true }
name = "Product name"
price = { type = "number", description = "Product price", required = true }
in_stock = { type = "boolean", description = "Stock availability", default_value = true }
categories = { type = "list", item_type = "text", description = "Product categories", required = false }
```

**2. Create a Python file for structures**

Create `ecommerce_struct.py` in your project:

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Product(StructuredContent):
    """A product in the catalog."""
    
    product_id: int = Field(description="Unique product ID")
    name: str = Field(description="Product name")
    price: float = Field(ge=0, description="Product price")
    in_stock: bool = Field(default=True, description="Stock availability")
    categories: list[str] | None = Field(default=None, description="Product categories")
```

**3. Remove the inline structure from .plx**

Update your `.plx` file:

```plx
domain = "ecommerce"

[concept]
Product = "A product in the catalog"

# Structure section removed - now defined in ecommerce_struct.py
```

**4. Verify automatic discovery**

Pipelex automatically discovers and registers `StructuredContent` classes. No manual registration needed.

**5. Test your pipeline**

Run your pipeline to ensure everything works. The behavior should be identical, but now you have the flexibility to add custom logic.

**6. Add enhancements (optional)**

Now you can add validators, computed properties, or other Python features:

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field, field_validator

class Product(StructuredContent):
    """A product in the catalog."""
    
    product_id: int = Field(description="Unique product ID")
    name: str = Field(description="Product name")
    price: float = Field(ge=0, description="Product price")
    in_stock: bool = Field(default=True, description="Stock availability")
    categories: list[str] | None = Field(default=None, description="Product categories")
    
    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        """Ensure price is positive and reasonable."""
        if v < 0:
            raise ValueError('Price cannot be negative')
        if v > 1_000_000:
            raise ValueError('Price seems unreasonably high')
        return v
    
    @property
    def display_price(self) -> str:
        """Format price for display."""
        return f"${self.price:.2f}"
```

## Recommendation: Start Simple, Grow as Needed

The inline structure feature is a **practical solution for the majority of use cases**. It allows you to:

- Get started quickly without Python overhead
- Keep all pipeline logic in one place
- Iterate rapidly during development
- Still get full type safety and validation

When your needs grow beyond what inline structures can provide, **explicit Python `StructuredContent` classes offer more power and flexibility**. With AI coding assistants, creating these classes is fast and easy, giving you the best of both worlds.

**Guidelines:**

- ✅ **Use inline structures** for straightforward data models
- ✅ **Use inline structures** during prototyping and early development
- ✅ **Use inline structures** for domain-specific models with simple validation
- ✅ **Use Python classes** when you need custom validation logic
- ✅ **Use Python classes** for reusable, shared data models
- ✅ **Use Python classes** when you need computed properties or methods
- ✅ **Use Python classes** for complex type relationships

Remember: You can always start with inline structures and migrate to Python classes later. The migration is straightforward, and AI assistants can help you make the transition quickly.

