"""The template environment a document engine fills a template file's Jinja tags in, when they read plain data.

An engine that fills a template file itself, such as a Word template's tags filled through docxtpl, renders them in
this environment rather than in one of its own, so a document template gets the sandbox every other Pipelex template
gets. The values it reads are the plain data of the step's inputs (`plain_data.py`), with no stuff in them, so the
environment registers none of Pipelex's filters made for stuff, and one made for plain data: `markdown`, which reads a
text as Markdown for the engine to print formatted (`formatted_markdown.py`).

This module is part of the document engine contract (`pipelex/plugins/contract.py`).
"""

from collections.abc import Callable
from typing import Any

from jinja2 import BaseLoader

from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_from_loader
from pipelex.tools.jinja2.jinja2_filters import markdown_to_formatted
from pipelex.tools.jinja2.jinja2_models import Jinja2FilterName
from pipelex.tools.jinja2.jinja2_sandbox import PipelexTemplateEnvironment
from pipelex.tools.jinja2.template_category import TemplateCategory


def make_plain_data_template_environment(*, finalize: Callable[..., Any] | None = None) -> PipelexTemplateEnvironment:
    """A new environment for a template of plain data: synchronous, sandboxed, strict about missing values, with Jinja's filters and `markdown`.

    - **Synchronous**: a template renders with `render`, as a library like docxtpl calls it.
    - **Sandboxed** as every Pipelex template is (`jinja2_sandbox.py`): a template reads data and calls the
      methods of plain values, and anything else raises `jinja2.exceptions.SecurityError`; and each render spends
      from a budget of its own, an overdraft raising `RenderBudgetExceededError`.
    - **Strict**: a missing value fails the render with `jinja2.exceptions.UndefinedError` rather than printing
      as empty text, as in every document template.
    - **Jinja's built-in filters and `markdown`**, under the sandbox: `{{ invoice.notes | markdown }}` reads a text as
      Markdown into a `FormattedMarkdown` (`formatted_markdown.py`), None into an empty one, its conversion charged to
      the render's budget.

    `finalize`, when given, is applied to every value a tag prints before the environment converts it to text, so an
    engine turns a printed `FormattedMarkdown` into its own form there and hands every other value back as it is.
    Without one, a `FormattedMarkdown` prints its plain text. It is handed to the environment at construction, which a
    Pipelex environment requires, since the environment wraps it to charge what is printed.

    It loads no template by name, so a template is built from its source with `from_string`.
    """
    environment = make_jinja2_env_from_loader(
        template_category=TemplateCategory.BASIC,
        loader=BaseLoader(),
        enable_async=False,
        finalize=finalize,
        is_undefined_strict=True,
    )
    environment.filters[Jinja2FilterName.MARKDOWN] = markdown_to_formatted
    return environment
