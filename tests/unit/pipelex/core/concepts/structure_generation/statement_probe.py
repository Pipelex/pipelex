"""A statement whose running a test can observe, for the tests that check a generated module runs only what it should.

`RUN_STATEMENT` appends to `STATEMENTS_RUN`, reaching this module through `sys.modules`, so a test sees whether the
statement ran without touching the filesystem. The `clear_statements_run` fixture in this directory's conftest
empties the list around each test that uses it.
"""

# A rendering that let a statement run would append to this list.
STATEMENTS_RUN: list[str] = []

# The statement the test cases spell, written without a space so that no line wrapping splits it.
RUN_STATEMENT = f'__import__("sys").modules["{__name__}"].STATEMENTS_RUN.append("ran")'
