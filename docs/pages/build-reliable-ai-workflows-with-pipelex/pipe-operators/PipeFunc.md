# PipeFunc

The `PipeFunc` operator provides an essential escape hatch, allowing you to execute arbitrary Python code from within a pipeline. This is useful for custom data manipulation, complex logic, or integrating with external services not supported by other operators.

## How it works

`PipeFunc` operates by calling a Python function that has been automatically registered with Pipelex's central function registry.

1.  **Automatic Registration**: Functions are automatically discovered and registered from Python files in the `pipelex/libraries/` directory when Pipelex starts up.
2.  **Function Signature**: Eligible functions are automatically registered using their function name as the registry key.
3.  **Execution**: When the `PipeFunc` pipe is executed, it looks up your function by name and calls it, passing in the current `working_memory`.
4.  **Returning Data**: The function returns data, which `PipeFunc` places back into the working memory, associated with the pipe's `output` concept.

## Function Eligibility Requirements

For a function to be automatically registered and available to `PipeFunc`, it **must** meet all of the following criteria:

!!! warning "Function Eligibility Requirements"
    - **Must be an async function** (defined with `async def`)
    - **Must have exactly 1 parameter** named `working_memory`
    - **Parameter type must be** `WorkingMemory`
    - **Return type must be** a subclass of `StuffContent` (or a generic type like `ListContent[SomeType]`)
    - **Must be defined in a Pipelex library file** within the `pipelines/` directory

### Return values

Your async Python function can return:
-   A `StuffContent` object (e.g., `TextContent`, `ImageContent`, or a custom `StructuredContent` model).
-   A `ListContent` containing `StuffContent` objects.

## How to Create a Function

To make a Python function available to `PipeFunc`, simply create it in any Python file within the `pipelex/libraries/` directory structure.

Here is an example of an eligible function:

```python
# in a file like pipelex/libraries/my_custom_functions.py

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import TextContent

async def concatenate_texts(working_memory: WorkingMemory) -> TextContent:
    """
    Retrieves two text stuffs, concatenates them, and returns a new text stuff.
    """
    # Get data from working memory using the names from previous steps
    text1 = working_memory.get_stuff_as_str("text_a")
    text2 = working_memory.get_stuff_as_str("text_b")

    concatenated = f"{text1} -- {text2}"

    return TextContent(text=concatenated)
```

The function will be automatically registered with the name `concatenate_texts` (the function name) when Pipelex starts up.

## Configuration

Once the function is registered, you can use it in your `.plx` file.

### PLX Parameters

| Parameter       | Type   | Description                                                                 | Required |
| --------------- | ------ | --------------------------------------------------------------------------- | -------- |
| `type`          | string | The type of the pipe: `PipeFunc`                                                                          | Yes      |
| `description`   | string | A description of the function operation.                                                                   | Yes      |
| `function_name` | string | The unique name used to register the Python function (e.g., "combine_two_texts"). | Yes      |
| `output`        | string | The concept to associate with the function's return value.                  | Yes      |

### Example

This PLX snippet shows how to use the `concatenate_texts` function defined above. It assumes two previous pipes have produced outputs named `text_a` and `text_b`.

```plx
[pipe.combine_them]
type = "PipeFunc"
description = "Combine two text inputs using a custom Python function"
function_name = "concatenate_texts"
output = "ConcatenatedText"
```
