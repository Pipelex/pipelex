# Writing unit tests

## Unit test generalities

NEVER USE unittest.mock or MagicMock. YOU MUST USE pytest-mock instead.

### Test file structure

- Name test files with `test_` prefix
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete workflows
    - `tests/test_pipelines/` - for test pipeline definitions (PLX files and their structuring python files)
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `tests.pipelex.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put test inside Test classes.
- The pipelex pipelines should be stored in `tests/test_pipelines` as well as the related structured Output classes that inherit from `StructuredContent`

### Markers

Apply the appropriate markers:
- "llm: uses an LLM to generate text or objects"
- "img_gen: uses an image generation AI"
- "extract: uses text/image extraction from documents"
- "inference: uses either an LLM or an image generation AI"
- "gha_disabled: will not be able to run properly on GitHub Actions"

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

- Never more than 1 class per test file.
- When testing one method, if possible, limit the number of test functions, but with different test cases in parameters
- Sometimes it can be convenient to access the test's name in its body, for instance to include into a job_id. To achieve that, add the argument `request: FixtureRequest` into the signature and then you can get the test name using `cast(str, request.node.originalname),  # type: ignore`. 

### Test Data Organization

- If it's not already there, create a `test_data.py` file in the proper test directory
- Define test cases using `StuffBlueprint`:

```python
class TestCases:
    CASE_BLUEPRINT_1 = StuffBlueprint(
        name="test_case_1",
        concept_code="domain.ConceptName1",
        value="test_value"
    )
    CASE_BLUEPRINT_2 = StuffBlueprint(
        name="test_case_2",
        concept_code="domain.ConceptName2",
        value="test_value"
    )

    CASE_BLUEPRINTS: ClassVar[list[tuple[str, str]]] = [  # topic, blueprint"
        ("topic1", CASE_BLUEPRINT_1),
        ("topic2", CASE_BLUEPRINT_2),
    ]
```

Note how we avoid initializing a default mutable value within a class instance, instead we use ClassVar.
Also note that we provide a topic for the test case, which is purely for convenience.

## Best Practices for Testing

- Whenever possible, use strong asserts to test value, not just type and presence.
- Use parametrize for multiple test cases
- Test both success and failure cases
- Verify working memory state
- Check output structure and content
- Use meaningful test case names
- Include docstrings explaining test purpose but not on top of the file
- Log outputs for debugging
- Generate reports for cost tracking
