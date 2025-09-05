# General rules

## Repo structure

Pipelex is a framework to run low-code AI workflows for repeatable processes.
This python >=3.10 code is in the `pipelex` directory.

## Code Style & formatting

- Imitate existing style
- Use type hints
- Respect Pydantic v2 standard
- Use Typer for CLIs
- Use explicit keyword arguments for function calls with multiple parameters (e.g., `func(arg_name=value)` not just `func(value)`)
- Add trailing commas to multi-line lists, dicts, function arguments, and tuples with >2 items (helps with cleaner diffs and prevents syntax errors when adding items)
- All imports inside this repo's packages must be absolute package paths from the root

## Error Handling & Validation

- Use `StuffContentValidationError` for type validation failures
- Apply `format_pydantic_validation_error` for formatting validation errors consistently


## Test file structure

- Name test files with `test_` prefix
- Use descriptive names that match the functionality being tested
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete workflows
    - `tests/test_pipelines/` - for test pipeline definitions (PLX files and their structuring python files)
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `tests.pipelex.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put test inside Test classes.
- The pipelex pipelines should be stored in `tests/test_pipelines` as well as the related structured Output classes that inherit from `StructuredContent`

## Markers

Apply the appropriate markers:
- "llm: uses an LLM to generate text or objects"
- "imgg: uses an image generation AI"
- "inference: uses either an LLM or an image generation AI"
- "gha_disabled: will not be able to run properly on GitHub Actions"

Several markers may be applied. For instance, if the test uses an LLM, then it uses inference, so you must mark with both `inference`and `llm`.

## Test Class Structure

Always group the tests of a module into a test class:

```python
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestFooBar:
    @pytest.mark.parametrize(
        "topic test_case_blueprint",
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

## Linting & checking

- Run `make lint` -> it runs `ruff check . --fix` to enforce all our linting rules
- Run `make pyright` -> it typechecks with pyright using proper settings
- Run `make mypy` -> it typechecks with mypy using proper settings
    - if you added a dependency and mypy complains that it's not typed, add it to the list of modules in [[tool.mypy.overrides]] in pyproject.toml, be sure to signal it in your PR recap so that maintainers can look for existing stubs
- After `make pyright`, you must also check with `make mypy`

## Testing

- Always test with `make t` -> it runs pytest using proper settings
- If some pytest tests fail, run pytest on the failed ones with the required verbosity to diagnose the issue
- If all unit tests pass, run `make validate` -> it runs a minimal version of our app with just the inits and data loading (`pipelex validate all -c pipelex/libraries` under the hood) in the python environment.

## PR Instructions

- Run `make fix-unused-imports` -> removes unused imports, required to validate PR
- Re-run checks in one call with `make check` -> formatting and linting with Ruff, type-checking with Pyright and Mypy
- Re-run `make codex-tests`
- Write a one-line summary of the changes.
- Be sure to list changes made to configs, tests and dependencies

## More docs

- Scan the *.mdc files in .cursor/rules/ to get usefull details and explanations on the codebase