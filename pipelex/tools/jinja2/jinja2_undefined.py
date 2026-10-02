"""The strict undefined of templates whose missing value must fail the render rather than print as empty text.

Jinja's default undefined prints as nothing, which suits a prompt that may leave a part out but not a document:
a misspelled field in an invoice template would print an invoice with a hole in it. `PipeDocGen` renders its
templates and its filename with this one instead, and so does the environment Pipelex hands a document engine
for filling a Word template, so the misspelling fails at the dry run.

It is Jinja's `StrictUndefined` with one difference: it is falsy rather than raising when tested. Truthiness is
how a Pipelex template probes whether a declared-optional input is present (`{% if notes %}`, which the
optional-input guard lint accepts as a guard, and which the `@?notes` sigil rewrites to), so a strict undefined
that raised on `bool()` would break every guarded template. Printing, iterating, comparing and reading an
attribute of it still raise, and `is defined` and the `default` filter behave as usual.
"""

from jinja2 import StrictUndefined
from typing_extensions import override


class PresenceProbingStrictUndefined(StrictUndefined):
    """A strict undefined that answers a truthiness test with False instead of raising."""

    # Jinja types StrictUndefined's `__bool__` as never returning, since it raises; answering is this class's point.
    @override
    def __bool__(self) -> bool:  # type: ignore[override]
        return False
