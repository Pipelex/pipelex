# PipeFunc

The `PipeFunc` operator provides an essential escape hatch, allowing you to execute arbitrary Python code from within a pipeline. This is useful for custom data manipulation, complex logic, or integrating with external services not supported by other operators.

## How it works

`PipeFunc` operates by calling a Python function that has been registered with Pipelex's central function registry.

1.  **Function Registration**: First, you must define a standard Python function and register it with a unique name. This is done once when your application starts up.
2.  **Function Signature**: The registered function **must** accept a single argument: `working_memory: WorkingMemory`. This object provides access to all the data currently available in the pipeline.
3.  **Execution**: When the `PipeFunc` pipe is executed, it looks up your function by its registered name and calls it, passing in the current `working_memory`.
4.  **Returning Data**: The function can return data, which `PipeFunc` will then place back into the working memory, associated with the pipe's `output` concept.

### Return values

Your Python function can return one of the following:
-   A `StuffContent` object (e.g., `TextContent`, `ImageContent`, or a custom `StructuredContent` model).
-   A `list` of `StuffContent` objects.
-   A simple Python `str`, which will be automatically converted to a `TextContent`.

## How to Register a Function

To make a Python function available to `PipeFunc`, you must register it using the global `func_registry`.

Here is an example of a function and its registration:

```python
# in a file like my_custom_functions.py

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.tools.func_registry import func_registry

def concatenate_texts(working_memory: WorkingMemory) -> TextContent:
    """
    Retrieves two text stuffs, concatenates them, and returns a new text stuff.
    """
    # Get data from working memory using the names from previous steps
    text1 = working_memory.get_stuff_as_str("text_a")
    text2 = working_memory.get_stuff_as_str("text_b")

    concatenated = f"{text1} -- {text2}"

    return TextContent(text=concatenated)

def register_my_functions():
    """This function should be called at application startup."""
    func_registry.register_function(concatenate_texts, name="combine_two_texts")

```

You would then call `register_my_functions()` when your Pipelex application initializes.

## Configuration

Once the function is registered, you can use it in your `.plx` file.

### PLX Parameters

| Parameter       | Type   | Description                                                                 | Required |
| --------------- | ------ | --------------------------------------------------------------------------- | -------- |
| `type`          | string | The type of the pipe: `PipeFunc`                                                                          | Yes      |
| `definition`   | string | A description of the function operation.                                                                   | Yes      |
| `function_name` | string | The unique name used to register the Python function (e.g., "combine_two_texts"). | Yes      |
| `output`        | string | The concept to associate with the function's return value.                  | Yes      |

### Example

This PLX snippet shows how to use the `combine_two_texts` function defined above. It assumes two previous pipes have produced outputs named `text_a` and `text_b`.

```plx
[pipe.combine_them]
type = "PipeFunc"
definition = "Combine two text inputs using a custom Python function"
function_name = "combine_two_texts"
output = "ConcatenatedText"
```
