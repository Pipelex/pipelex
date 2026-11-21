"""The attempts of one structured generation through ``instructor``, and the usage they spent, summed.

A structured generation is one call that ``instructor`` may answer in several requests: it re-asks the model when an
answer fails the schema, up to the job's re-ask budget, and every request is billed. Neither of the totals ``instructor``
keeps covers every provider: it sums the usage of OpenAI- and Anthropic-shaped answers only, into the last answer on
success and into ``InstructorRetryException.total_usage`` when the re-asks run out, and leaves a Google, Mistral or
OpenAI Responses answer with its own usage alone. So each worker passes this recorder's hooks with the call, the hooks
``instructor`` calls once per request: ``completion:kwargs`` before the request, which counts the attempt, and
``completion:response`` with the answer, before ``instructor`` folds its usage into a running total, from which the
worker's own reader takes the tokens that answer reports. The worker then records the sum and the count on its job's
report however the call ended, so a generation whose re-asks ran out still reports what it spent, on its span and on
its summary event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from instructor.core import Hooks

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.usage.token_category import NbTokensByCategoryDict


class AnswerTokensReader(Protocol):
    """Reads the tokens one answer of the provider reports, by category; `None` for an answer that reports no usage."""

    def __call__(self, *, response: Any) -> NbTokensByCategoryDict | None: ...


class InstructorAttempts:
    """Counts the requests of one structured generation and sums the tokens each answer reported.

    Args:
        read_nb_tokens: Reads the tokens one answer of the provider reports, by category; `None` for an answer that
            reports no usage.
    """

    def __init__(self, *, read_nb_tokens: AnswerTokensReader) -> None:
        self._read_nb_tokens = read_nb_tokens
        self.attempt_count = 0
        self.nb_tokens_by_category: NbTokensByCategoryDict = {}
        self.has_usage = False

    def make_hooks(self) -> Hooks:
        """The per-call hooks to pass `instructor` as `hooks=`, which count each request and read each answer's usage."""
        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import HookName, Hooks  # ruff: ignore[import-outside-top-level]

        hooks = Hooks()
        hooks.on(HookName.COMPLETION_KWARGS, self._count_attempt)
        hooks.on(HookName.COMPLETION_RESPONSE, self._add_response_usage)
        return hooks

    def _count_attempt(self, *args: Any, **kwargs: Any) -> None:  # ruff: ignore[unused-method-argument]
        """Count one request, `instructor` handing over the request's arguments, which are not read."""
        self.attempt_count += 1

    def _add_response_usage(self, response: Any) -> None:  # kw-only: ignore — instructor hook, invoked positionally with the answer
        """Add the tokens one answer reports to the sum, read now, before `instructor` folds them into a running total."""
        nb_tokens = self._read_nb_tokens(response=response)
        if not nb_tokens:
            return
        self.has_usage = True
        for token_category, nb_tokens_of_category in nb_tokens.items():
            self.nb_tokens_by_category[token_category] = self.nb_tokens_by_category.get(token_category, 0) + nb_tokens_of_category

    def record_into(self, *, llm_job: LLMJob) -> None:
        """Record the attempts and the usage they spent on the job's report, the usage only when an answer reported some."""
        if self.attempt_count:
            llm_job.job_report.attempt_count = self.attempt_count
        if self.has_usage and (llm_tokens_usage := llm_job.job_report.llm_tokens_usage):
            llm_tokens_usage.nb_tokens_by_category = dict(self.nb_tokens_by_category)
