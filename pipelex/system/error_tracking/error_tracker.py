"""The error tracker seam: where the errors pipelex reports go, beside its log lines.

An error tracker is a destination an operator chooses, as they choose a log sink: Pipelex ships one, ``posthog``, which
sends an exception to the operator's own PostHog as an ``$exception``, and a host plugs in its own, Sentry for
instance, through the registrar (``PluginRegistrar.add_error_tracker``). Pipelex ships no vendor SDK: an implementation
lives in the plugin that contributes it, and imports its SDK when its factory runs, never at registration.
"""

from abc import ABC, abstractmethod

from pipelex.system.error_tracking.error_report import ErrorReport


class ErrorTrackerAbstract(ABC):
    """One destination of the errors pipelex reports.

    **What it receives.** ``report`` is called once per reported error with its ``ErrorReport``: the problem in the
    operator's view, the exception when there is one, and the identifiers to group, tag and join on. It is called on
    the thread that met the error, an interpreter hook's thread included, so it returns quickly: a tracker whose SDK
    sends over the network queues the event and sends it in the background, as the PostHog and Sentry SDKs do.

    **What it must never send is a run's content.** A tracker reads the exception's class and its stack, and never the
    locals of its frames; it attaches no request body, no input and no output of a run, and no personal data its SDK
    would collect by default. The problem's sentences, parameters and ``diagnostics.message`` may quote the caller's
    own submission, so a tracker sending off the machine leaves them out unless its operator chose otherwise (see
    ``pipelex.system.error_tracking.error_report``).

    **It never raises into its caller.** A failure to report is the tracker's own: the dispatcher guards every call and
    logs a failing tracker at debug level, but a tracker that swallows its SDK's failures itself loses nothing more.
    """

    @abstractmethod
    def report(self, *, report: ErrorReport) -> None:
        """Send one error to this tracker's destination."""

    def close(self) -> None:
        """Release what the tracker holds, flushing what it queued; called once, at teardown. Nothing to release by default."""
        return
