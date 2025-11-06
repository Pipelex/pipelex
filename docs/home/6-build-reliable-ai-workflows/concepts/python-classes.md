# Python StructuredContent Classes

For advanced features beyond inline structures, create explicit Python classes that inherit from `StructuredContent`. This approach gives you full Pydantic power with custom validation, computed properties, and reusable business logic.

For most use cases, start with [Inline Structures](inline-structures.md) first. This guide shows when and how to use Python classes for more advanced needs.

## When to Use Python Classes

Use Python classes when you need:

1. **Custom validation logic** - Cross-field validation, complex rules
2. **Computed properties** - Derived values, formatted outputs
3. **Custom methods** - Business logic, helper functions
4. **Reusability** - Shared structures across multiple domains
5. **Advanced typing** - `Literal`, complex unions, etc.
6. **Better IDE support** - Full autocomplete and type checking

## Basic Python Class Example

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Invoice(StructuredContent):
    """A commercial invoice."""
    
    invoice_number: str = Field(description="Unique invoice identifier")
    issue_date: datetime = Field(description="Date the invoice was issued")
    total_amount: float = Field(ge=0, description="Total invoice amount")
    vendor_name: str = Field(description="Name of the vendor")
    line_items: list[str] = Field(default_factory=list, description="List of items")
```

Classes inheriting from `StructuredContent` are automatically discovered and registered by Pipelex.

!!! warning "Module Execution During Auto-Discovery"
    When Pipelex discovers `StructuredContent` classes, it imports the module containing them. **Any code at the module level (outside functions/classes) will be executed during import.** This can have unintended side effects.
    
    **Best practice:** Keep your `StructuredContent` classes in dedicated modules (e.g., `*_struct.py` files) with minimal module-level code, or ensure module-level code is safe to execute during discovery.

## With Custom Validation

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
```

## With Computed Properties

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
```

## Using AI to Create Python Classes

Modern AI coding assistants like Cursor AI and GitHub Copilot can generate `StructuredContent` classes instantly, making the transition from inline structures to Python classes fast and easy.

### Recommended Workflow

Follow this pragmatic approach:

1. **Prototype Fast**: Start with inline structures for rapid development
2. **Validate Quickly**: Test your pipelines and iterate on the structure
3. **Upgrade When Needed**: Convert to Python classes when you need advanced features
4. **Let AI Help**: Use AI assistants to generate the Python code automatically

### Example: AI-Assisted Migration

**Step 1: Start with inline structure**

```plx
[concept.UserProfile]
description = "A user profile"

[concept.UserProfile.structure]
username = "The user's username"
email = "The user's email address"
age = { type = "integer", description = "User's age", required = false }
```

**Step 2: Ask your AI assistant**

> "Convert this inline UserProfile structure to a Python StructuredContent class with email validation"

**Step 3: AI generates the class**

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
```

**Step 4: Update your .plx file**

```plx
[concept]
UserProfile = "A user profile"  # Structure now defined in Python
```

The Python class is automatically discovered and registered.

## Migration Guide

### From Inline Structure to Python Class

Here's how to migrate when you need more advanced features:

**1. You have this inline structure:**

```plx
domain = "ecommerce"

[concept.Product]
description = "A product in the catalog"

[concept.Product.structure]
product_id = { type = "integer", description = "Unique product ID", required = true }
name = "Product name"
price = { type = "number", description = "Product price", required = true }
in_stock = { type = "boolean", description = "Stock availability", default_value = true }
```

**2. Create a Python file** (e.g., `ecommerce_struct.py`):

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Product(StructuredContent):
    """A product in the catalog."""
    
    product_id: int = Field(description="Unique product ID")
    name: str = Field(description="Product name")
    price: float = Field(ge=0, description="Product price")
    in_stock: bool = Field(default=True, description="Stock availability")
```

**3. Update your `.plx` file:**

```plx
domain = "ecommerce"

[concept]
Product = "A product in the catalog"

# Structure section removed - now defined in ecommerce_struct.py
```

**4. Test your pipeline** - The behavior should be identical.

**5. Add enhancements** (optional):

```python
class Product(StructuredContent):
    """A product in the catalog."""
    
    product_id: int = Field(description="Unique product ID")
    name: str = Field(description="Product name")
    price: float = Field(ge=0, description="Product price")
    in_stock: bool = Field(default=True, description="Stock availability")
    
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

## Recommendations

### Guidelines

- ✅ **Start with inline structures** for straightforward data models
- ✅ **Use inline structures** during prototyping and early development
- ✅ **Use inline structures** for domain-specific models with simple validation
- ✅ **Upgrade to Python classes** when you need custom validation logic
- ✅ **Use Python classes** for reusable, shared data models
- ✅ **Use Python classes** when you need computed properties or methods
- ✅ **Use Python classes** for complex type relationships

Remember: You can always start with inline structures and migrate to Python classes later. The migration is straightforward, and AI assistants can help you make the transition quickly.

### The Pragmatic Approach

The inline structure feature is a **practical solution for the majority of use cases**. Use it to:

- Get started quickly without Python overhead
- Keep all pipeline logic in one place
- Iterate rapidly during development
- Still get full type safety and validation

When your needs grow, **Python `StructuredContent` classes offer more power and flexibility**.

## Related Documentation

- [Inline Structures](inline-structures.md) - Fast prototyping with TOML
- [Define Your Concepts](define_your_concepts.md) - Learn about concept semantics and naming
- [Writing Workflows Tutorial](../../2-get-started/pipe-builder.md) - Get started with structured outputs

