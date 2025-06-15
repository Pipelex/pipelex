# PipeCondition

The `PipeCondition` controller adds branching logic to your pipelines. It evaluates an expression and, based on the string result, chooses which subsequent pipe to execute from a map of possibilities.

## How it works

`PipeCondition` is a routing mechanism. Its execution flow is as follows:

1.  **Evaluate an Expression**: It takes an expression and renders it using Jinja2, with the full `WorkingMemory` available as context. This evaluation results in a simple string.
2.  **Look Up in Pipe Map**: The resulting string is used as a key to find a corresponding pipe name in the `pipe_map`.
3.  **Use Default (Optional)**: If the key is not found in the `pipe_map`, it will use the `default_pipe_code` if one is provided. If there's no match and no default, an error is raised.
4.  **Execute Chosen Pipe**: The chosen pipe is then executed. It receives the exact same `WorkingMemory` and inputs that were passed to the `PipeCondition` operator. The output of the chosen pipe becomes the output of the `PipeCondition` itself.

## Configuration

`PipeCondition` is configured in your pipeline's `.toml` file.

### TOML Parameters

| Parameter                      | Type           | Description                                                                                                                                              | Required                       |
| ------------------------------ | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `PipeCondition`                | string         | A descriptive name for the condition.                                                                           | Yes                            |
| `inputs`                       | dictionary     | The input concept(s) for the condition, as a dictionary mapping input names to concept codes.                                                     | Yes                            |
| `output`                       | string         | The output concept produced by the selected pipe.                                                | Yes                            |
| `expression`                   | string         | A simple Jinja2 expression. `{{ ... }}` are automatically added. Good for simple variable access like `"my_var.category"`.                                | Yes (or `expression_jinja2`)   |
| `expression_jinja2`            | string         | A full Jinja2 template string. Use this for more complex logic, like `{% if my_var.value > 10 %}high{% else %}low{% endif %}`.                           | Yes (or `expression`)          |
| `pipe_map`                     | table (dict)   | A mapping where keys are the possible string results of the expression, and values are the names of the pipes to execute.                                  | Yes                            |
| `default_pipe_code`            | string         | The name of a pipe to execute if the expression result does not match any key in `pipe_map`.                                                             | No                             |
| `add_alias_from_expression_to` | string         | An advanced feature. If provided, the string result of the expression evaluation is added to the working memory as an alias with this name.               | No                             |

### Example: Routing based on document type

Imagine a pipeline that needs to process invoices and receipts differently.

```toml
[pipe.classify_document_type]
PipeLLM = "Classify the document as 'invoice' or 'receipt'"
inputs = { document = "DocumentText" }
output = "DocumentClassification" # A structure with a 'type' field
prompt_template = """
Classify the document as 'invoice' or 'receipt'

@document
"""

[pipe.process_invoice]
# ... pipe definition ...
output = "ProcessedDocument"

[pipe.process_receipt]
# ... pipe definition ...
output = "ProcessedDocument"

[pipe.process_other]
# ... pipe definition ...
output = "ProcessedDocument"

# The PipeCondition definition
[pipe.route_by_doc_type]
PipeCondition = "Route document based on its classified type"
inputs = { classification = "DocumentClassification" }
output = "ProcessedDocument"
expression = "doc_classification.type" # Assumes input from a previous step was named 'doc_classification'

[pipe.route_by_doc_type.pipe_map]
invoice = "process_invoice"
receipt = "process_receipt"

[pipe.route_by_doc_type]
default_pipe_code = "process_other"
```

How this works:
1.  A previous step, `classify_document_type`, runs and its output is named `doc_classification`. This output is an object with a `type` attribute (e.g., `"invoice"`).
2.  `PipeCondition` evaluates the `expression`: `"doc_classification.type"`. Let's say it results in the string `"invoice"`.
3.  It looks up `"invoice"` in the `pipe_map` and finds the corresponding pipe: `"process_invoice"`.
4.  The `process_invoice` pipe is executed.
5.  If the classification had been `"letter"`, it would not match any key in the `pipe_map`, so the `default_pipe_code` `"process_other"` would be executed instead.

## Expression Types

### Simple Expression
```python
expression = "product_or_services_category.category"
```

- Direct access to working memory variables
- No template syntax needed
- Good for simple field access
- Access to Jinja2 filters and functions

## Features

### Default Routing
```python
default_pipe_code = "process_unknown"
```

- Fallback pipe when no match is found

### Expression Aliasing
```python
add_alias_from_expression_to = "category_type"
```

- Creates an alias from the expression result
- Makes the result available in working memory
