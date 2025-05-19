# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Self

from pydantic import BaseModel, model_validator

from pipelex.cogt.exceptions import CogtError
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class OcrInputError(CogtError):
    pass


class OcrInput(BaseModel):
    image_uri: Optional[str] = None
    pdf_uri: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_exactly_one_input(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_uri", "pdf_uri"]):
            raise OcrInputError("Exactly one of 'image_uri' or 'pdf_uri' must be provided")
        return self
