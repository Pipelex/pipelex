# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import BaseModel

from pipelex.cogt.imgg.imgg_platform import ImggPlatform


class ImggEngine(BaseModel):
    imgg_platform: ImggPlatform
    imgg_model_name: str

    @property
    def desc(self) -> str:
        return f"Imgg Engine {self.imgg_platform}/{self.imgg_model_name}"
