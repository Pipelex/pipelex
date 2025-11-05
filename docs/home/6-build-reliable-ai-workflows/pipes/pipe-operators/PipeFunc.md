# PipeFunc

The `PipeFunc` operator provides an essential escape hatch, allowing you to execute arbitrary Python code from within a pipeline. This is useful for custom data manipulation, complex logic, or integrating with external services not supported by other operators.

## How it works

`PipeFunc` operates by calling a Python function that has been registered with Pipelex's central function registry.

1.  **Decorator Required**: Functions must be decorated with `@pipe_func()` to be discovered and registered (since v0.12.0).
2.  **Automatic Discovery**: Functions with the `@pipe_func()` decorator are automatically discovered from anywhere in your project when Pipelex starts up.
3.  **Function Signature**: Eligible functions are registered using their function name (or a custom name) as the registry key.
4.  **Execution**: When the `PipeFunc` pipe is executed, it looks up your function by name and calls it, passing in the current `working_memory`.
5.  **Returning Data**: The function returns data, which `PipeFunc` places back into the working memory, associated with the pipe's `output` concept.

## Function Eligibility Requirements

For a function to be automatically registered and available to `PipeFunc`, it **must** meet all of the following criteria:

!!! warning "Function Eligibility Requirements"

- **Must be decorated with** `@pipe_func()` (required since v0.12.0)
- **Must be an async function** (defined with `async def`)
- **Must have exactly 1 parameter** named `working_memory`
- **Parameter type must be** `WorkingMemory`
- **Return type must be** a subclass of `StuffContent` (or a generic type like `ListContent[SomeType]`)
- **Must be discoverable** (not in excluded directories like `.venv`, `__pycache__`, etc.)

### Return values

Your async Python function can return:

-   A `StuffContent` object (e.g., `TextContent`, `ImageContent`, or a custom `StructuredContent` model).
-   A `ListContent` containing `StuffContent` objects.

## How to Create a Function

To make a Python function available to `PipeFunc`:

1. Add the `@pipe_func()` decorator to your function
2. Place the function anywhere in your project (it will be auto-discovered)
3. Ensure it meets all eligibility requirements

!!! warning "Module Execution During Auto-Discovery"
    When Pipelex discovers functions with `@pipe_func()`, it imports the module containing them. **Any code at the module level (outside functions/classes) will be executed during import.** This can have unintended side effects.
    
    **Best practice:** Keep your `@pipe_func()` functions in dedicated modules with minimal module-level code, or ensure module-level code is safe to execute during discovery.

Here is an example of an eligible function:

```python
# in any Python file in your project (e.g., my_project/custom_functions.py)

from pipelex.system.registries.func_registry import pipe_func
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent

@pipe_func()  # Required decorator for auto-discovery
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

### Custom Registration Name

You can optionally specify a custom name for registration:

```python
@pipe_func(name="custom_concat")
async def concatenate_texts(working_memory: WorkingMemory) -> TextContent:
    # Implementation...
    pass
```

Then use `function_name = "custom_concat"` in your `.plx` file.

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
