# Commands
  
## Prerequisites: Virtual Environment

**CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST activate the appropriate Python virtual environment. Without proper venv activation, these commands will not work:

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

## Instructions

After making changes to the code, always run the following command to validate the code:

### Linting

```bash
make check
```

This runs multiple code quality tools:
- Pyright: Static type checking
- Ruff: Fast Python linter  
- Mypy: Static type checker

Always fix any issues reported by these tools before proceeding.

If the current system doesn't have the `make` command, lookup the "check" target in the Makefile and run the command manually.

### Running Tests

```bash
make test-xdist
```

If the current system doesn't have the `make` command, lookup the "test-xdist" target in the Makefile and run the command manually.

### Running Tests with Prints

If anything when wrong, you can run the tests with prints to see the error:

```bash
make test-with-prints
```

If the current system doesn't have the `make` command, lookup the "test-with-prints" target in the Makefile and run the command manually.

### Running specific Tests

   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

### Make targets NOT to run

**Important**: Never run `make ti`, `make test-inference`, `make te`, `make test-extract`, `make tg`, or `make test-img-gen` - these use costly inference.
