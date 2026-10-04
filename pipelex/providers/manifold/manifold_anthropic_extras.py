"""The per-request extras of a Claude call through the Pipelex Manifold service.

Claude reaches the service over the open Anthropic worker, registered here under the package's own
`manifold_anthropic` sdk token with this factory: the worker asks it, per request, what joins the
call, and the answer is the `x-pipelex-metadata` header naming the run and the step (see
`manifold_metadata`). Every other Anthropic path builds the worker without a factory and sends
nothing of the kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.plugins.backend_extras_factory import BackendExtrasFactory
from pipelex.providers.manifold.manifold_metadata import make_manifold_metadata_headers

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class ManifoldAnthropicExtrasFactory(BackendExtrasFactory):
    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """The metadata header alone, and no body additions.

        `inference_model` and `output_desc` are part of the shared factory signature and unused here:
        the header names the job, not the model or the output.
        """
        del inference_model, output_desc
        return make_manifold_metadata_headers(job_metadata=inference_job.job_metadata), {}
