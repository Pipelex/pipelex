# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing_extensions import override

from pipelex.cogt.imgg.imgg_engine_abstract import ImggEngineAbstract
from pipelex.cogt.imgg.imgg_handle import ImggHandle


class FalEngine(ImggEngineAbstract):
    fal_application: ImggHandle

    @property
    @override
    def desc(self) -> str:
        return f"Fal Engine using application '{self.fal_application}'"
