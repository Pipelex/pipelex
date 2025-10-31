# PipeCondition

The `PipeCondition` controller adds branching logic to your pipelines. It evaluates an expression and, based on the string result, chooses which subsequent pipe to execute from a map of possibilities.

## How it works

`PipeCondition` is a routing mechanism. Its execution flow is as follows:

1.  **Evaluate an Expression**: It takes an expression and renders it using Jinja2, with the full `WorkingMemory` available as context. This evaluation results in a simple string.
2.  **Look Up in Pipe Map**: The resulting string is used as a key to find a corresponding pipe name in the `pipe_map`.
3.  **Use Default (Optional)**: If the key is not found in the `pipe_map`, it will use the `default_pipe_code` if one is provided. If there's no match and no default, an error is raised.
4.  **Execute Chosen Pipe**: The chosen pipe is then executed. It receives the exact same `WorkingMemory` and inputs that were passed to the `PipeCondition` operator. The output of the chosen pipe becomes the output of the `PipeCondition` itself.

## Configuration

`PipeCondition` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter                      | Type           | Description                                                                                                                                              | Required                       |
| ------------------------------ | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `type`                         | string         | The type of the pipe: `PipeCondition`                                                                          | Yes                            |
| `description`                   | string         | A description of the condition operation.                                                                          | Yes                            |
| `inputs`                       | dictionary     | The input concept(s) for the condition, as a dictionary mapping input names to concept codes.                                                     | Yes                            |
| `output`                       | string         | The output concept produced by the selected pipe.                                                | Yes                            |
| `expression`                   | string         | A simple Jinja2 expression. `{{ ... }}` are automatically added. Good for simple variable access like `"my_var.category"`.                                | Yes (or `expression_template`)   |
| `expression_template`            | string         | A full Jinja2 template string. Use this for more complex logic, like `{% if my_var.value > 10 %}high{% else %}low{% endif %}`.                           | Yes (or `expression`)          |
| `pipe_map`                     | table (dict)   | A mapping where keys are the possible string results of the expression, and values are the names of the pipes to execute.                                  | Yes                            |
| `default_pipe_code`            | string         | The name of a pipe to execute if the expression result does not match any key in `pipe_map`.                                                             | No                             |
| `add_alias_from_expression_to` | string         | An advanced feature. If provided, the string result of the expression evaluation is added to the working memory as an alias with this name.               | No                             |

!!! important "Output Concept Matching"
    The output concept of the `PipeCondition` has to match the output of all the pipes in the `pipe_map`.

### Example: Simple routing based on category

Here's a basic example showing how PipeCondition routes based on input data:

```plx
domain = "routing_example"
description = "Example of PipeCondition routing"

[concept]
CategoryInput = "Input with a category field"

# Define the PipeCondition first
[pipe.route_by_category]
type = "PipeCondition"
description = "Route based on category field"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"

[pipe.route_by_category.pipe_map]
small = "process_small"
medium = "process_medium"
large = "process_large"

# Define the pipes that PipeCondition can route to
[pipe.process_small]
type = "PipeLLM"
description = "Handle small category"
output = "native.Text"
prompt = """
Output this only: "small"
"""

[pipe.process_medium]
type = "PipeLLM"
description = "Handle medium category"
output = "native.Text"
prompt = """
Output this only: "medium"
"""

[pipe.process_large]
type = "PipeLLM"
description = "Handle large category"
output = "native.Text"
prompt = """
Output this only: "large"
"""
```

How this works:
1. `PipeCondition` receives input data with a `category` field (e.g., `{category: "small"}`)
2. It evaluates the expression `"input_data.category"` which results in the string `"small"`
3. It looks up `"small"` in the `pipe_map` and finds the corresponding pipe: `"process_small"`
4. The `process_small` pipe is executed with the same working memory
5. The output from `process_small` becomes the output of the entire `PipeCondition`

### Example: Routing with default fallback

```plx
[pipe.route_with_fallback]
type = "PipeCondition"
description = "Route with default handling"
inputs = { classification = "DocumentType" }
output = "ProcessedDocument"
expression = "classification.type"
default_pipe_code = "process_unknown"

[pipe.route_with_fallback.pipe_map]
invoice = "process_invoice"
receipt = "process_receipt"

[pipe.process_invoice]
type = "PipeLLM"
description = "Process invoice documents"
inputs = { classification = "DocumentType" }
output = "ProcessedDocument"
prompt = """
Process this invoice document...
"""

[pipe.process_receipt]
type = "PipeLLM"
description = "Process receipt documents" 
inputs = { classification = "DocumentType" }
output = "ProcessedDocument"
prompt = """
Process this receipt document...
"""

[pipe.process_unknown]
type = "PipeLLM"
description = "Handle unknown document types"
inputs = { classification = "DocumentType" }
output = "ProcessedDocument"
prompt = """
Process this unknown document type...
"""
```

## Expression Types

### Simple Expression
```plx
expression = "input_data.category"
```

- Direct access to working memory variables
- No template syntax needed (`{{ }}` are automatically added)
- Good for simple field access
- Access to Jinja2 filters and functions

### Complex Expression  
```plx
expression_template = "{% if input_data.score >= 70 %}high{% else %}low{% endif %}"
```

- Full Jinja2 template syntax
- Conditional logic and loops
- Complex transformations
- Multiple variable access

## Features

### Default Routing
```python
default_pipe_code = "process_unknown"
```

- Fallback pipe when no match is found

### Expression Aliasing
```plx
add_alias_from_expression_to = "category_type"
```

- Creates an alias from the expression result
- Makes the result available in working memory
- Requires the target to exist in working memory beforehand
