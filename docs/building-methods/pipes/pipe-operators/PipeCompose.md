---
description: "PipeCompose renders Jinja2 templates or constructs structured objects from working memory. Combine pipeline data into new outputs deterministically."
---

# PipeCompose

The `PipeCompose` operator composes data from your pipeline's working memory into new outputs. It supports two modes:

1. **Template mode**: Render templates to produce `Text`-like output
2. **Construct mode**: Build structured objects by mapping fields from inputs

In both modes, `PipeCompose` produces a single output stuff: the `output` concept cannot carry multiplicity (`output = "Report[]"` is rejected at validation).

## Template Mode

Template mode uses [Jinja2 templates](https://jinja.palletsprojects.com/) to dynamically generate text by combining data from working memory. This is ideal for creating formatted reports, HTML content, or constructing complex, multi-part prompts for LLMs.

### How Template Mode Works

`PipeCompose` takes all the data currently in the `WorkingMemory` and uses it as the context for rendering a Jinja2 template. The resulting text is then saved back to the working memory as a new `Text` or `Html` output. In template mode, the `output` concept must refine the native `Text` or `Html` concept — use construct mode for structured outputs.

Template mode supports two syntax variants:

- **Simple**: `template = "Hello $name"` — an inline string, defaults to `basic` category
- **Rich**: A `[pipe.name.template]` section with `template`, `category`, and optionally `templating_style`

### Template Context

The Jinja2 template has access to all the "stuffs" currently in the working memory. You can access them by the names they were given in previous pipeline steps. For example, if a previous step produced an output named `user_profile`, you can access its attributes in the template like `{{ user_profile.name }}` or `{{ user_profile.email }}`.

### Template Mode Configuration

| Parameter       | Type              | Description                                                                 | Required |
| --------------- | ----------------- | --------------------------------------------------------------------------- | -------- |
| `type`          | string            | The type of the pipe: `PipeCompose`                                         | Yes      |
| `description`   | string            | A description of the operation                                              | Yes      |
| `inputs`        | table             | Input variables needed for the template                                     | No       |
| `output`        | string            | The concept for the output                                                  | Yes      |
| `template`      | string or section | An inline template string, or a `[pipe.name.template]` section (see below)  | Yes*     |

*Template mode requires `template`. When using the rich form (`[pipe.name.template]` section), the following sub-fields are available:

| Sub-field          | Type   | Description                                                                      | Required |
|--------------------|--------|----------------------------------------------------------------------------------|----------|
| `template`         | string | The Jinja2 template string                                                       | Yes      |
| `category`         | string | Template category: `basic`, `markdown`, `html`, `mermaid`                        | Yes      |
| `templating_style` | table  | How `\| tag` and `\| format` render in this template: `{ tag_style = "...", text_format = "..." }`. Omit it to use the runtime default — see [Templating Style](../../templating-style.md) | No       |
| `extra_context`    | table  | Additional key-value pairs merged into the template rendering context             | No       |

### Template Mode Examples

**Simple inline template:**

```toml
[pipe.compose_greeting]
type = "PipeCompose"
description = "Compose a greeting message"
inputs = { user = "User" }
output = "Text"
template = "Hello $user.name, welcome to our platform!"
```

**Markdown template with category:**

```toml
[pipe.compose_report]
type = "PipeCompose"
description = "Format data as a markdown report"
inputs = { summary = "Text", items = "Item[]" }
output = "Text"

[pipe.compose_report.template]
category = "markdown"
template = """
# Report

$summary

{% for item in items %}
- {{ item.name }}: {{ item.value }}
{% endfor %}
"""
```

**HTML template with templating style:**

```toml
[pipe.format_html_report]
type = "PipeCompose"
description = "Format data as HTML"
inputs = { summary = "Text", items = "Item[]" }
output = "Html"

[pipe.format_html_report.template]
category = "html"
templating_style = { tag_style = "xml", text_format = "html" }
template = """
<h1>Report</h1>
<p>{{ summary }}</p>
<ul>
{% for item in items %}
  <li>{{ item.name }}: {{ item.value }}</li>
{% endfor %}
</ul>
"""
```

## Construct Mode

Construct mode builds structured objects by mapping fields from inputs. Use this when you need to assemble a complex output concept from multiple inputs without using an LLM.

### How Construct Mode Works

Instead of rendering a template, construct mode creates a structured object by specifying how each field should be populated. Fields can be:

- **Referenced from inputs**: Copy a value from working memory
- **Templated**: Generate a string using template interpolation
- **Fixed**: Use a static value

### Construct Mode Configuration

| Parameter     | Type   | Description                                               | Required |
| ------------- | ------ | --------------------------------------------------------- | -------- |
| `type`        | string | The type of the pipe: `PipeCompose`                       | Yes      |
| `description` | string | A description of the operation                            | Yes      |
| `inputs`      | table  | Input variables needed for the construct                  | No       |
| `output`      | string | The structured concept to output                          | Yes      |
| `construct`   | section| Field mappings (see below)                                | Yes*     |

*Either `template` or `construct` must be provided, but not both.

### Construct Field Methods

Each field in the `[pipe.name.construct]` section can use one of these methods:

| Method | Syntax | Description |
|--------|--------|-------------|
| Reference | `{ from = "input.field" }` | Copy value from input variable or nested field |
| Template | `{ template = "text with $var" }` | Generate string using template interpolation |
| Fixed | `"value"`, `123`, `true`, or `["a", "b"]` | Use a static value directly (scalars and lists) |
| Nested | a table with sub-fields (no `from`/`template` key) | Recursively compose a nested structured object |

A nested construct is written as a table whose keys are the sub-object's own field names — each sub-field uses any of the four methods, recursively:

```toml
[pipe.assemble_invoice.construct]
customer = { name = { from = "order.customer_name" }, tier = "standard" }
```

A `from` reference also accepts one modifier, `list_to_dict_keyed_by`: when the target field is a dict, it converts the referenced list into a dict keyed by the named attribute of each item:

```toml
[pipe.index_products.construct]
products_by_sku = { from = "products", list_to_dict_keyed_by = "sku" }
```

The referenced value must be a list, and every item must carry the key attribute with a string value — otherwise the composer raises an error.

### Copying Whole Inputs Into Native Fields

The `from` reference is not limited to dotted paths like `"customer.name"` — it can name a whole input variable. When the referenced input is a native stuff (`Text`, `Number`, `YesNo`, `Date`, `Time`, or a list of them) and the target field is native-typed, the composer automatically converts the content wrapper into the field's native value. This works for required and optional fields alike.

Conversion matrix:

| Source input | Native target field | Composed value |
|---|---|---|
| `Text` | `type = "text"` | the text string |
| `Number` | `type = "number"` | the number |
| `YesNo` | `type = "boolean"` | the boolean |
| `Date` | `type = "date"` | the date |
| `Time` | `type = "time"` | the time of day |
| `Text[]` | `type = "list"`, `item_type = "text"` | the list of strings |
| `Number[]` | `type = "list"`, `item_type = "number"` | the list of numbers |
| `YesNo[]` | `type = "list"`, `item_type = "boolean"` | the list of booleans |
| `Date[]` | `type = "list"`, `item_type = "date"` | the list of dates |
| `Time[]` | `type = "list"`, `item_type = "time"` | the list of times of day |

When the target field expects a content object rather than a native value (e.g. a field typed with a concept), the object is kept as-is — the conversion only fires when the field expects the native type.

One fidelity guard: a `Date` stuff that carries a time of day cannot be copied into a bare `date` field — that would silently drop the time and its UTC offset, so the composer raises an error instead. Target a `Date`-typed field to keep the full timestamp. The same guard applies per item when copying a `Date[]` into a list of `date` items.

`Time` needs no such guard, and the asymmetry is deliberate: a `Time` is a single value that carries its UTC offset inside the time itself, so copying it into a `time` field is lossless and nothing can be dropped. In the other direction, a whole `Date` does not convert into a `time` field at all — that would drop the date. Use a dotted path instead, `{ from = "deadline.time" }`, to take the time of day out of a `Date`.

Worked example — assembling a report from whole stuffs produced by earlier steps:

```toml
[concept.ScreeningReport]
description = "The final screening report"

[concept.ScreeningReport.structure]
match_score = { type = "number", description = "The match score", required = true }
rejection_email = { type = "text", description = "The rejection email — optional" }
interview_questions = { type = "list", item_type = "text", description = "Questions to ask — optional" }

[pipe.assemble_report]
type = "PipeCompose"
description = "Assemble the screening report from previously generated pieces"
inputs = { score = "Number", email = "Text", questions = "Text[]" }
output = "ScreeningReport"

[pipe.assemble_report.construct]
match_score = { from = "score" }
rejection_email = { from = "email" }
interview_questions = { from = "questions" }
```

Here `email` is a whole `Text` stuff copied into an optional `text` field, `questions` is a whole `Text[]` stuff copied into an optional `list` of `text` items, and `score` is a whole `Number` stuff copied into a required `number` field. Each lands as its native value (`str`, `list[str]`, `float`).

### Construct Mode Example

```toml
[pipe.assemble_invoice]
type = "PipeCompose"
description = "Assemble invoice from order and customer data"
inputs = { order = "Order", customer = "Customer" }
output = "Invoice"

[pipe.assemble_invoice.construct]
invoice_number = { template = "INV-$order.id" }
customer_name = { from = "customer.name" }
customer_email = { from = "customer.email" }
line_items = { from = "order.items" }
total = { from = "order.total" }
status = "pending"
version = 1
```

In this example:

- `invoice_number` is generated from a template using the order ID
- `customer_name`, `customer_email`, `line_items`, and `total` are copied from inputs
- `status` and `version` are fixed values

## Choosing Between Modes

| Use Case | Mode |
|----------|------|
| Generate text reports, emails, prompts | Template |
| Create HTML content | Template |
| Assemble structured data from multiple sources | Construct |
| Combine fields from different inputs into one object | Construct |
| Need to map/rename fields | Construct |

## Related Documentation

- [Working Memory](../working-memory.md) - How pipes access and share data
- [Provide Inputs](../provide-inputs.md) - Passing inputs to pipes and pipelines
- [Templating Style](../../templating-style.md) - Tag styles and text formats, and the runtime default
