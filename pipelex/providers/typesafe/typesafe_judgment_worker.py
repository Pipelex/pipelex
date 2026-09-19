from typesafe_sdk import AsyncTypeSafeClient, SystemOneResponse, TypeSafeError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.error_classification import extract_typesafe_metadata
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_models import JudgmentAnswer
from pipelex.cogt.judgment.judgment_worker_abstract import JudgmentWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.typesafe.typesafe_error_classification import classify_typesafe_error
from pipelex.providers.typesafe.typesafe_translation import from_typesafe_response, to_typesafe_questions
from pipelex.reporting.reporting_protocol import ReportingProtocol


class TypesafeJudgmentWorker(JudgmentWorkerAbstract):
    """Serves the judgment family from TypeSafe's System One endpoint.

    One request carries the whole job, which is the reason the family's contract is batch-shaped:
    three questions over one state cost 506 input tokens together against 1138 apart, and answered
    in 0.27 s against 0.66 s. The state is paid for once, so a caller that asks everything it wants
    to know in one job is rewarded for it.
    """

    def __init__(
        self,
        *,
        sdk_instance: AsyncTypeSafeClient,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        JudgmentWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=reporting_delegate)
        self._typesafe_client = sdk_instance

    @override
    async def _judge(
        self,
        judgment_job: JudgmentJob,
    ) -> dict[str, JudgmentAnswer]:
        typesafe_questions = to_typesafe_questions(questions=judgment_job.questions)
        try:
            # The SDK types its state as a recursive JSON alias that pyright cannot resolve to the end.
            response = await self._typesafe_client.system_one(  # pyright: ignore[reportUnknownMemberType]
                judgment_job.state,
                typesafe_questions,
                model=self.inference_model.model_id,
            )
        except TypeSafeError as sdk_exc:
            # The whole vendor family in one arm, on purpose. ``TypeSafeError`` is the SDK's base
            # class: its API subclasses carry a status and a body, and the bare class is the SDK
            # refusing a request it would not send. Both are failures of this call and both are
            # classified from the metadata, which is where the difference is read.
            metadata = extract_typesafe_metadata(sdk_exc)
            classification = classify_typesafe_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.JUDGMENT,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        self._log_request_id(response=response)
        self._warn_if_another_model_answered(response=response)
        self._record_usage(judgment_job=judgment_job, response=response)
        return from_typesafe_response(questions=judgment_job.questions, response=response)

    def _log_request_id(self, *, response: SystemOneResponse) -> None:
        """Trace the provider's own request id, which it returns on success as well as on failure.

        The read has to be guarded, and this is the trap the spike walked into first: on a response
        ``request_id`` is a property that **raises** when the header was absent rather than
        returning ``None``. On an error object the same attribute is a plain ``str | None``, which
        is why the error path reads it without any of this.
        """
        try:
            request_id = response.request_id
        except TypeSafeError:
            return
        log.debug(f"TypeSafe judgment answered by '{response.model}' (request_id={request_id})")

    def _warn_if_another_model_answered(self, *, response: SystemOneResponse) -> None:
        """Say so when the API answered under a model other than the one the deck pinned.

        The deck names a versioned model precisely so that a threshold keeps meaning what it meant
        when the method was written, and this API reports which model actually answered. The spike
        saw it echo the pinned id back unchanged, so a mismatch means the pin was not honoured —
        worth a warning on the run, not worth failing a call that did answer.
        """
        if response.model != self.inference_model.model_id:
            log.warning(
                f"TypeSafe was asked for judgment model '{self.inference_model.model_id}' and answered as "
                f"'{response.model}': verdicts and their thresholds may not mean what they meant under the pinned model"
            )

    def _record_usage(self, *, judgment_job: JudgmentJob, response: SystemOneResponse) -> None:
        """Record the real token counts this call was billed for.

        Usage is reported per *request*, never per question, and both fields are optional in the
        SDK's model even though the live API has always filled them. An absent field records no
        tokens for that category rather than a guess — the family's rule for a backend that does
        not report what it read.
        """
        judgment_tokens_usage = judgment_job.job_report.judgment_tokens_usage
        if judgment_tokens_usage is None:
            return
        nb_tokens_by_category: NbTokensByCategoryDict = {}
        if response.usage.input_tokens is not None:
            nb_tokens_by_category[TokenCategory.INPUT] = response.usage.input_tokens
        if response.usage.output_tokens is not None:
            nb_tokens_by_category[TokenCategory.OUTPUT] = response.usage.output_tokens
        judgment_tokens_usage.nb_tokens_by_category = nb_tokens_by_category
