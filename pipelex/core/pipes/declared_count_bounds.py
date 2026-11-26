"""The fixed bounds on a declared item count that hold whatever maximum a runtime or a plan sets.

A method declares a fixed number of items with `Concept[N]` on an input or an output, or with `nb_output = N` on a
controller step. How many a runtime accepts is its own limit, `[interpreter.method_limits] max_declared_item_count`, which
a request may replace (`pipelex.core.pipes.declared_item_count`). These bounds sit above every such limit: the parser
refuses a count written with more digits than any limit could allow, before it converts the digits to an integer, so an
absurd count is refused by a typed error of ours rather than by Python's guard on long integer strings, and no
configuration or request may set a maximum above them.

This module imports nothing, so the configuration model can read it without reaching the parser.
"""

# The most digits a declared count may be written with, leading zeros aside.
DECLARED_ITEM_COUNT_MAX_DIGITS = 9

# The largest count any runtime limit may allow: the largest number written with `DECLARED_ITEM_COUNT_MAX_DIGITS` digits.
DECLARED_ITEM_COUNT_CEILING = 10**DECLARED_ITEM_COUNT_MAX_DIGITS - 1
