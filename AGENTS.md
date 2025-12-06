<!-- BEGIN_PIPELEX_RULES -->
# Pipelex Coding Rules

## Codex Cloud Commands

### Linting

   After making code changes, you must always lint using `make check`.

   ```bash
   make format lint pyright mypy check-unused-imports check-config-sync check-rules pylint
   # If the current system doesn't have the `make` command, lookup the "check" target in the Makefile and run the command manually.
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fast Python linter  
   - Mypy: Static type checker
   - Other checks

   Always fix any issues reported by these tools before proceeding.

### Running Tests in Codex Cloud

    To test everything that can be tested from within the Codex Cloud sandbox, run this:

    ```bash
    make codex-tests
    # It's equivalent to running pytest with `-m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)"`
    # If some test fails, re-run it with `-s -vv` to see more details
    ```

---

### Prerequisites for running command lines: activate virtual environment

   **CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST activate the appropriate Python virtual environment. The only exceptions are our `make` commands which already include the env activation.

   Do this:

   ```bash
   source .venv/bin/activate
   pytest -s -v -k test_render_jinja2_from_text
   pipelex validate all
   ```

   or do that:

   ```bash
   .venv/bin/python -m pytest -s -v -k test_render_jinja2_from_text
   .venv/bin/pipelex validate all
   ```

   (adapt the above command to the OS and available virtual environment name)

   For standard installations, the virtual environment is named `.venv`. Always check this first:

   ```bash
   # Activate the virtual environment (standard installation)
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

   If the installation uses a different venv name or location, activate that one instead. All subsequent `pipelex` and `pytest` commands assume the venv is active.

## Coding Standards & Best Practices for Python Code

This document outlines the core coding standards, best practices, and quality control procedures for the codebase.

### Variables, loops and indexes

    - Variable names should have a minimum length of 3 characters. No exceptions: name your `for` loop indexes like `index_foobar`, your exceptions `exc` or more specific like `validation_error` when there are several layers of exceptions, and use `for key, value in ...` for key/value pairs.
    - When looping on the keys of a dict, use `for key in the_dict` rather than `for key in the_dict.keys()` otherwise you won't pass linting.
    - Avoid inline for loops, unless it's ultra-simple and holds on oneline.
    - If you have a variable that will get its value differently through different code paths, declare it first with a type, e.g. `pipe_code: str` but DO NOT give it a default value like `pipe_code: str = ""` unless it's really justified. We want the variable to be unbound until all paths are covered, and the linters will help us avoid bugs this way.

### Enums and tests

    - When defining enums related to string values, always inherit from `StrEnum`
    - When you need the enum value as a string, don't use `str(enum_var)` or `enum_var.value`, just use `enum_var` itself, that is the point of using StrEnum!
    - Never test equality to an enum value: use match/case, even to single out 1 case out of 10 cases. To avoid heavy match/case code in awkward places, add methods to the enum class such as `is_foobar()`. This is to avoid bugs: when new enum values are added we want the linter to complain. Use the `|` operator to group cases
    - As our match/case constructs over enums are always exhaustive, NEVER add a default `case _: ...`. Otherwise, you won't pass linting.
    - `StrEnum` must be imported from `pipelex.types` (handles python retrocompatibility):
    ```python
    from pipelex.types import StrEnum
    ```

### Optionals

- Don't write things like `a = b if b else c`, write `a = b or c` instead.

### Imports

#### **Imports at the top of the file**

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
    log.verbose("Hello, world!", title="Your first Pipelex log")
    pretty_print(output_object, title="Your first Pipelex output")
    ```
    - Both handle formatting json using Rich, pretty_print makes it prettier.

- **StrEnum and Self type**:

    - Both `StrEnum` and `Self` must be imported from `pipelex.types` (handles python retrocompatibility):
    ```python
    from pipelex.types import Self, StrEnum
    ```

### Typing

#### **Always Use Type Hints**

    - Every function parameter must be typed
    - Every function return must be typed
    - Use type hints for all variables where type is not obvious
    - Use dict, list, tuple types with lowercase first letter: dict[], list[], tuple[]
    - Use type hints for all fields
    - Use Field(default_factory=...) for mutable defaults
    - Use `# pyright: ignore[specificError]` or `# type: ignore` only as a last resort. In particular, if you are sure about the type, you often solve issues by using cast() or creating a new typed variable.

#### **BaseModel / Pydantic Standards**

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

### Factory Pattern

    - Use factory pattern for object creation when dealing with multiple implementations
    - Our factory methods are named `make_from_...` and such

### Error Handling

    - Always catch exceptions at the place where you can add useful context to it.
    - Use try/except blocks with specific exceptions
    - Convert third-party exceptions to our custom ones except in pydantic validators where you can raise a ValueError or a TypeError
    - NEVER catch the generic Exception, only catch specific exceptions, except at the root of CLI commands
    - Always add `from exc` to the exception raise statements
    - Always write the error message as a variable before raising it, for cleaner error traces
   
   ```python
   try:
       self.models_manager.setup()
   except RoutingProfileLibraryNotFoundError as exc:
       msg = "The routing library could not be found, please call `pipelex init config` to create it"
       raise PipelexSetupError(msg) from exc
   ```

### Documentation

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

## Writing tests

### Unit test generalities

NEVER USE unittest.mock. YOU MUST USE pytest-mock instead.

#### Test file structure

- Name test files with `test_` prefix
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete workflows
    - `tests/test_pipelines/` - for test pipeline definitions (PLX files and their structuring python files)
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `from tests.integration.pipelex.cogt.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put test inside Test classes: 1 TestClass per module.

#### Markers

Apply the appropriate markers:
- "llm: uses an LLM to generate text or objects"
- "img_gen: uses an image generation AI"
- "extract: uses text/image extraction from documents"
- "inference: uses either an LLM or an image generation AI"
- "gha_disabled: will not be able to run properly on GitHub Actions"

Several markers may be applied. For instance, if the test uses an LLM, then it uses inference, so you must mark with both `inference`and `llm`.

#### Important rules

- Never use the unittest.mock. Use pytest-mock.

#### Test Class Structure

- Always group the tests of a module into a test class:

```python
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestFooBar:
    @pytest.mark.parametrize(
        "topic, test_case_blueprint",
        [
            TestCases.CASE_1,
            TestCases.CASE_2,
        ],
    )
    async def test_pipe_processing(
        self,
        request: FixtureRequest,
        topic: str,
        test_case_blueprint: StuffBlueprint,
    ):
        # Test implementation
```

- Never more than 1 class per test module.
- When testing one method, if possible, limit the number of test functions, but with different test cases in parameters
- Sometimes it can be convenient to access the test's name in its body, for instance to include into a job_id. To achieve that, add the argument `request: FixtureRequest` into the signature and then you can get the test name using `cast(str, request.node.originalname),  # type: ignore`. 

#### Test Data Organization

- If it's not already there, create a `test_data.py` file in the proper test directory
- Note how we avoid initializing a default mutable value within a class instance, instead we use ClassVar.
- Also note that we provide a topic for the test case, which is purely for convenience.

### Best Practices for Testing

- Use strong asserts: test value, not just type and presence.
- Use parametrize for multiple test cases
- Test both success and failure cases
- Verify working memory state
- Check output structure and content
- Use meaningful test case names
- Include docstrings explaining test purpose but not on top of the file and not on top of the class.
- Log outputs for debugging

## Writing Docs

We use Material for MkDocs. All markdown in our docs must be compatible with Material for MkDocs and done using best practices to get the best results with Material for MkDocs.

### MkDocs Markdown Requirements

- Always add a blank line before any bullet lists or numbered lists in MkDocs markdown.

## Test-Driven Development Guide

This document outlines our test-driven development (TDD) process and the tools available for testing.

### TDD Cycle

1. **Write a Test First**

2. **Write the Code**
   - Implement the minimum amount of code needed to pass the test
   - Follow the project's coding standards
   - Keep it simple - don't write more than needed

3. **Run Linting and Type Checking**

4. **Validate tests**

Remember: The key to TDD is writing the test first and letting it drive your implementation. Then, always run the full test suite and quality checks before considering a feature complete.
<!-- END_PIPELEX_RULES -->
