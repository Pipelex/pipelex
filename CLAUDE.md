# Pipelex Coding Rules

## Commands

### Linting

   After making code changes, you must always lint using `make agent-check`.

   ```bash
   make agent-check
   # If the current system doesn't have the `make` command,
   # lookup the "agent-check" target in the Makefile and run the commands one by one (targets fix-unused-imports format lint pyright mypy)
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fix unused imports, lint, format  
   - Mypy: Static type checker
   - plxt: Format and lint TOML, MTHDS, and PLX files

   Always fix any issues reported by these tools before proceeding.

### Cleaning Derived Files

   If you need to clean derived files and caches, typically after you erased files or moved tests, the linters can get confused, the pytest collection can be off...

   ```bash
   make cleanderived
   ```

### Running Tests

   `make agent-test` runs the full test suite and is **critical at the end of a coding session** to verify everything is good before wrapping up.

   At intermediate steps during LOCAL development, it's OK to run only the tests relevant to your changes — either by calling pytest directly from the `.venv` (e.g. `.venv/bin/pytest -x -q tests/unit/path/to/test_module.py`) or using `make t TEST=TestClassName`. This applies only to local setups, not cloud agents.

   ```bash
   make agent-test
   # If the current system doesn't have the `make` command, lookup the "agent-test" target in the Makefile and run the command manually.
   # Zero output on success; full output on failure.
   ```

### Running Tests with Prints

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   If anything went wrong, you can run the tests with prints to see the error:

   ```bash
   make test-with-prints
   # If the current system doesn't have the `make` command, lookup the "test-with-prints" target in the Makefile and run the command manually.
   ```

### Running specific Tests

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

### Running Last Failed Tests

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   To rerun only the tests that failed in the previous run, use:

   ```bash
   make tp TEST=LF
   # or with any test target
   make test TEST=LF
   make t TEST=LF
   ```
   Note: `TEST=LF` (or `TEST=lf`) will use pytest's `--lf` flag instead of name filtering.

### Temporal Integration Test Options

   The Temporal integration tests support different server modes via the `--temporal-server` pytest CLI option:

   - `--temporal-server`: Which Temporal server to use
     - `none` (default): in-process test server — no external dependencies, used in CI
     - `time-skipping`: in-process server with deterministic time control
     - A profile name from `temporal_server_configs` in `pipelex.toml` (e.g. `local`, `testing`): connects to a real Temporal server using the profile's host, namespace, and API key settings

   ```bash
   # CI default: in-process server
   .venv/bin/pytest tests/integration/pipelex/temporal/

   # Dev with local Temporal server
   .venv/bin/pytest tests/integration/pipelex/temporal/ \
     --temporal-server local

   # Dev with cloud/testing server
   .venv/bin/pytest tests/integration/pipelex/temporal/ \
     --temporal-server testing
   ```

   The `--class-registry` option controls whether dynamic concept classes leak to the
   global KajsonManager registry or are scoped to the library:

   - `--class-registry both` (default): runs tests in both shared and isolated modes
   - `--class-registry shared`: dynamic classes go to global registry (standard behavior)
   - `--class-registry isolated`: dynamic classes are scoped to the library registry,
     keeping the global clean — forces deferred hydration paths, catching regressions
     that only manifest in multi-process deployments

   ```bash
   # Default: runs both modes automatically
   .venv/bin/pytest tests/integration/pipelex/temporal/

   # Force single mode (useful for debugging)
   .venv/bin/pytest tests/integration/pipelex/temporal/ \
     --class-registry isolated
   ```

---

### Prerequisites for running command lines: use virtual environment

   **CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST use the appropriate Python virtual environment. The only exceptions are our `make` commands which already include the env activation.

   Call the CLI directly from the virtual environment:

   ```bash
   .venv/bin/pytest -s -v -k test_render_jinja2_from_text
   .venv/bin/pipelex validate --all
   ```

   For standard installations, the virtual environment is named `.venv`. Always check this first. On Windows, the path is `.venv\Scripts\` instead of `.venv/bin/`.

### Pipelex Dev CLI (`pipelex-dev`)

   The `pipelex-dev` CLI provides internal development tools that are not distributed with the package. It is available in the virtual environment.

   ```bash
   .venv/bin/pipelex-dev --help
   ```

   Key commands:

   - **`generate-mthds-schema`**: Regenerate the MTHDS JSON Schema (`derived/mthds_schema.json`). Run this after modifying `mthds_schema_generator.py`.

     ```bash
     .venv/bin/pipelex-dev generate-mthds-schema
     ```

## Coding Standards & Best Practices for Python Code

This document outlines the core coding standards, best practices, and quality control procedures for the codebase.

### Python Version Compatibility

    - The project supports Python 3.10+ (`requires-python = ">=3.10,<3.15"`). Never use features introduced after Python 3.10 without a compatibility fallback.
    - Common pitfalls:
      - `datetime.UTC` was added in Python 3.11. Use `datetime.timezone.utc` instead.
      - `StrEnum` was added in Python 3.11. Always import it from `pipelex.types` which handles retrocompatibility.
      - `type` statement (PEP 695) was added in Python 3.12. Use `TypeAlias` from `typing` instead.
      - `ExceptionGroup` / `except*` was added in Python 3.11. Avoid unless using the `exceptiongroup` backport.

### Variables, loops and indexes

    - Variable names should have a minimum length of 3 characters. No exceptions: name your `for` loop indexes like `index_foobar`, your exceptions `exc` or more specific like `validation_error` when there are several layers of exceptions, and use `for key, value in ...` for key/value pairs.
    - When looping on the keys of a dict, use `for key in the_dict` rather than `for key in the_dict.keys()` otherwise you won't pass linting.
    - Avoid inline for loops, unless it's ultra-simple and holds on oneline.
    - If you have a variable that will get its value differently through different code paths, declare it first with a type, e.g. `pipe_code: str` but DO NOT give it a default value like `pipe_code: str = ""` unless it's really justified. We want the variable to be unbound until all paths are covered, and the linters will help us avoid bugs this way.

### Enums and tests

    - When defining enums related to string values, always inherit from `StrEnum`
    - When you need the enum value as a string, don't use `str(enum_var)` or `enum_var.value`, just use `enum_var` itself, that is the point of using StrEnum!
    - Never test equality to an enum value: use match/case, even to single out 1 case out of 10 cases. To avoid heavy match/case code in awkward places, add @property methods to the enum class such as `is_foobar()`. This is to avoid bugs: when new enum values are added we want the linter to complain. Use the `|` operator to group cases
    - As our match/case constructs over enums are always exhaustive, NEVER add a default `case _: ...`. Otherwise, you won't pass linting.
    - `StrEnum` must be imported from `pipelex.types` (handles python retrocompatibility):
    ```python
    from pipelex.types import StrEnum
    ```

### Optionals

- Don't write things like `a = b if b else c`, write `a = b or c` instead.

### Imports

#### **Imports at the top of the file**

    - Avoid as much as possible import statements outside of a module's top-level scope.
    - Do not import libraries in functions or classes unless in very specific cases, to be discussed with the user, as they would required a `# noqa: ...` comment to pass linting
    - Do not bother with ordering the imports or removing unused imports, our Ruff linter will handle it for us.
    - `if TYPE_CHECKING:` blocks must always be the **last** block in the imports section, placed after all regular imports.

#### **Removing unused imports**

    - To remove unused imports, run `make fix-unused-imports` or `make fui` (shorthand). This is faster and cheaper than rewriting with LLM.

#### **No re-exports in `__init__.py`**

    - Do NOT fill `__init__.py` files with re-exports.
    - Always use direct full-path imports everywhere. For example:

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

## Standards related to developing the Pipelex codebase

### Spec vs Blueprint Architecture

- **Blueprints** (`pipelex/pipe_operators/`, `pipelex/pipe_controllers/`, `pipelex/core/`) are the MTHDS language reference — what `.mthds` files parse into.
- **Specs** (`pipelex/builder/pipe/`) are a convenience authoring format for AI agents. Each spec has `to_blueprint()` that transforms it into the corresponding blueprint. Spec-level fields may differ from blueprint-level fields.

When adding validation or fields, decide which layer they belong to. Language rules go on blueprints; authoring convenience goes on specs. See `pipelex/builder/CLAUDE.md` for details.

### Main config

- The main config model is defined using `ConfigModel` classes, derived from `pydantic BaseModel`
- The model is defined in `pipelex/system/configuration/configs.py`, some of the submodels being defined in their respective sub-packages
- When adding new configs, place them where it makes most sense, ask the user if you need arbitrage
- As per our python standards, use StrEnum for multiple-value enums. In that case they must not be strict pydantic fields, i.e. add `= Field(strict=False)`
- **Important**: NEVER EVER set default values for config attributes in the class definition. All the default values are defined in the main config file `pipelex/pipelex.toml`. The only exception si for Optional values which must be set to `None` in the class definition.
- If (and only if) you add some config that will clearly make sense for client projects to override, for instance if it's a case of user preference, then you can also add a copy of the settings to the project override config file `.pipelex/pipelex.toml` but leaving them commented out, as an invitation to override.
- The different `pipelex.toml` files and the python model `configs.py` must be up to date with each other in terms of structure and attributes, otherwise the loading of teh config fails. To check quickly that you're good, just run `make tb` which tests the boot sequence, which includes the config loading.

## Writing tests

### Unit test generalities

NEVER USE unittest.mock. Instead YOU MUST USE pytest-mock: `from pytest_mock import MockerFixture`.
NEVER EVER put more than one TestClass into a test module.

#### Test file structure

- Name test files with `test_` prefix
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete methods
- Do NOT add `__init__.py` files to test directories. Test directories do not need to be Python packages.
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `from tests.integration.pipelex.cogt.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put tests inside Test classes: 1 TestClass per module.
- NEVER EVER put more than one TestClass into a test module.
- Put fixtures into conftest.py files for easy sharing.

#### Markers

Apply the appropriate markers:
- "gha_disabled: will not be able to run properly on GitHub Actions"
- "llm: uses an LLM to generate text or objects"
- "img_gen: uses an image generation AI"
- "extract: uses text/image extraction from documents"
- "inference: uses either an LLM or an image generation AI"
- never add "@pytest.mark.dry_runnable" if you haven't set the "inference" marker

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
- Include concise docstrings explaining test purpose but not on top of the file and not on top of the class.
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
