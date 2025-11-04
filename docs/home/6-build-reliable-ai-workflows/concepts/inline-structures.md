# Inline Structure Definition

Define structured concepts directly in your `.plx` files using pipelex syntax. This is the **recommended approach** for most use cases, offering rapid development without Python boilerplate.

For an introduction to concepts themselves, see [Define Your Concepts](define_your_concepts.md). For advanced features requiring Python classes, see [Python StructuredContent Classes](python-classes.md).

## Quick Example

```plx
domain = "finance"

[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
issue_date = { type = "date", description = "The date the invoice was issued", required = true }
total_amount = { type = "number", description = "The total invoice amount", required = true }
vendor_name = "The name of the vendor"
line_items = { type = "list", item_type = "text", description = "List of items in the invoice", required = false }
```

Behind the scenes, Pipelex automatically generates a fully-typed Pydantic model with validation—all from TOML.

!!! warning "Important: Generated classes are not accessible"
    When you define an inline structure, Pipelex generates a Python class **behind the scenes**. However, **you do not have direct access to this generated class** in your Python code.
    
    This means:

    - You **cannot** import the generated class
    - You **cannot** use it for type hints in your Python code
    - You **cannot** access it when working with `PipeOutput` objects
    
    The class exists only for runtime validation. If you need to type your Python variables or access the class directly, use [Python StructuredContent Classes](python-classes.md) instead.

!!! warning "Important: No nested concepts (For Now)"
    Inline structures **cannot reference other custom concepts** as field types. You can only use basic types (text, integer, boolean, etc.) and native concepts.
    
    **Not allowed:**
    ```plx
    [concept.Address.structure]
    street = "Street address"
    
    [concept.Company.structure]
    headquarters = { type = "Address" }  # ❌ Cannot use custom concept
    ```
    
    If you need nested structures, use [Python StructuredContent Classes](python-classes.md).

## Field Properties

Each field can specify:

- **type**: The data type (required for detailed definitions)
- **description**: Human-readable description
- **default_value**: Default value if not provided
- **choices**: For `enum`-like fields, a list of valid values
- **item_type**: For `list` fields, the type of list items
- **key_type** and **value_type**: For `dict` fields, the types of keys and values

## Supported Field Types

Inline structures support these field types:

### text

String values. Use for any text content.

```plx
[concept.Person.structure]
email = { type = "text", description = "Email address" }
```

!!! tip "Simple Syntax Shorthand"
    When you write `field_name = "description"`, Pipelex automatically creates a **text** field with:
    
    - **type**: `text`
    - **description**: The string you provided
    
    This is a shorthand for the most common case: text fields.
    This will put the field as optional by default, and not required.

### integer

Whole numbers (no decimals). Use for counts, IDs, ages, etc.

```plx
[concept.Product.structure]
product_id = { type = "integer", description = "Unique product ID" }
quantity = { type = "integer", description = "Stock quantity", default_value = 0 }
```

### boolean

True/false values. Use for flags, states, toggles.

```plx
[concept.Account.structure]
is_active = { type = "boolean", description = "Account status" }
is_verified = { type = "boolean", description = "Email verified", default_value = false }
```

### number

Numeric values (integers or floats). Use for prices, measurements, scores.

```plx
[concept.Invoice.structure]
total_amount = { type = "number", description = "Total amount" }
tax_rate = { type = "number", description = "Tax rate as decimal", default_value = 0.0 }
```

### date

Date and datetime values. Pipelex handles date parsing automatically.

```plx
[concept.Event.structure]
event_date = { type = "date", description = "Event date and time" }
created_at = { type = "date", description = "Creation timestamp" }
```

### list

Arrays/lists of items. **Must specify `item_type`** to indicate what the list contains.

```plx
[concept.Project.structure]
tags = { type = "list", item_type = "text", description = "Project tags" }
milestones = { type = "list", item_type = "text", description = "Milestone names" }
scores = { type = "list", item_type = "number", description = "Test scores" }
```

### dict

Dictionaries/maps with key-value pairs. **Must specify `key_type` and `value_type`**.

```plx
[concept.Configuration.structure]
settings = { type = "dict", key_type = "text", value_type = "text", description = "Config settings" }
metadata = { type = "dict", key_type = "text", value_type = "number", description = "Numeric metadata" }
```

## Choice Fields (Enums)

For fields that should only accept specific values, use the `choices` property. When using `choices`, you don't need to specify a `type`.

```plx
[concept.Task.structure]
title = "Task title"
priority = { choices = ["low", "medium", "high"], description = "Task priority level" }
status = { choices = ["todo", "in_progress", "done"], description = "Current status", default_value = "todo" }
```

## Required Fields

By default, **all fields are optional** (`required = false`). To make a field mandatory, explicitly set `required = true`:

```plx
[concept.User.structure]
username = { type = "text", description = "Username", required = true }
email = { type = "text", description = "Email address", required = true }
bio = { type = "text", description = "User bio" }  # Optional (default)
```

In this example, `username` and `email` are mandatory, while `bio` is optional.

## When to Use Inline Structures

Use inline structures when:

- ✅ You need simple structured data with basic field types
- ✅ You want rapid prototyping without Python boilerplate
- ✅ Runtime validation is sufficient (you don't need type hints in Python)
- ✅ Your structures don't require nested custom concepts

Use Python classes when:

- ✅ You need custom validation logic or computed properties
- ✅ You want type hints and IDE autocomplete in your Python code
- ✅ You need nested structures or complex relationships
- ✅ You want to access the class directly in `PipeOutput`

See [Python StructuredContent Classes](python-classes.md) for advanced features.

## Related Documentation

- [Define Your Concepts](define_your_concepts.md) - Learn about concept semantics and naming
- [Python StructuredContent Classes](python-classes.md) - Advanced features with Python
- [Writing Workflows Tutorial](../../2-get-started/pipe-builder.md) - Get started with structured outputs

