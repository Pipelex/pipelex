"""The webhooks a run is delivered to: the deployment's own completion target, and the caller's `callback_urls`.

The two are different hops and never mix:

- **The deployment's completion target** is the operator's: the URL `COMPLETION_CALLBACK_URL` configures, which may name
  the run's id with one `{pipeline_run_id}` placeholder. A `/start` run notifies it with the completion notice, in the
  operator's view, signed with `X-Completion-Signature`, the HMAC-SHA256 of the run's id under
  `COMPLETION_CALLBACK_SECRET`. It never receives a caller's event.
- **A caller's webhooks** are the `callback_urls` of a `/start` or an `/execute` request. Each receives the signed
  `run.finished` event of the caller-webhook contract (`pipelex.pipe_run.caller_webhook_delivery`), never the completion
  notice nor its signature. The runner signs them under `CALLER_WEBHOOK_SECRET`, so a request carrying any is refused
  with a `422` `pipelex.webhook.secret_not_configured` on a runner whose operator configured none, before anything runs.

On `/start`, a `callback_urls` entry equal to the completion target's URL for the run is the deployment's own hop, sent
there by a host that also forwards it, and is dropped from the caller's: the target is notified once, with its own
notice. An `/execute` run notifies no completion target, so there every entry is a caller's webhook.
"""

import hashlib
import hmac
from collections.abc import Sequence
from urllib.parse import quote, urlsplit

from pipelex.errors.problem import ProblemView
from pipelex.pipe_run.caller_webhook_delivery import CALLER_WEBHOOK_SECRET_ENV, caller_webhook_secret_keys, is_caller_webhook_secret_set
from pipelex.pipe_run.delivery_assignment import CallerWebhookTarget, DeliveryAssignment, StorageTarget, WebhookTarget
from pipelex.system.environment import get_optional_env, get_required_env

from pipelex_api.exceptions import CallerWebhookSecretNotConfiguredError, RunnerMisconfiguredError

COMPLETION_CALLBACK_URL_ENV = "COMPLETION_CALLBACK_URL"
"""The environment variable naming the deployment's own completion target."""

COMPLETION_CALLBACK_SECRET_ENV = "COMPLETION_CALLBACK_SECRET"
"""The environment variable holding the secret the completion target's `X-Completion-Signature` is computed under."""

COMPLETION_SIGNATURE_HEADER = "X-Completion-Signature"
"""The header carrying the completion target's signature, which no caller webhook ever receives."""

PIPELINE_RUN_ID_PLACEHOLDER = "{pipeline_run_id}"
"""The placeholder `COMPLETION_CALLBACK_URL` may hold once, replaced with the run's id."""

_ALLOWED_COMPLETION_SCHEMES = frozenset({"http", "https"})


def completion_callback_template() -> str | None:
    """The deployment's completion target as configured, or None when `COMPLETION_CALLBACK_URL` is unset or empty.

    Read at each use, and once when the server starts, so a malformed value stops the boot.

    Raises:
        RunnerMisconfiguredError: The value is not an absolute http or https URL naming a host, holds a fragment, or holds
            the `{pipeline_run_id}` placeholder more than once (a 500 `runtime.misconfigured` naming the variable).
    """
    configured = get_optional_env(COMPLETION_CALLBACK_URL_ENV)
    if not configured:
        return None
    if configured.count(PIPELINE_RUN_ID_PLACEHOLDER) > 1:
        msg = f"Server configuration error: {COMPLETION_CALLBACK_URL_ENV} may hold the placeholder {PIPELINE_RUN_ID_PLACEHOLDER} once at most."
        raise RunnerMisconfiguredError(msg, component=COMPLETION_CALLBACK_URL_ENV)
    parts = urlsplit(configured.replace(PIPELINE_RUN_ID_PLACEHOLDER, "run"))
    if parts.scheme not in _ALLOWED_COMPLETION_SCHEMES or not parts.hostname or parts.fragment:
        msg = (
            f"Server configuration error: {COMPLETION_CALLBACK_URL_ENV} must be an absolute http or https URL without a fragment, "
            f"such as https://ops.example.com/runs/complete/{PIPELINE_RUN_ID_PLACEHOLDER}."
        )
        raise RunnerMisconfiguredError(msg, component=COMPLETION_CALLBACK_URL_ENV)
    return configured


def ensure_completion_target_configured() -> None:
    """Refuse a completion target this server cannot sign or cannot reach: checked at boot, and before a run is set up.

    Raises:
        RunnerMisconfiguredError: `COMPLETION_CALLBACK_URL` is malformed, or it is set and `COMPLETION_CALLBACK_SECRET`
            holds no secret to sign its notices with (a 500 `runtime.misconfigured` naming the variable to the operator).
    """
    if completion_callback_template() is None:
        return
    if not get_optional_env(COMPLETION_CALLBACK_SECRET_ENV):
        msg = (
            f"Server configuration error: {COMPLETION_CALLBACK_URL_ENV} is set, and {COMPLETION_CALLBACK_SECRET_ENV} holds no "
            "secret to sign its completion notices with."
        )
        raise RunnerMisconfiguredError(msg, component=COMPLETION_CALLBACK_SECRET_ENV)


def completion_callback_url(*, pipeline_run_id: str | None) -> str | None:
    """The completion target's URL for a run, or None when the deployment has none, or names the run's id and it is unknown.

    The id replaces the placeholder percent-encoded, so an id the caller chose cannot add a path segment or a query.
    """
    template = completion_callback_template()
    if template is None:
        return None
    if PIPELINE_RUN_ID_PLACEHOLDER not in template:
        return template
    if pipeline_run_id is None:
        return None
    return template.replace(PIPELINE_RUN_ID_PLACEHOLDER, quote(pipeline_run_id, safe=""))


def completion_signature(*, pipeline_run_id: str) -> str:
    """The completion target's `X-Completion-Signature`: the hex HMAC-SHA256 of the run's id under `COMPLETION_CALLBACK_SECRET`.

    The signer (this server) and the verifier (the deployment's completion receiver) share the secret; only the per-run
    MAC travels.

    Raises:
        EnvVarNotFoundError: `COMPLETION_CALLBACK_SECRET` is not set (a 500 `pipelex.config.variable_missing`).
    """
    secret = get_required_env(COMPLETION_CALLBACK_SECRET_ENV)
    return hmac.new(secret.encode("utf-8"), pipeline_run_id.encode("utf-8"), hashlib.sha256).hexdigest()


def caller_webhook_urls(*, callback_urls: Sequence[str] | None) -> list[str]:
    """The caller's webhooks of an `/execute` request: each of its `callback_urls` once, in order.

    An `/execute` run notifies no completion target, so every URL it lists is a caller's webhook, the completion target's
    own URL included: a host that lists it there is sent the caller's event.

    Args:
        callback_urls: The request's `callback_urls`, already validated by the request model.
    """
    if not callback_urls:
        return []
    return list(dict.fromkeys(callback_urls))


def start_caller_webhook_urls(*, callback_urls: Sequence[str] | None, pipeline_run_id: str | None) -> list[str]:
    """The caller's webhooks of a `/start` request: each of its `callback_urls` once, in order, without the completion URL.

    A `/start` run notifies the deployment's completion target, so a URL equal to the target's URL for the run is the
    host forwarding its own hop, which the target's notice reaches, and never a caller's webhook.

    Args:
        callback_urls: The request's `callback_urls`, already validated by the request model.
        pipeline_run_id: The run's id, when it is known, which the completion target's URL may name.
    """
    completion_url = completion_callback_url(pipeline_run_id=pipeline_run_id)
    return [url for url in caller_webhook_urls(callback_urls=callback_urls) if url != completion_url]


def ensure_caller_webhooks_signable(*, caller_urls: Sequence[str]) -> None:
    """Refuse a request with caller webhooks this runner cannot sign, before anything is fetched, loaded or run.

    Raises:
        CallerWebhookSecretNotConfiguredError: `CALLER_WEBHOOK_SECRET` holds no secret (a 422 naming the setting).
        CallerWebhookSecretError: It holds a value that is not a `whsec_` secret (a 500 `runtime.misconfigured`, the
            operator's to fix, naming the variable to the operator alone).
    """
    if not caller_urls:
        return
    if not is_caller_webhook_secret_set():
        msg = f"The request registers callback URLs, and {CALLER_WEBHOOK_SECRET_ENV} holds no secret to sign their calls with."
        raise CallerWebhookSecretNotConfiguredError(msg, setting=CALLER_WEBHOOK_SECRET_ENV)
    caller_webhook_secret_keys()


def start_delivery_assignment(*, caller_urls: Sequence[str], pipeline_run_id: str) -> DeliveryAssignment:
    """The delivery of a `/start` run: its results stored, the deployment's completion target, then the caller's webhooks.

    No `key_prefix`: the runtime owns the `results/` leaf, under the run's storage scope.

    Raises:
        EnvVarNotFoundError: A completion target is configured and `COMPLETION_CALLBACK_SECRET` is not set.
    """
    completion_url = completion_callback_url(pipeline_run_id=pipeline_run_id)
    webhooks: list[WebhookTarget] = []
    if completion_url is not None:
        # The operator's hop: the completion notice in the operator's view, whoever started the run. Its payload's wire
        # fields are written per delivery by pipelex's DeliveryExecutor, so nothing is injected here.
        webhooks.append(
            WebhookTarget(
                url=completion_url,
                headers={COMPLETION_SIGNATURE_HEADER: completion_signature(pipeline_run_id=pipeline_run_id)},
                problem_view=ProblemView.OPERATOR,
            )
        )
    return DeliveryAssignment(
        storage=StorageTarget(),
        webhooks=webhooks,
        caller_webhooks=[CallerWebhookTarget(url=url) for url in caller_urls if url != completion_url],
    )


def execute_delivery_assignment(*, caller_urls: Sequence[str], delivery_assignment: DeliveryAssignment | None) -> DeliveryAssignment | None:
    """The delivery of an `/execute` run: the caller's webhooks, beside whatever an in-process host assigned.

    An `/execute` run answers with its output, so nothing is stored and no completion target is notified for it: its
    delivery is the caller's webhooks alone, and none at all when it has none.
    """
    if not caller_urls:
        return delivery_assignment
    base_assignment = delivery_assignment or DeliveryAssignment()
    caller_webhooks = [*base_assignment.caller_webhooks, *(CallerWebhookTarget(url=url) for url in caller_urls)]
    return base_assignment.model_copy(update={"caller_webhooks": caller_webhooks})
