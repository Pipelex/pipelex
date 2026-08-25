---
description: "Declare typed schemas directly in .mthds files with inline structures. Build structured AI workflows without Python boilerplate."
---

# Inline Structure Definition

Define structured concepts directly in your `.mthds` files using pipelex syntax. This is the **recommended approach** for most use cases, offering rapid development without Python boilerplate.

For an introduction to concepts themselves, see [Define Your Concepts](define_your_concepts.md). For advanced features requiring Python classes, see [Python StructuredContent Classes](python-classes.md).

## Quick Example

```toml
domain = "finance"

[concept.LineItem]
description = "A single line item in an invoice"

[concept.LineItem.structure]
product_name = { type = "text", description = "Name of the product", required = true }
quantity = { type = "integer", description = "Quantity ordered", required = true }
unit_price = { type = "number", description = "Price per unit", required = true }

[concept.Customer]
description = "A customer for an invoice"

[concept.Customer.structure]
name = { type = "text", description = "Customer's full name", required = true }
email = { type = "text", description = "Customer's email address", required = true }

[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
issue_date = { type = "date", description = "The date the invoice was issued", required = true }
customer = { type = "concept", concept_ref = "finance.Customer", description = "The customer for this invoice", required = true }
line_items = { type = "list", item_type = "concept", item_concept_ref = "finance.LineItem", description = "List of line items", required = true }
total_amount = { type = "number", description = "The total invoice amount", required = true }
```

Behind the scenes, Pipelex automatically generates fully-typed Pydantic models with validation—all from TOML. Nested concepts are fully supported!

!!! tip "Generate Python Classes from Inline Structures"
    Want type hints and IDE autocomplete? Use the `pipelex build structures` command to generate Python classes from your inline definitions:

    ```bash
    pipelex build structures ./my_pipelines/
    ```

    This gives you the best of both worlds: rapid prototyping in TOML, then Python classes when you need them.

## Field Properties

Each field can specify:

- **type**: The data type (required for detailed definitions)
- **description**: Human-readable description
- **required**: Whether the field must be present in the payload (defaults to `false`)
- **default_value**: Default value applied when the field is omitted. A field cannot declare both `required = true` and a `default_value` — a default makes absence legal, which contradicts requiring the field, so the pair is rejected at validation
- **choices**: For `enum`-like fields, a list of valid values
- **item_type**: For `list` fields, the type of list items
- **key_type** and **value_type**: For `dict` fields, the types of keys and values
- **concept_ref** and **item_concept_ref**: For `concept` fields (and `list` fields whose items are concepts), the concept being referenced
- **hints**: Non-normative presentation intent for this field — see [Intent Hints](intent-hints.md)

Field names must be valid Python identifiers and cannot be Python keywords; generated Python projections use them as model attributes.

!!! warning "The key set is closed"

    The keys above are the only ones a structure field accepts, and anything else is rejected at validation. A typo (`descrption`), a hopeful constraint the language does not carry (`minimum = 0`, `unit = "kg"`), or a misspelled `hints` all fail the bundle instead of being dropped.

    This is deliberate: a silently discarded key is authored intent that vanishes without a trace, and you only find out when the value it was supposed to govern comes back wrong. If you need a numeric bound or another constraint, express it on a Python class instead — see [Python Classes](python-classes.md), whose pydantic `Field(...)` metadata is read as an authored fact. Note that hint *content* stays lenient: an unknown key inside a `hints` table warns and is preserved, rather than failing the bundle.

## All-Optional Structures and the `input_presence_vacuous` Lint

`required` defaults to **`false`** in the long form, and this is the difference between the two spellings that is easiest to miss:

```toml
[concept.RunOptions.structure]
tone  = "The tone to use"                                        # shorthand: a REQUIRED text field
depth = { type = "integer", description = "How deep to go" }     # long form: OPTIONAL, because required defaults to false
```

A structure written entirely in the long form with no `required = true` anywhere is **all-optional**: its payload admits `{}`. That is perfectly legal, and often exactly right — an extraction concept that records whatever a document happens to state should not demand any particular field.

It becomes a problem at one place only: when such a concept is named by a **method input that must be supplied** — an input of the bundle's declared `main_pipe`, written without a `?`. The declaration says "the caller must provide this", but since the empty object satisfies the concept, the only thing it can enforce is that the caller provides `{}`. Nothing is actually demanded, and a form, an API client or a person filling the input in has no way to tell what to put there. Validation reports this as the advisory `input_presence_vacuous` warning — the bundle stays **valid**, the warning never flips the verdict.

There are two remedies, and which one is right depends on what you meant:

- **The method can run without it.** Mark the input optional: `opts = "RunOptions?"`. Now absence is a declared, handled outcome rather than an empty object.
- **The method genuinely needs something in it.** Give the concept at least one required field — either `required = true` on the field that matters, or the shorthand form, which is required by definition.

The lint looks one level deep and only at entry pipes. A slot on an inner pipe is fed by dataflow, not by a caller, so it is never warned about; and a required field that is *itself* an all-optional concept is not warned about either.

## Supported Field Types

Inline structures support these field types:

### text

String values. Use for any text content.

```toml
[concept.Person.structure]
email = { type = "text", description = "Email address" }
```

!!! tip "Simple Syntax Shorthand"
    When you write `field_name = "description"`, Pipelex automatically creates a **text** field with:
    
    - **type**: `text`
    - **description**: The string you provided
    - **required**: `true`
    
    This is a shorthand for the most common case: required text fields. To make a text field optional, use the explicit form instead, e.g. `email = { type = "text", description = "Email address" }`.

### integer

Whole numbers (no decimals). Use for counts, IDs, ages, etc.

```toml
[concept.Product.structure]
product_id = { type = "integer", description = "Unique product ID" }
quantity = { type = "integer", description = "Stock quantity", default_value = 0 }
```

### boolean

True/false values. Use for flags, states, toggles.

```toml
[concept.Account.structure]
is_active = { type = "boolean", description = "Account status" }
is_verified = { type = "boolean", description = "Email verified", default_value = false }
```

### number

Numeric values (integers or floats). Use for prices, measurements, scores.

```toml
[concept.Invoice.structure]
total_amount = { type = "number", description = "Total amount" }
tax_rate = { type = "number", description = "Tax rate as decimal", default_value = 0.0 }
```

### date

A calendar date, no time of day. Generates a `datetime.date` field (JSON schema `format: date`). Use it for issue dates, due dates, dates of birth — anything you'd write as `2026-07-07`.

```toml
[concept.Event.structure]
event_date = { type = "date", description = "The date of the event" }
```

### datetime

A timestamp — a date *and* a time of day. Generates a `datetime.datetime` field (JSON schema `format: date-time`). Use it only when the time genuinely matters; a plain calendar date should be `date`, so the LLM is never forced to fabricate a time.

```toml
[concept.Event.structure]
created_at = { type = "datetime", description = "Creation timestamp" }
```

### time

A time of day, optionally with a UTC offset — no date attached. Generates a `datetime.time` field (JSON schema `format: time`). Use it for opening hours, schedules, recurring times — anything you'd write as `09:00:00` or `15:40:00+02:00`.

```toml
[concept.OpeningHours.structure]
opens_at = { type = "time", description = "Daily opening time" }
```

!!! note "Field type vs the native `Date` / `Time` concepts"
    A structure field's `date` / `datetime` / `time` type is a plain machine type — you pick one up front. If a field should keep *document fidelity* (a time only when the source states one), model it as `type = "concept", concept_ref = "Date"` instead: the native `Date` concept carries a required date plus an optional `time` field.

### list

Arrays/lists of items. **Must specify `item_type`** to indicate what the list contains.

```toml
[concept.Project.structure]
tags = { type = "list", item_type = "text", description = "Project tags" }
milestones = { type = "list", item_type = "text", description = "Milestone names" }
scores = { type = "list", item_type = "number", description = "Test scores" }
```

### dict

Dictionaries/maps with key-value pairs. **Must specify `key_type` and `value_type`**. Dictionary keys are text on the JSON wire, so `key_type` must be `"text"` (`"str"` remains accepted as a legacy spelling).

```toml
[concept.Configuration.structure]
settings = { type = "dict", key_type = "text", value_type = "text", description = "Config settings" }
metadata = { type = "dict", key_type = "text", value_type = "number", description = "Numeric metadata" }
```

### concept

References to other custom concepts. Use for nested structures and relationships between concepts.

**Single concept reference:**

```toml
[concept.Order.structure]
customer = { type = "concept", concept_ref = "myapp.Customer", description = "The customer placing the order" }
```

**List of concepts:**

```toml
[concept.Order.structure]
items = { type = "list", item_type = "concept", item_concept_ref = "myapp.OrderItem", description = "Items in the order" }
```

!!! note "Concept Reference Format"
    Use the format `domain.ConceptCode` (e.g., `"finance.Invoice"`) or just `ConceptCode` if the concept is in the same domain.

## Nested Concepts

Inline structures fully support concept-to-concept references, allowing you to build complex data models entirely in TOML.

### Single Concept Reference

Use `type = "concept"` with `concept_ref` to reference another concept:

```toml
[concept.Address]
description = "A physical address"

[concept.Address.structure]
street = { type = "text", description = "Street address", required = true }
city = { type = "text", description = "City name", required = true }
country = { type = "text", description = "Country", required = true }

[concept.Company]
description = "A company with headquarters"

[concept.Company.structure]
name = { type = "text", description = "Company name", required = true }
headquarters = { type = "concept", concept_ref = "myapp.Address", description = "Company headquarters" }
```

### List of Concepts

Use `type = "list"` with `item_type = "concept"` and `item_concept_ref` for lists of concepts:

```toml
[concept.Employee]
description = "An employee"

[concept.Employee.structure]
name = { type = "text", description = "Employee name", required = true }
role = { type = "text", description = "Job role", required = true }

[concept.Team]
description = "A team of employees"

[concept.Team.structure]
team_name = { type = "text", description = "Team name", required = true }
members = { type = "list", item_type = "concept", item_concept_ref = "myapp.Employee", description = "Team members", required = true }
lead = { type = "concept", concept_ref = "myapp.Employee", description = "Team lead" }
```

### Dependency Ordering

Pipelex automatically handles concept dependencies. You can define concepts in any order—Pipelex loads them in the correct sequence based on their relationships.

## Choice Fields (Enums)

For fields that should only accept specific values, use the `choices` property. When using `choices`, you don't need to specify a `type`.

```toml
[concept.Task.structure]
title = "Task title"
priority = { choices = ["low", "medium", "high"], description = "Task priority level" }
status = { choices = ["todo", "in_progress", "done"], description = "Current status", default_value = "todo" }
```

## Required Fields

Fields declared with the explicit inline-table form are **optional by default** (`required = false`). To make one mandatory, explicitly set `required = true`. Note that fields declared with the shorthand string syntax (`field_name = "description"`) are **required**:

```toml
[concept.User.structure]
username = { type = "text", description = "Username", required = true }
email = { type = "text", description = "Email address", required = true }
bio = { type = "text", description = "User bio" }  # Optional (default)
```

In this example, `username` and `email` are mandatory, while `bio` is optional.

## Generating Python Classes

The `pipelex build structures` command generates Python classes from your inline definitions. This is useful when you want:

- Type hints and IDE autocomplete
- To import the generated classes in your Python code
- A starting point before adding custom validation

### Usage

```bash
# Generate from a directory of .mthds files
pipelex build structures ./my_pipelines/

# Generate from a specific .mthds file
pipelex build structures ./my_pipeline/bundle.mthds

# Specify output directory
pipelex build structures ./my_pipelines/ -o ./generated/
```

### Example Output

Given the Invoice example from above, Pipelex generates one stamped `structures.py` module (plus a `codegen.lock` for the offline drift check) containing every concept of the closure:

```python
# generated/structures.py (below the codegen stamp header)
class Invoice(StructuredContent):
    """A commercial document issued by a seller to a buyer"""

    invoice_number: str = Field(..., description="The unique invoice identifier")
    issue_date: date = Field(..., description="The date the invoice was issued")
    customer: Customer = Field(..., description="The customer for this invoice")
    line_items: List[LineItem] = Field(..., description="List of line items")
    total_amount: float = Field(..., description="The total invoice amount")
```

You can then import and use these classes with full type safety. Generated files are never edited in place — to customize a class, subclass it in a sibling module (the generated header shows how).

## When to Use Inline Structures

**Inline structures are the recommended approach for most use cases.** They support:

- ✅ All basic field types (text, integer, number, boolean, date, datetime, list, dict)
- ✅ Nested concepts and complex relationships
- ✅ Choice fields (enums)
- ✅ Required/optional fields with defaults
- ✅ Full runtime validation

Use `pipelex build structures` when you additionally need:

- ✅ Type hints and IDE autocomplete in your Python code
- ✅ To import the classes in your application

Use hand-written Python classes when you need:

- ✅ Custom validation logic (e.g., cross-field validation)
- ✅ Computed properties
- ✅ Custom methods and business logic

See [Python StructuredContent Classes](python-classes.md) for advanced features.

## Related Documentation

- [Define Your Concepts](define_your_concepts.md) - Learn about concept semantics and naming
- [Python StructuredContent Classes](python-classes.md) - Advanced features with Python
- [MTHDS Language Tutorial](../../get-started/mthds-language-tutorial.md) - Get started with structured outputs
