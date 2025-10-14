# Coding Standards & Best Practices for Python Code

This document outlines the core coding standards, best practices, and quality control procedures for the codebase.

## Variables, loops and indexes

    - Variable names should have a minimum length of 3 characters. No exceptions: name your `for` loop indexes like `index_foobar`, your exceptions `exc` or more specific like `validation_error` when there are several layers of exceptions, and use `for key, value in ...` for key/value pairs.
    - When looping on the keys of a dict, use `for key in the_dict` rather than `for key in the_dict.keys()` otherwise you won't pass linting.
    - Avoid inline for loops, unless it's ultra-simple and holds on oneline.

## Enums and tests

    - When defining enums related to string values, always inherit from `StrEnum`
    - Never test equality to an enum value: use match/case, even to single out 1 case out of 10 cases. To avoid heavy match/case code in awkward places, add methods to the enum class such as `is_foobar()`. This is to avoid bugs: when new enum values are added we want the linter to complain. Use the `|` operator to group cases
    - As our match/case constructs over enums are always exhaustive, NEVER add a default `case _: ...`. Otherwise, you won't pass linting.

## Imports

### **Imports at the top of the file**

    - Import all necessary libraries at the top of the file
    - Do not import libraries in functions or classes unless in very specific cases, to be discussed with the user, as they would required a `# noqa: ...` comment to pass linting
    - Do not bother with ordering the imports, our Ruff linter will handle it for us. Same goes with removing unused imports.

- **Logging and Pretty Printing**:

    - Both `log()` and `pretty_print()` can be imported from `pipelex` directly:
    ```python
    from pipelex import log, pretty_print

    log.info("Hello, world!")
    ```
    - Both have a title arg which is handy when logging/printing objects:

    ```python
    log.debug("Hello, world!", title="Your first Pipelex log")
    pretty_print(output_object, title="Your first Pipelex output")
    ```
    - Both handle formatting json using Rich, pretty_print makes it prettier.

- **StrEnum and Self type**:

    - Both `StrEnum` and `Self` must be imported from `pipelex.types` (handles python retrocompatibility):
    ```python
    from pipelex.types import Self, StrEnum
    ```

## Typing

### **Always Use Type Hints**

    - Every function parameter must be typed
    - Every function return must be typed
    - Use type hints for all variables where type is not obvious
    - Use dict, list, tuple types with lowercase first letter: dict[], list[], tuple[]
    - Use type hints for all fields
    - Use Field(default_factory=...) for mutable defaults
    - Use `# pyright: ignore[specificError]` or `# type: ignore` only as a last resort. In particular, if you are sure about the type, you often solve issues by using cast() or creating a new typed variable.

### **BaseModel / Pydantic Standards**

    - Use `BaseModel` and respect Pydantic v2 standards
    - Use the modern `ConfigDict` when needed, e.g. `model_config = ConfigDict(extra="forbid", strict=True)`
    - Keep models focused and single-purpose
    - For list fields with non-string items in BaseModels, use `empty_list_factory_of()` to avoid linter complaints:
      ```python
      from pydantic import BaseModel, Field
      from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
      
      class MyModel(BaseModel):
          names: list[str] = Field(default_factory=list)  # OK for strings
          numbers: list[int] = Field(default_factory=empty_list_factory_of(int), description="A list of numbers")
          items: list[MyItem] = Field(default_factory=empty_list_factory_of(MyItem), description="A list of items")
      ```

## Factory Pattern

    - Use Factory Pattern for object creation when dealing with multiple implementations
    - Our factory methods are named `make_from_...` and such

## Error Handling

    - Always catch exceptions at the place where you can add useful context to it.
    - Use try/except blocks with specific exceptions
    - Convert third-party exceptions to our custom ones
    - NEVER catch the generic Exception, only catch specific exceptions, except at the root of CLI commands
    - NEVER raise generic exceptions like ValueError or TypeError, create new error classes and raise them instead
    - Always add `from exc` to the exception
   
   ```python
   try:
       self.models_manager.setup()
   except RoutingProfileLibraryNotFoundError as exc:
       msg = "The routing library could not be found, please call `pipelex init config` to create it"
       raise PipelexSetupError(msg) from exc
   ```

   **Note**: Following Ruff rules, we set the error message as a variable before raising it, for cleaner error traces.

## Documentation

1. **Docstring Format**
   ```python
   def process_image(image_path: str, size: tuple[int, int]) -> bytes:
       """Process and resize an image.
       
       Args:
           image_path: Path to the source image
           size: Tuple of (width, height) for resizing
           
       Returns:
           Processed image as bytes
       """
       pass
   ```

2. **Class Documentation**
   ```python
   class ImageProcessor:
       """Handles image processing operations.
       
       Provides methods for resizing, converting, and optimizing images.
       """
   ```

## Code Quality Checks

### Linting and Type Checking

Before finalizing a task, run:
```bash
make fix-unused-imports
make check
```

This runs multiple code quality tools:
- Pyright: Static type checking
- Ruff: Fast Python linter  
- Mypy: Static type checker

Always fix any issues reported by these tools before proceeding.

### Running Tests

1. **Quick Test Run** (no LLM/image generation):
   ```bash
   make tp
   ```
   Runs tests with markers: `(dry_runnable or not (inference or llm or img_gen or extract)) and not (needs_output or pipelex_api)`

2. **Specific Tests**:
   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

**Important**: Never run `make ti`, `make test-inference`, `make te`, `make test-extract`, `make tg`, or `make test-img-gen` - these use costly inference.

## Pipelines

- Always validate pipelines after creation/edit with `make validate`.
  Iterate if there are errors.

## Project Structure

- **Tests**: `tests/` directory
- **Documentation**: `docs/` directory
