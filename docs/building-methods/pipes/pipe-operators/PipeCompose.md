---
description: "PipeCompose renders Jinja2 templates or constructs structured objects from working memory. Combine pipeline data into new outputs deterministically."
---

# PipeCompose

The `PipeCompose` operator composes data from your pipeline's working memory into new outputs. It supports two modes:

1. **Template mode**: Render templates to produce `Text`-like output
2. **Construct mode**: Build structured objects by mapping fields from inputs

## Template Mode

Template mode uses [Jinja2 templates](https://jinja.palletsprojects.com/) to dynamically generate text by combining data from working memory. This is ideal for creating formatted reports, HTML content, or constructing complex, multi-part prompts for LLMs.

### How Template Mode Works

`PipeCompose` takes all the data currently in the `WorkingMemory` and uses it as the context for rendering a Jinja2 template. The resulting text is then saved back to the working memory as a new `Text` or `Html` output.

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
| `inputs`        | table             | Input variables needed for the template                                     | Yes      |
| `output`        | string            | The concept for the output                                                  | No       |
| `template`      | string or section | An inline template string, or a `[pipe.name.template]` section (see below)  | Yes*     |

*Template mode requires `template`. When using the rich form (`[pipe.name.template]` section), the following sub-fields are available:

| Sub-field          | Type   | Description                                                                      | Required |
|--------------------|--------|----------------------------------------------------------------------------------|----------|
| `template`         | string | The Jinja2 template string                                                       | Yes      |
| `category`         | string | Template category: `basic`, `markdown`, `html`, `mermaid`                        | Yes      |
| `templating_style` | table  | Style options: `{ tag_style = "...", text_format = "..." }`                      | No       |
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
| `inputs`      | table  | Input variables needed for the construct                  | Yes      |
| `output`      | string | The structured concept to output                          | Yes      |
| `construct`   | section| Field mappings (see below)                                | Yes*     |

*Either `template` or `construct` must be provided, but not both.

### Construct Field Methods

Each field in the `[pipe.name.construct]` section can use one of these methods:

| Method | Syntax | Description |
|--------|--------|-------------|
| Reference | `{ from = "input.field" }` | Copy value from input variable or nested field |
| Template | `{ template = "text with $var" }` | Generate string using template interpolation |
| Fixed | `"value"` or `123` or `true` | Use a static value directly |

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
