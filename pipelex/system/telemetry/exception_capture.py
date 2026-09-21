import sys
import threading
from types import TracebackType
from typing import TYPE_CHECKING

from pipelex import log

if TYPE_CHECKING:
    # Deferred import: avoid pulling heavy SDK at module-load time
    from posthog import Posthog


class ExceptionCapture:
    """Captures unhandled exceptions and sends them to the user's PostHog client.

    Installed in place of PostHog's built-in exception_autocapture so the capture goes through the
    client the telemetry manager built (with its sanitized ``capture_exception``) and is attributed
    to the configured distinct id.
    """

    def __init__(
        self,
        posthog_client: "Posthog",
        distinct_id: str | None,
    ):
        self._client = posthog_client
        self._distinct_id = distinct_id

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
        """Capture exception to the PostHog client."""
        exc_type, exc_value, exc_traceback = exc_info

        # Skip if no actual exception value (can happen with threading.excepthook)
        if exc_value is None:
            return

        # Create the properly typed tuple for PostHog
        posthog_exc_info: tuple[type[BaseException], BaseException, TracebackType | None] = (
            exc_type,
            exc_value,
            exc_traceback,
        )

        try:
            self._client.capture_exception(posthog_exc_info, distinct_id=self._distinct_id)
        except Exception as capture_exc:  # ruff: ignore[blind-except]
            # Telemetry must never break the app: a failed exception capture is logged at debug and swallowed.
            log.debug(f"Failed to capture exception to PostHog: {capture_exc}")
