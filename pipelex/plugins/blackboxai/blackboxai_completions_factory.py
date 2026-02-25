from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class BlackboxaiCompletionsFactory(OpenAICompletionsFactory):
    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        if isinstance(inference_job, ImgGenJob):
            if isinstance(inference_job.job_params.seed, int):
                seed = inference_job.job_params.seed
            else:
                seed = random.randint(0, 2**32 - 1)
            extra_body = {"seed": seed}
        else:
            extra_body = {}
        return inference_model.extra_headers or {}, extra_body
