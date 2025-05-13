# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.cogt.imgg.imgg_engine_abstract import ImggEngineAbstract
from pipelex.cogt.imgg.imgg_handle import ImggHandle


class ImggEngineFactory:
    @classmethod
    def make_imgg_engine_for_fal(
        cls,
        imgg_name: str,
    ) -> ImggEngineAbstract:
        fal_application: ImggHandle = ImggHandle(imgg_name)
        from pipelex.cogt.fal.fal_engine import FalEngine

        return FalEngine(fal_application=fal_application)
