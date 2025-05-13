# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex import pretty_print
from pipelex.cogt.imgg.imgg_job_factory import ImggJobFactory
from pipelex.hub import get_async_imgg_worker
from tests.cogt.test_data import IMGGTestCases


@pytest.mark.imgg
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestAsyncCogtImgg:
    @pytest.mark.parametrize("topic, imgg_prompt_text", IMGGTestCases.IMAGE_DESC)
    async def test_imgg_async_using_handle(self, imgg_handle: str, topic: str, imgg_prompt_text: str):
        pretty_print(imgg_prompt_text, title=topic)
        imgg_worker_async = get_async_imgg_worker(imgg_handle=imgg_handle)
        imgg_job = ImggJobFactory.make_imgg_job_from_prompt_contents(
            positive_text=imgg_prompt_text,
        )
        generated_image = await imgg_worker_async.gen_image(
            imgg_job=imgg_job,
        )
        pretty_print(generated_image, title=f"Generated Image, topic={topic}")
