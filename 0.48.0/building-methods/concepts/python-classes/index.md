# Python StructuredContent Classes

For advanced features beyond inline structures, create explicit Python classes that inherit from `StructuredContent`. This approach gives you full Pydantic power with custom validation, computed properties, and reusable business logic.

!!! tip "Start with Inline Structures"
    For most use cases, [Inline Structures](inline-structures.md) are the recommended approach. They support all field types including nested concepts, and you can generate Python classes from them using `pipelex build structures`.

    Use hand-written Python classes only when you need **custom validation logic**, **computed properties**, or **custom methods**.

## When to Use Python Classes

Most structured data needs are covered by inline structures + `pipelex build structures`. Use hand-written Python classes only when you need:

1. **Custom validation logic** - Cross-field validation, complex business rules
2. **Computed properties** - Derived values, formatted outputs
3. **Custom methods** - Business logic, helper functions
4. **Advanced Pydantic features** - `Literal`, complex unions, model validators

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

## Generating Python Classes Automatically

The easiest way to get Python classes is to use `pipelex build structures`:

```bash
pipelex build structures ./my_pipelines/
```

This generates a single stamped `structures.py` module from your inline definitions, giving you type hints and IDE autocomplete without writing boilerplate. Generated files are never edited in place — they are overwritten on every regeneration, and `pipelex codegen check` flags hand edits as drift.

### When You Need Custom Logic

If you need custom validation or computed properties, you have two options:

1. **Generate then subclass**: Run `pipelex build structures`, then subclass the generated class in a sibling module and add your custom logic there — never copy or edit the generated file; a subclass survives regeneration and stays in sync with the source concept
2. **Write from scratch**: Create a Python class manually with your custom logic

### Example: Adding Custom Validation

**Step 1: Start with inline structure**

```toml
[concept.UserProfile]
description = "A user profile"

[concept.UserProfile.structure]
username = "The user's username"
email = "The user's email address"
age = { type = "integer", description = "User's age", required = false }
```

**Step 2: Generate the base class**

```bash
pipelex build structures ./my_pipeline.mthds -o ./structures/
```

**Step 3: Subclass the generated class in a sibling module**

Never copy or edit the generated file — it is overwritten on regeneration. A subclass in a sibling module survives regeneration and inherits all the generated fields, so you only write the custom logic:

```python
# structures/user_profile_ext.py
import re

from pydantic import field_validator

from .structures import UserProfile


class ValidatedUserProfile(UserProfile):
    """A user profile with email validation."""

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v
```

**Step 4: Keep the inline structure in your `.mthds` file**

The inline structure remains the source of truth: on the next regeneration the base class is rewritten from it and your subclass picks up the changes automatically. At pipeline time the concept still resolves to the structure declared inline — apply your custom logic by validating with the subclass wherever your own code consumes the result (e.g. `ValidatedUserProfile.model_validate(profile.model_dump())`). If Pipelex itself must enforce the validation when producing the concept, move the structure to a hand-written class instead (see the [Migration Guide](#migration-guide) below).

## Migration Guide

### From Inline Structure to Python Class

Before migrating, check whether you need to migrate at all: if you only want custom logic on top of the structure, subclass the generated class in a sibling module (see above) and keep the inline structure as the source of truth. Migrate only when Pipelex itself must enforce your custom validation when producing the concept. In that case, write the Python class by hand — it becomes the source of truth:

**1. You have this inline structure:**

```toml
domain = "ecommerce"

[concept.Product]
description = "A product in the catalog"

[concept.Product.structure]
product_id = { type = "integer", description = "Unique product ID", required = true }
name = "Product name"
price = { type = "number", description = "Product price", required = true }
in_stock = { type = "boolean", description = "Stock availability", default_value = true }
```

**2. Write the Python class in your own module** with your custom logic:

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field, field_validator

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

**3. Update your `.mthds` file:**

```toml
domain = "ecommerce"

[concept]
Product = "A product in the catalog"

# Structure section removed - now defined in Python
```

**4. Test your pipeline** - The behavior should be identical, plus your custom validation.

## Recommendations

### The Recommended Workflow

1. **Start with inline structures** - Define your concepts entirely in TOML
2. **Generate Python classes when needed** - Use `pipelex build structures` for type hints and IDE support
3. **Add custom logic only when necessary** - Custom validation, computed properties, business methods

### When to Use Each Approach

| Need | Solution |
|------|----------|
| Rapid prototyping | Inline structures |
| Simple structured data | Inline structures |
| Nested concepts | Inline structures |
| Type hints in Python | `pipelex build structures` |
| IDE autocomplete | `pipelex build structures` |
| Custom validation | Hand-written Python class |
| Computed properties | Hand-written Python class |
| Business methods | Hand-written Python class |

## Related Documentation

- [Inline Structures](inline-structures.md) - Fast prototyping with TOML
- [Define Your Concepts](define_your_concepts.md) - Learn about concept semantics and naming
- [MTHDS Language Tutorial](../../get-started/mthds-language-tutorial.md) - Get started with structured outputs

