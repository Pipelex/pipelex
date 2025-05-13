# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import BaseModel


class GeneratedImage(BaseModel):
    # TODO: add image_format
    # image_format: str = "jpeg"
    url: str
    width: int
    height: int
