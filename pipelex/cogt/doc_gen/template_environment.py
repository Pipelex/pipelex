"""The template environment a document engine fills a template file's Jinja tags in, when they read plain data.

An engine that fills a template file itself, such as a Word template's tags filled through docxtpl, renders them in
this environment rather than in one of its own, so a document template gets the sandbox every other Pipelex template
gets. The values it reads are the plain data of the step's inputs (`plain_data.py`), with no stuff in them, so the
environment registers none of Pipelex's filters, which are made for stuff.

This module is part of the document engine contract (`pipelex/plugins/contract.py`).
"""

from jinja2 import BaseLoader

from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_from_loader
from pipelex.tools.jinja2.jinja2_sandbox import PipelexTemplateEnvironment
from pipelex.tools.jinja2.template_category import TemplateCategory


def make_plain_data_template_environment() -> PipelexTemplateEnvironment:
    """A new environment for a template of plain data: synchronous, sandboxed, strict about missing values, filterless.

    - **Synchronous**: a template renders with `render`, as a library like docxtpl calls it.
    - **Sandboxed** as every Pipelex template is (`jinja2_sandbox.py`): a template reads data and calls the
      methods of plain values, and anything else raises `jinja2.exceptions.SecurityError`; and each render spends
      from a budget of its own, an overdraft raising `RenderBudgetExceededError`.
    - **Strict**: a missing value fails the render with `jinja2.exceptions.UndefinedError` rather than printing
      as empty text, as in every document template.
    - **Without Pipelex's filters**: Jinja's built-in filters only, under the sandbox.

    It loads no template by name, so a template is built from its source with `from_string`.
    """
    return make_jinja2_env_from_loader(
        template_category=TemplateCategory.BASIC,
        loader=BaseLoader(),
        enable_async=False,
        is_undefined_strict=True,
    )
