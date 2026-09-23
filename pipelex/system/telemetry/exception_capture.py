import sys
import threading
from types import TracebackType
from typing import TYPE_CHECKING

from pipelex import log
from pipelex.system.telemetry.otel_constants import PostHogAttr
from pipelex.system.telemetry.telemetry_identity import TelemetryIdentity

if TYPE_CHECKING:
    # Deferred import: avoid pulling heavy SDK at module-load time
    from posthog import Posthog
    from posthog.args import ExceptionArg


class ExceptionCapture:
    """Captures unhandled exceptions and sends them to the user's PostHog client.

    Installed in place of PostHog's built-in exception_autocapture so the capture goes through the
    client the telemetry manager built, with its sanitized ``capture_exception``.

    **An `$exception` is attributed like every other capture.** It is resolved
    through `TelemetryIdentity` rather than from a raw id, because the two
    interpreter hooks below are handed nothing but `(type, value, traceback)`:
    they cannot see the run that was in flight, so what they send is the runless
    identity of the stream, resolved once here. That resolution is what makes
    `anonymous` mode mean the same thing on this path as on every other — a mode
    that identifies nobody must not identify somebody when the process crashes.
    """

    # What PostHog stamps onto an error once a client has captured it. Every
    # later `capture_exception` of that same object returns without sending.
    POSTHOG_CAPTURE_MARKS = ("__posthog_exception_captured", "__posthog_exception_uuid")

    def __init__(
        self,
        posthog_client: "Posthog | None",
        identity: TelemetryIdentity,
    ):
        self._client = posthog_client
        self._identity = identity

        # Save original hooks
        self._original_excepthook = sys.excepthook
        self._original_threading_excepthook = threading.excepthook

        # Install our hooks
        sys.excepthook = self._exception_handler
        threading.excepthook = self._thread_exception_handler

    def close(self) -> None:
        """Restore original exception hooks."""
        sys.excepthook = self._original_excepthook
        threading.excepthook = self._original_threading_excepthook

    def _exception_handler(  # kw-only: ignore — installed as sys.excepthook; interpreter calls it positionally
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        """Handle uncaught exceptions from main thread."""
        self._capture_exception(exc_info=(exc_type, exc_value, exc_traceback))
        # Always call original handler to preserve default behavior
        self._original_excepthook(exc_type, exc_value, exc_traceback)

    def _thread_exception_handler(  # kw-only: ignore — installed as threading.excepthook; the interpreter calls it positionally
        self, args: threading.ExceptHookArgs
    ) -> None:
        """Handle uncaught exceptions from threads."""
        self._capture_exception(exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        # Always call original handler to preserve default behavior (prints to stderr)
        self._original_threading_excepthook(args)

    def _capture_exception(
        self,
        *,
        exc_info: tuple[type[BaseException], BaseException | None, TracebackType | None],
    ) -> None:
        """Capture exception to the PostHog client.

        An error already marked when the hook runs was captured by the host
        before it escaped, and is not sent again.
        """
        exc_type, exc_value, exc_traceback = exc_info

        # Skip if no actual exception value (can happen with threading.excepthook)
        if exc_value is None:
            return
        if self.is_marked_as_captured(exception=exc_value):
            return

        # Create the properly typed tuple for PostHog
        posthog_exc_info: tuple[type[BaseException], BaseException, TracebackType | None] = (
            exc_type,
            exc_value,
            exc_traceback,
        )

        if self._client:
            self._capture_to_client(client=self._client, posthog_exc_info=posthog_exc_info)

    def _capture_to_client(
        self,
        *,
        client: "Posthog",
        posthog_exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
    ) -> None:
        """Send the `$exception` under the identity the stream resolved.

        The identified and anonymous shapes are PostHog's own: an identified
        capture passes `distinct_id` and the groups it belongs to, an anonymous
        one passes no `distinct_id` at all and marks itself so, because PostHog
        rejects a null one and would otherwise mint a person for it.
        """
        try:
            if self._identity.distinct_id:
                client.capture_exception(posthog_exc_info, distinct_id=self._identity.distinct_id, groups=self._identity.groups or None)
            else:
                client.capture_exception(posthog_exc_info, properties={PostHogAttr.PROCESS_PERSON_PROFILE: False})
        except Exception as capture_exc:  # ruff: ignore[blind-except]
            # Telemetry must never break the app: a failed exception capture is logged at debug and swallowed.
            log.debug(f"Failed to capture exception to PostHog: {capture_exc}")

    @classmethod
    def is_marked_as_captured(cls, *, exception: "ExceptionArg") -> bool:
        """Whether PostHog has already sent this error, from any client, bare or as the triple."""
        exception_value = exception[1] if isinstance(exception, tuple) else exception
        return exception_value is not None and hasattr(exception_value, cls.POSTHOG_CAPTURE_MARKS[0])

    @classmethod
    def carry_capture_marks(cls, *, source: "ExceptionArg | None", target: "ExceptionArg | None") -> None:
        """Copy PostHog's capture marks from the error that was sent onto the error the caller holds.

        The two differ when the sent one is a redacted copy. Either argument may
        be bare or the `(type, value, traceback)` triple, as PostHog accepts both.
        """
        source_value = source[1] if isinstance(source, tuple) else source
        target_value = target[1] if isinstance(target, tuple) else target
        if source_value is None or target_value is None or source_value is target_value:
            return
        for mark in cls.POSTHOG_CAPTURE_MARKS:
            if hasattr(source_value, mark):
                setattr(target_value, mark, getattr(source_value, mark))
