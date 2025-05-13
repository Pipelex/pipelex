# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Protocol

from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract


class InferenceManagerProtocol(Protocol):
    """
    This is the protocol for the inference manager.
    Its point is only to avoid a circular import.
    """

    def reset(self): ...

    ####################################################################################################
    # LLM Workers
    ####################################################################################################

    def setup_llm_workers(self): ...

    def get_llm_worker(
        self,
        llm_handle: str,
        specific_llm_engine_blueprint: Optional[LLMEngineBlueprint] = None,
    ) -> LLMWorkerAbstract: ...

    ####################################################################################################
    # IMG Generation Workers
    ####################################################################################################

    def setup_imgg_workers(self): ...

    def get_imgg_worker(self, imgg_handle: str) -> ImggWorkerAbstract: ...
