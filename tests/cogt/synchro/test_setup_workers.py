# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex.hub import get_inference_manager


@pytest.mark.gha_disabled
class TestCogtSetupWorkers:
    def test_setup_inference_manager(self):
        get_inference_manager().setup_llm_workers()
        get_inference_manager().setup_imgg_workers()
