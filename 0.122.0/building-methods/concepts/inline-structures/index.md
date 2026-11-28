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
- **default_value**: Default value applied when the field is omitted. A field cannot declare both `required = true` and a `default_value` — a default makes absence legal, which contradicts requiring the field, so the pair is rejected at validation. A defaulted field never holds nothing: a value that sets it to `null` is refused, so leave the key out to get the default
- **choices**: For `enum`-like fields, a list of valid values, each a string or an option table — see [Choice Fields](#choice-fields-enums)
- **item_type**: For `list` fields, the type of list items
- **key_type** and **value_type**: For `dict` fields, the types of keys and values
- **concept_ref** and **item_concept_ref**: For `concept` fields (and `list` fields whose items are concepts), the concept being referenced
- **hints**: Non-normative presentation intent for this field — see [Intent Hints](intent-hints.md)
- **minimum**, **maximum**, **exclusive_minimum**, **exclusive_maximum**, **min_length**, **max_length**, **pattern**, **format**, **unit**, **aggregate** and **examples**: The field's contract facts — see [Contract Facts](#contract-facts)

`item_type` and `value_type` take one of the field types above (`text`, `integer`, `number`, `boolean`, `date`, `datetime`, `time`, `list`, `dict`, `concept`) or `Any`, for values whose type is genuinely unspecified. Any other name is refused when the method loads, a concept's name included: a list of concepts is `item_type = "concept"` with its `item_concept_ref`.

Field names must be valid Python identifiers and cannot be Python keywords; generated Python projections use them as model attributes.

A field may share its name with a Python type or with a name the generated class uses, such as `date = { type = "date", ... }`, `str`, `list` or `Field`: the structure class Pipelex builds for the concept when it loads the method imports every such name under an alias (`date: _date = Field(...)`), so the field neither hides its own type nor the types of the fields after it. The Python targets of [`pipelex codegen`](../../under-the-hood/codegen-projections.md), `python-structures` and `python-pydantic`, do not alias these names yet, so for a structure with such a field they write Python types that fail at import; the `ts-zod` target, which writes each field as an object key, is unaffected. The one name a structure cannot take is the name Pipelex gives the Python class of a concept the structure refers to, `<domain>__<Concept>` (a field named `shop__Item` in a structure that holds a `shop.Item`): validation refuses it with a `method.concept_invalid` error naming the concept and the field.

!!! warning "The key set is closed"

    The keys above are the only ones a structure field accepts, and anything else is rejected at validation. A typo (`descrption`), a hopeful key the language does not carry (`placeholder`, `step`), or a misspelled `hints` all fail the bundle instead of being dropped.

    This is deliberate: a silently discarded key is authored intent that vanishes without a trace, and you only find out when the value it was supposed to govern comes back wrong. Note that hint *content* stays lenient: an unknown key inside a `hints` table warns and is preserved, rather than failing the bundle.

## Contract Facts

A field may state facts about its value. The **constraints** refuse a value that breaks them: the runtime enforces them on every value of the field, the field's JSON Schema states them, and a dry run's mock values satisfy them. The **descriptions** never refuse a value: they tell a reader or a renderer what the value means.

```toml
[concept.Invoice.structure]
reference = { type = "text", description = "The invoice reference", pattern = "^INV-[0-9]{6}$", examples = ["INV-000123"] }
quantity = { type = "integer", description = "How many units", minimum = 1, maximum = 999 }
share = { type = "number", description = "The discount", unit = "percent", exclusive_minimum = 0, maximum = 100 }
amount = { type = "number", description = "The line amount", unit = "EUR", aggregate = "sum" }
contact = { type = "text", description = "Who to write to", format = "email" }
```

| Fact | Kind | Applies to |
|---|---|---|
| `minimum`, `maximum`, `exclusive_minimum`, `exclusive_maximum` | constraint | number-valued fields (`integer`, `number`); a bound on an `integer` field is an integer |
| `min_length`, `max_length` | constraint | text-valued fields, counted in characters |
| `pattern` | constraint | text-valued fields: a regular expression searched in the value, as JSON Schema does, so anchor it with `^` and `$` to match the whole value |
| `format` | constraint | text-valued fields: `email`, `uri`, `date-time`, `uuid`, `hostname`, `ipv4` or `ipv6` |
| `unit` | description | number-valued fields: an ISO 4217-shaped currency code such as `EUR`, `percent`, or a unit of measure such as `m`, `kg` or `h` |
| `aggregate` | description | number-valued fields: `sum` or `average`, how the values of a column of records combine |
| `examples` | description | any value class (text, number, date, time): a list of values of the field, each satisfying its constraints |

A list, a dict, a boolean and an enumeration field belong to no value class and take no fact. A `concept` field takes the value class of its concept: a field typed `Number` takes the number facts, one typed `Text` the text facts, and one typed by a structured concept none. A concept refining `Number` may state a `unit` itself, which its refinements inherit and a field may override:

```toml
[concept.Amount]
description = "An amount of money"
refines = "Number"
unit = "EUR"
```

A fact that does not apply where it is written, two facts that contradict each other (an empty range, `minimum` beside `exclusive_minimum`, `min_length` above `max_length`), a pattern that does not compile, an unknown unit, format or aggregate, and an example or a default that breaks the field's constraints are all refused with the error type `contract_fact_invalid`, whose parameters name the `fact`, the `reason` and the `field_path`.

A pattern runs against values a caller sends, so the runtime keeps it from holding a run:

- **Each search has a time limit of a tenth of a second.** A pattern you mean answers in microseconds; only one that backtracks catastrophically, such as `^(a|aa)+$`, whose branches can match the same characters in many ways, reaches the limit. A value whose search is stopped is refused as breaking the pattern, never let through unchecked, and a pattern that cannot be searched in its own example or default within the limit is refused as `malformed`. Write each part so that a character can match only one way: `^a+$` rather than `^(a|aa)+$`. The values a caller sends for one input, the items of a list included, share one second of search time at the run's entry pipe, so a long list of values that each take just under the limit is refused once that second is spent rather than holding the run for as many tenths of a second as it has items.
- **Counted repetitions are bounded.** A pattern whose counts, written out and multiplied through nested groups, pass 10,000 positions, such as `(ab){1000000}`, is refused as `malformed`: the engine that searches it would hold memory in proportion to the counts. `{0,1000000}` writes out nothing and is accepted.
- **A dry run's mock text holds at most 100,000 characters.** A field whose `min_length` passes that bound has no mock that satisfies it, so its dry run refuses the mock as it would any value that breaks the field.
- **A dry run mocks a text from its `examples`, else by drawing from its `pattern`.** The draw reads atomic groups and possessive repeats in their plain form and checks each draw against the pattern; a pattern it cannot draw from, such as one holding a conditional `(?(1)…|…)`, is mocked from the field's `examples`, so give such a field an example, or its dry run reports `method.mock_unsatisfiable`. A number mock keeps integers exact, so an integer bound or example past a float's precision is honoured.

## All-Optional Structures and the `input_presence_vacuous` Lint

`required` defaults to **`false`** in the long form, and this is the difference between the two spellings that is easiest to miss:

```toml
[concept.RunOptions.structure]
tone  = "The tone to use"                                        # shorthand: a REQUIRED text field
depth = { type = "integer", description = "How deep to go" }     # long form: OPTIONAL, because required defaults to false
```

A structure written entirely in the long form with no `required = true` anywhere is **all-optional**: its payload admits `{}`. That is perfectly legal, and often exactly right — an extraction concept that records whatever a document happens to state should not demand any particular field. A structure table holding *no* field at all is the degenerate case of the same thing — its payload admits only `{}` — and the lint below names it in its own words.

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

A field may name a concept declared in the same bundle, in another bundle loaded into the same library (in the same load or an earlier one), or in a method package the bundle depends on, written with the package's address: `concept_ref = "github.com/acme/crm-methods/crm->crm.Customer"`. A method package is loaded when one of the bundle's pipes references it, so a field alone does not bring a package in. A concept in a method package sees only that package's own concepts.

Two things refuse the load rather than failing later, when the concept is first used:

- **A cycle between concepts**, such as `A` holding a `B` that holds an `A`, including a concept that holds itself.
- **A field naming a concept that cannot be found**, because no bundle the concept can see declares it. A concept declared only by a bundle loaded afterwards cannot be found either.

A method package's own dependencies are never loaded, so a concept in the package that names one of their concepts is not refused. It fails when first used, and so does any concept holding it.

## Choice Fields (Enums)

For fields that should only accept specific values, use the `choices` property. When using `choices`, you don't need to specify a `type`.

```toml
[concept.Task.structure]
title = "Task title"
priority = { choices = ["low", "medium", "high"], description = "Task priority level" }
status = { choices = ["todo", "in_progress", "done"], description = "Current status", default_value = "todo" }
```

An option may be a table giving its value the words a person reads in its place: a `label`, a `description` and a `tone`, one of `positive`, `caution`, `negative` and `neutral`. Plain strings and tables mix freely, and a table carrying `value` alone is the same option as its string:

```toml
[concept.Review.structure]
decision = { description = "What to do with the contract", choices = [
  { value = "sign", label = "Sign it", tone = "positive" },
  { value = "negotiate", label = "Negotiate first", tone = "caution", description = "Some clauses need changes" },
  "reject",
] }
```

An option table needs a non-empty `value`, shares neither its value nor its label with another option, and carries no other key; a `choices` list needs at least one option. A list of plain strings that repeats a value or holds an empty one is accepted with a `choice_option_dubious` warning. An enumeration field takes no contract fact.

## Required Fields

Fields declared with the explicit inline-table form are **optional by default** (`required = false`). To make one mandatory, explicitly set `required = true`. Note that fields declared with the shorthand string syntax (`field_name = "description"`) are **required**:

```toml
[concept.User.structure]
username = { type = "text", description = "Username", required = true }
email = { type = "text", description = "Email address", required = true }
bio = { type = "text", description = "User bio" }  # Optional (default)
```

In this example, `username` and `email` are mandatory, while `bio` is optional.

Only an optional field with no `default_value` may hold nothing, and it is the only kind of field a value may set to `null`. A required field refuses `null`, a required field naming `native.Anything` included, which takes any value but `null`, and so does a defaulted one. This is the rule a [binding step](../pipes/understanding-optionality.md#binding-steps-under-absence) reading a field relies on: binding a required or defaulted field never records an absence.

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
