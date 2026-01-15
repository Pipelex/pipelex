# Writing tests

## Unit test generalities

NEVER USE unittest.mock. Instead YOU MUST USE pytest-mock: `from pytest_mock import MockerFixture`.
NEVER EVER put more than one TestClass into a test module.

### Test file structure

- Name test files with `test_` prefix
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete workflows
- Do NOT add `__init__.py` files to test directories. Test directories do not need to be Python packages.
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `from tests.integration.pipelex.cogt.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put tests inside Test classes: 1 TestClass per module.
- NEVER EVER put more than one TestClass into a test module.
- Put fixtures into conftest.py files for easy sharing.

### Markers

Apply the appropriate markers:
- "gha_disabled: will not be able to run properly on GitHub Actions"
- "llm: uses an LLM to generate text or objects"
- "img_gen: uses an image generation AI"
- "extract: uses text/image extraction from documents"
- "inference: uses either an LLM or an image generation AI"
- never add "@pytest.mark.dry_runnable" if you haven't set the "inference" marker

Several markers may be applied. For instance, if the test uses an LLM, then it uses inference, so you must mark with both `inference`and `llm`.

### Important rules

- Never use the unittest.mock. Use pytest-mock.

### Test Class Structure

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

### Test Data Organization

- If it's not already there, create a `test_data.py` file in the proper test directory
- Note how we avoid initializing a default mutable value within a class instance, instead we use ClassVar.
- Also note that we provide a topic for the test case, which is purely for convenience.

## Best Practices for Testing

- Use strong asserts: test value, not just type and presence.
- Use parametrize for multiple test cases
- Test both success and failure cases
- Verify working memory state
- Check output structure and content
- Use meaningful test case names
- Include concise docstrings explaining test purpose but not on top of the file and not on top of the class.
- Log outputs for debugging
