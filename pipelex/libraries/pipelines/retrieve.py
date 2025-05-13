# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import Field

from pipelex.core.stuff_content import StructuredContent


class RetrievedExcerpt(StructuredContent):
    """
    This model represents an excerpt from a text with its justification for being relevant to a question.
    """

    text: str
    justification: str = Field(..., description="The justification for why this excerpt is relevant to the question")
