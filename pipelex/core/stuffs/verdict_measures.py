"""The value range shared by the verdict natives' probabilities and confidences.

The pinned definitions state the range in prose only ("from 0 to 1"), so it is the content classes'
own invariant: a content holding a probability of 1.5 is not a verdict this engine will hold,
whichever producer wrote it. It is stated as a schema constraint rather than enforced by a
validator, so a model filling the structure is told the range, and the dry-run mock factory, which
reads constraints but cannot see inside a validator, builds values within it.
"""

from typing import Annotated

from pydantic import Field

UnitInterval = Annotated[float, Field(ge=0, le=1)]
"""A probability or a confidence: a number from 0 to 1, as a distribution's value type."""
