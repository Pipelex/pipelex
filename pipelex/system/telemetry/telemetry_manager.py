import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator, cast

import posthog
from opentelemetry.trace import Tracer as OTelTracer
from posthog import Posthog, new_context  # type: ignore[attr-defined]
from posthog.args import ExceptionArg, OptionalCaptureArgs
from typing_extensions import Unpack, override

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.system.caller_identity import CallerIdentity, get_current_caller_identity
from pipelex.system.environment import is_env_var_truthy
from pipelex.system.exceptions import PipelexError
from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.exception_capture import DualClientExceptionCapture
from pipelex.system.telemetry.otel_constants import OTelConstants, PostHogAttr, PostHogEvent
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig, TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy, StreamIdentityRule, TelemetryIdentity
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider

    from pipelex.system.job_metadata import RunMetadata


class TelemetryManager(TelemetryManagerAbstract):
    PRIVACY_NOTICE = "[Privacy: exception message redacted]"

    def __init__(
        self,
        telemetry_config: TelemetryConfig,
        remote_config: RemoteConfig | None,
        pipelex_telemetry_enabled: bool = False,
        gateway_api_key: str | None = None,
    ):
        """Initialize the TelemetryManager with custom and optional Pipelex telemetry.

        Args:
            telemetry_config: User's telemetry configuration.
            remote_config: Remote configuration for Pipelex Service (including telemetry).
            pipelex_telemetry_enabled: Whether Pipelex internal telemetry is enabled (for gateway).
            gateway_api_key: The user's Pipelex Gateway API key (required if pipelex_telemetry_enabled).
        """
        self.telemetry_config = telemetry_config
        self._pipelex_telemetry_enabled = pipelex_telemetry_enabled
        self._pipelex_distinct_id: str | None = None
        self._exception_capture: DualClientExceptionCapture | None = None

        # Create custom PostHog client only if user's telemetry is enabled
        self.custom_posthog_client: Posthog | None = None
        if telemetry_config.custom_posthog.mode.is_enabled:
            if not telemetry_config.custom_posthog.api_key:
                msg = "Custom PostHog API key is not set"
                raise PipelexUnexpectedError(msg)
            self.custom_posthog_client = Posthog(
                project_api_key=telemetry_config.custom_posthog.api_key,
                host=telemetry_config.custom_posthog.endpoint,
                disable_geoip=not telemetry_config.custom_posthog.geoip,
                debug=telemetry_config.custom_posthog.debug,
                on_error=self._handle_transmission_error,
            )

        # Create Pipelex PostHog client if gateway telemetry is enabled
        self.pipelex_posthog_client: Posthog | None = None
        if pipelex_telemetry_enabled:
            if gateway_api_key:
                self._pipelex_distinct_id = PipelexDetails.make_distinct_id(gateway_api_key)
            if not remote_config:
                msg = "Pipelex Gateway telemetry is enabled but remote config is not set"
                raise PipelexUnexpectedError(msg)
            pipelex_posthog_config = remote_config.posthog
            self.pipelex_posthog_client = Posthog(
                project_api_key=pipelex_posthog_config.project_api_key,
                host=pipelex_posthog_config.endpoint,
                disable_geoip=not pipelex_posthog_config.is_geoip_enabled,
                debug=pipelex_posthog_config.is_debug_enabled,
                on_error=self._handle_pipelex_transmission_error,
            )
            log.verbose("Pipelex Gateway telemetry enabled")

        # Create OTel tracer for AI tracing if enabled
        self._otel_tracer: OTelTracer | None
        self._tracer_provider: OTelTracerProvider | None
        if telemetry_config.custom_posthog.tracing.enabled or pipelex_telemetry_enabled:
            # AI tracing is enabled if either custom or pipelex telemetry wants it
            # Create redaction config from user settings for custom telemetry
            custom_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(posthog_config=telemetry_config.custom_posthog)
            if telemetry_config.pipelex_gateway:
                pipelex_gateway_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(
                    posthog_config=telemetry_config.pipelex_gateway.posthog
                )
            else:
                pipelex_gateway_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(posthog_config=None)
            self._otel_tracer, self._tracer_provider = OtelFactory.make_ai_tracer(
                custom_fallback_distinct_id=telemetry_config.custom_posthog.user_id,
                custom_run_identity_policy=RunIdentityPolicy.make_for_operator_stream(posthog_mode=telemetry_config.custom_posthog.mode),
                custom_posthog_client=self.custom_posthog_client if telemetry_config.custom_posthog.tracing.enabled else None,
                custom_redaction_config=custom_redaction_config,
                pipelex_posthog_client=self.pipelex_posthog_client,
                pipelex_gateway_redaction_config=pipelex_gateway_redaction_config,
                pipelex_distinct_id=self._pipelex_distinct_id,
                otlp_exporters=telemetry_config.otlp,
                langfuse_config=telemetry_config.langfuse,
            )
            log.verbose("AI tracing enabled: OpenTelemetry tracer created")
        else:
            self._otel_tracer = None
            self._tracer_provider = None
            log.verbose("AI tracing disabled: No OpenTelemetry tracer created")

        # Wrap capture_exception to sanitize before sending (for whichever clients are enabled)
        if self.custom_posthog_client:
            self._wrap_capture_exception(self.custom_posthog_client)
        if self.pipelex_posthog_client:
            self._wrap_capture_exception(self.pipelex_posthog_client)

        # Set global PostHog settings (prefer custom client, fall back to pipelex client)
        posthog.privacy_mode = True
        posthog.default_client = self.custom_posthog_client or self.pipelex_posthog_client

        # Set up dual-client exception autocapture if any client is enabled
        if self.custom_posthog_client or self.pipelex_posthog_client:
            self._exception_capture = self._make_exception_capture()

    def _make_exception_capture(self) -> DualClientExceptionCapture:
        """Build the exception autocapture, with each stream's identity rule.

        An unhandled exception is attributed when it arrives, not here: the
        capture reads back the caller of the pipe run the error escaped from, and
        falls back to the stream's own id only for an error that belongs to no
        caller. What is fixed here is each stream's rule, taken from the same
        settings as every other capture on that stream — which is what carries
        `anonymous` mode onto this path: a stream that identifies nobody must not
        identify somebody when the process crashes.

        Stated as its own method so the wiring can be exercised without the
        constructor, which builds live clients and registers a singleton.
        """
        return DualClientExceptionCapture(
            custom_posthog_client=self.custom_posthog_client,
            custom_identity_rule=StreamIdentityRule(
                fallback_distinct_id=self.telemetry_config.custom_posthog.user_id,
                run_identity_policy=RunIdentityPolicy.make_for_operator_stream(posthog_mode=self.telemetry_config.custom_posthog.mode),
            ),
            pipelex_posthog_client=self.pipelex_posthog_client,
            pipelex_identity_rule=StreamIdentityRule(
                fallback_distinct_id=self._pipelex_distinct_id,
                run_identity_policy=RunIdentityPolicy.NAMESPACED,
            ),
        )

    def _handle_transmission_error(  # kw-only: ignore — PostHog on_error callback, invoked positionally as (error, items)
        self, error: Exception | None, _items: list[dict[str, Any]]
    ) -> None:
        """Handle errors that occur during custom telemetry transmission.

        Args:
            error: The transmission error that occurred
            _items: List of telemetry items that failed to send
        """
        if error:
            log.error(f"Telemetry transmission error: {error}")

    def _handle_pipelex_transmission_error(  # kw-only: ignore — PostHog on_error callback, invoked positionally as (error, items)
        self, error: Exception | None, _items: list[dict[str, Any]]
    ) -> None:
        """Handle errors that occur during Pipelex telemetry transmission.

        Args:
            error: The transmission error that occurred
            _items: List of telemetry items that failed to send
        """
        if error:
            log.debug(f"Pipelex telemetry transmission error: {error}")

    def _wrap_capture_exception(self, client: Posthog) -> None:
        """Wrap a PostHog client's capture_exception method to sanitize exception messages.

        Args:
            client: The PostHog client to wrap.
        """
        original_capture_exception = client.capture_exception

        def sanitized_capture_exception(
            exception: ExceptionArg | None = None,
            **kwargs: Unpack[OptionalCaptureArgs],
        ) -> Any:
            """Capture exception with message sanitization for PipelexError subclasses.

            PostHog marks what it sent so a second capture of the same error is
            dropped, and what it sent may be a redacted copy rather than the
            error the caller holds. The mark is carried back onto the original,
            so the guard still works for a caller that captures an error and
            then lets it escape. Given nothing, PostHog would read the error
            being handled for itself, so that error is resolved first: both the
            check and the mark need it, and `None` can carry neither.

            PostHog's own `capture_exception` never raises into its caller, and
            the redaction in front of it must not either. An argument the SDK
            would decline, or a chain too deep to copy, drops the capture with a
            debug line: sending the original in its place is the one fallback
            that is not open, since it is what the redaction exists to stop.
            """
            try:
                resolved = self._resolved_exception_arg(exception=exception)
                if resolved is None or DualClientExceptionCapture.is_marked_as_captured(exception=resolved):
                    return None
                sanitized = self._sanitized_exception_arg(exception=resolved)
            except Exception as sanitize_exc:  # ruff: ignore[blind-except]
                log.debug(f"Dropped an exception capture the privacy redaction could not complete: {sanitize_exc!r}")
                return None
            result = original_capture_exception(sanitized, **kwargs)
            DualClientExceptionCapture.carry_capture_marks(source=sanitized, target=resolved)
            return result

        client.capture_exception = sanitized_capture_exception  # type: ignore[method-assign]

    @classmethod
    def _resolved_exception_arg(cls, *, exception: ExceptionArg | None) -> ExceptionArg | None:
        """Return `exception`, or when it is `None` the error being handled, which is what PostHog would read for itself.

        Resolved here rather than left to the SDK so the error can still be
        redacted, and so the capture mark lands on the error the caller holds.
        """
        if exception is not None:
            return exception
        current_type, current_value, current_traceback = sys.exc_info()
        if current_type is None or current_value is None:
            return None
        return (current_type, current_value, current_traceback)

    @classmethod
    def _sanitized_exception_arg(cls, *, exception: ExceptionArg) -> ExceptionArg:
        """Return what may go out in place of `exception`, in whichever form PostHog was handed.

        PostHog takes an error either bare or as the `(type, value, traceback)`
        triple an interpreter excepthook receives. And it does not send one
        exception: it walks `__cause__`, `__context__` and the members of an
        exception group, and sends the message of every error it reaches. A
        `PipelexError` message may repeat whatever the caller passed in — the
        path it was reading, a slice of the document that would not parse — so
        the message of every `PipelexError` in that graph is replaced by the
        privacy notice, wherever it sits, and not only the one at the top.

        The redaction goes by class. An error of another class keeps its own
        message, so one that copied a `PipelexError`'s text into it —
        `raise RuntimeError(f"failed: {error}") from error` — still sends that
        text; only the linked `PipelexError` itself is replaced.
        """
        if isinstance(exception, BaseException):
            return cls._redacted_exception_graph(exception=exception)
        _, exception_value, exception_traceback = exception
        if exception_value is None:
            return exception
        redacted_value = cls._redacted_exception_graph(exception=exception_value)
        if redacted_value is exception_value:
            return exception
        return (type(redacted_value), redacted_value, exception_traceback)

    @classmethod
    def _redacted_exception_graph(cls, *, exception: BaseException) -> BaseException:
        """Return `exception` itself when nothing it reaches is a `PipelexError`, else a redacted copy of all of it.

        The copy is never written back: the live exception is the one the
        interpreter goes on to print and a host may still be holding, so only a
        copy of the graph has its links pointed at the stand-ins.
        """
        if not cls._reaches_pipelex_error(exception=exception):
            return exception
        redacted = cls._redacted_link(exception=exception, copies={})
        # The root is never cut: only a link back to an exception still being copied is.
        assert redacted is not None
        return redacted

    @classmethod
    def _reaches_pipelex_error(cls, *, exception: BaseException) -> bool:
        """Whether a `PipelexError` sits anywhere PostHog would walk from `exception`.

        A loop and not a recursion, as PostHog's own walk is: the SDK sends a
        chain as long as the recursion limit, and the check deciding whether it
        needs redacting must not be what fails on it.
        """
        pending: list[BaseException | None] = [exception]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current is None or id(current) in visited:
                continue
            visited.add(id(current))
            if isinstance(current, PipelexError):
                return True
            pending.extend((current.__cause__, current.__context__, *cls._group_members(exception=current)))
        return False

    @classmethod
    def _group_members(cls, *, exception: BaseException) -> tuple[BaseException, ...]:
        """The members PostHog expands out of an exception group, or nothing for any other error."""
        if isinstance(exception, BaseExceptionGroup):
            return cast("BaseExceptionGroup[BaseException]", exception).exceptions
        return ()

    @classmethod
    def _redacted_link(cls, *, exception: BaseException | None, copies: dict[int, BaseException | None]) -> BaseException | None:
        """Copy one exception of the graph, with its own links redacted in turn.

        `copies` maps an original to its copy so a shared or cyclic link is
        copied once. An entry of `None` means that exception is still being
        copied, and a link back to it is cut rather than followed forever.
        """
        if exception is None:
            return None
        exception_id = id(exception)
        if exception_id in copies:
            return copies[exception_id]
        copies[exception_id] = None
        copied: BaseException
        if isinstance(exception, PipelexError):
            copied = cls._redacted_stand_in(exception=exception)
        elif isinstance(exception, BaseExceptionGroup):
            group = cast("BaseExceptionGroup[BaseException]", exception)
            members = [cls._redacted_link(exception=member, copies=copies) for member in cls._group_members(exception=group)]
            kept_members = [member for member in members if member is not None]
            copied = cast("BaseException", group.derive(kept_members)) if kept_members else Exception(type(group).__name__)
            if hasattr(group, "__notes__"):
                copied.__notes__ = list(group.__notes__)
        else:
            copied = cls._plain_copy(exception=exception)
        copied.__traceback__ = exception.__traceback__
        copies[exception_id] = copied
        copied.__cause__ = cls._redacted_link(exception=exception.__cause__, copies=copies)
        copied.__context__ = cls._redacted_link(exception=exception.__context__, copies=copies)
        copied.__suppress_context__ = exception.__suppress_context__
        return copied

    @classmethod
    def _redacted_stand_in(cls, *, exception: PipelexError) -> PipelexError:
        """Build a same-class stand-in for `exception` whose message is the privacy notice.

        `__new__` without `__init__` is the point: the instance comes out with an
        empty `__dict__`, so none of the subclass's own attributes — the
        concepts it was comparing, the file it was reading — travel with it. What
        goes out is the class name, the notice and the traceback.
        """
        exception_type = type(exception)
        stand_in = exception_type.__new__(exception_type)
        stand_in.args = (cls.PRIVACY_NOTICE,)
        stand_in.__traceback__ = exception.__traceback__
        return stand_in

    @classmethod
    def _plain_copy(cls, *, exception: BaseException) -> BaseException:
        """Copy an error that is not a `PipelexError`, message and attributes included, without running its `__init__`.

        Its own message is sent as it is, because the redaction goes by class:
        a message that copied a `PipelexError`'s text travels with that text.
        Its attributes stay because a subclass's `__str__` may read them. Only
        the links are rewritten, by `_redacted_link`.
        """
        exception_type = type(exception)
        try:
            copied = exception_type.__new__(exception_type, *exception.args)
            copied.args = exception.args
            copied.__dict__.update(
                {name: value for name, value in exception.__dict__.items() if name not in DualClientExceptionCapture.POSTHOG_CAPTURE_MARKS}
            )
        except Exception:  # ruff: ignore[blind-except]
            # A class whose construction cannot be reproduced keeps its name and message, and nothing else.
            return Exception(f"{exception_type.__name__}: {exception}")
        return copied

    @override
    def setup(self, *, integration_mode: IntegrationMode):
        pass

    @override
    def teardown(self):
        # First, restore original exception hooks to avoid capturing exceptions during shutdown
        if self._exception_capture:
            try:
                self._exception_capture.close()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Telemetry teardown must never break the app: a close failure is logged at debug and swallowed.
                log.debug(f"Error closing exception capture: {exc}")

        # Then, shutdown the TracerProvider to flush all pending spans
        # This MUST happen before PostHog shutdown, otherwise spans won't be exported
        if self._tracer_provider:
            try:
                log.verbose("Shutting down OTel TracerProvider (flushing pending spans)...")
                self._tracer_provider.shutdown()
                log.verbose("OTel TracerProvider shutdown complete")
            except Exception as exc:  # ruff: ignore[blind-except]
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during TracerProvider shutdown: {exc}")

        # Then shutdown custom PostHog client
        if self.custom_posthog_client:
            try:
                self.custom_posthog_client.shutdown()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during custom PostHog shutdown: {exc}")

        # Then shutdown Pipelex PostHog client
        if self.pipelex_posthog_client:
            try:
                self.pipelex_posthog_client.shutdown()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during Pipelex PostHog shutdown: {exc}")

        # Clear singleton instance
        TelemetryManagerAbstract.clear_instance()

    @override
    def track_event(
        self,
        event_name: EventName,
        *,
        properties: dict[EventProperty, Any] | None = None,
        run_metadata: "RunMetadata | None" = None,
    ):
        # We copy the incoming properties to avoid modifying the original dictionary
        # and to convert the keys to str
        # and to remove the properties that are in the redact list
        tracked_properties: dict[str, Any]
        if properties:
            tracked_properties = {key: value for key, value in properties.items() if key not in self.telemetry_config.redact_properties}
        else:
            tracked_properties = {}

        caller_identity = self.resolve_event_caller_identity(run_metadata=run_metadata)

        # Track to custom PostHog based on user's posthog.mode
        match self.telemetry_config.custom_posthog.mode:
            case PostHogMode.ANONYMOUS:
                # The operator chose not to identify people, and that choice covers
                # their users too: no run identity is applied and no groups are sent.
                self._capture_custom_event(event_name, properties=tracked_properties, identity=TelemetryIdentity.make_anonymous())
            case PostHogMode.IDENTIFIED:
                if not self.telemetry_config.custom_posthog.user_id:
                    log.error(f"Could not track event '{event_name}' as identified because user_id is not set, tracking as anonymous")
                    self._capture_custom_event(event_name, properties=tracked_properties, identity=TelemetryIdentity.make_anonymous())
                else:
                    self._capture_custom_event(
                        event_name,
                        properties=tracked_properties,
                        identity=TelemetryIdentity.make_from_caller_identity(
                            caller_identity=caller_identity,
                            fallback_distinct_id=self.telemetry_config.custom_posthog.user_id,
                            run_identity_policy=RunIdentityPolicy.DIRECT,
                        ),
                    )
            case PostHogMode.OFF:
                log.verbose(f"Custom telemetry is off, skipping event '{event_name}' for custom client")

        # Always track to Pipelex PostHog if enabled (independent of posthog.mode)
        if self._pipelex_telemetry_enabled:
            self._track_to_pipelex(event_name, properties=tracked_properties, caller_identity=caller_identity)

    @classmethod
    def resolve_event_caller_identity(cls, *, run_metadata: "RunMetadata | None") -> CallerIdentity | None:
        """The caller an event is attributed to: its run's, else the one in scope, else nobody.

        The run an emitter hands over is the most specific fact there is, so it
        wins. An emitter with no run in hand — the validation sweep, which is not
        a run — is still working for somebody when a host or a pipe run opened a
        caller scope around it, and reads that caller rather than falling back to
        the stream's constant. Only an event emitted outside every scope, such as
        a CLI command, belongs to nobody.
        """
        if run_metadata is not None:
            return CallerIdentity.make_from_run_metadata(run_metadata=run_metadata)
        return get_current_caller_identity()

    def _capture_custom_event(self, event_name: str, *, properties: dict[str, Any], identity: TelemetryIdentity):
        """Capture one event on the operator's stream, under the identity resolved for it.

        Captures a COPY of the properties, because the same dict is offered to
        both streams and the anonymous branch below stamps
        `$process_person_profile` on the one it sends. Without the copy that mark
        travelled on to the Pipelex capture, labelling an event sent WITH a
        distinct_id as having no person profile.
        """
        if not self.custom_posthog_client:
            log.error("Could not track event to custom telemetry because custom_posthog_client is not set")
            return
        capture_properties = dict(properties)
        if identity.distinct_id:
            self.custom_posthog_client.capture(
                event_name,
                distinct_id=identity.distinct_id,
                properties=capture_properties,
                groups=identity.groups or None,
            )
            log.verbose(f"Tracked identified event '{event_name}' with properties: {capture_properties}")
        else:
            capture_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
            self.custom_posthog_client.capture(event_name, properties=capture_properties)
            log.verbose(f"Tracked anonymous event '{event_name}' with properties: {capture_properties}")

    def _track_to_pipelex(self, event_name: str, *, properties: dict[str, Any], caller_identity: CallerIdentity | None = None):
        """Track event to Pipelex's PostHog (always identified, always namespaced).

        The stream has no mode to turn identification off, but it is a shared
        project: a run's own user reaches it only as a digest taken inside the
        gateway-key hash, and the hash itself is what an event with no run
        reports under. The run's groups do not travel here at all.
        """
        if not self.pipelex_posthog_client or not self._pipelex_distinct_id:
            log.error("Could not track event to Pipelex telemetry because pipelex_posthog_client or _pipelex_distinct_id is not set")
            return
        identity = TelemetryIdentity.make_from_caller_identity(
            caller_identity=caller_identity,
            fallback_distinct_id=self._pipelex_distinct_id,
            run_identity_policy=RunIdentityPolicy.NAMESPACED,
        )
        self.pipelex_posthog_client.capture(
            event_name,
            distinct_id=identity.distinct_id,
            properties=dict(properties),
            groups=identity.groups or None,
        )
        log.verbose(f"Tracked event '{event_name}' to Pipelex telemetry")

    @override
    @contextmanager
    def telemetry_context(self) -> Generator[None, None, None]:
        """Context manager that uses PostHog's new_context when telemetry is enabled."""
        with new_context():
            yield

    @override
    def is_custom_portkey_logging_enabled(self, *, is_debug_configured: bool) -> bool:
        is_debug: bool = is_debug_configured
        if not is_debug and self.telemetry_config.custom_portkey.force_debug_enabled:
            log.verbose("Force-enabling Portkey logging (debug mode) because custom_portkey.force_debug_enabled is set in telemetry configuration")
            is_debug = True
        if is_debug and is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.warning(
                f"Disabling Custom Portkey logging (debug mode) "
                f"because '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}' is set and that setting takes precedence"
            )
            is_debug = False
        return is_debug

    @override
    def is_custom_portkey_tracing_enabled(self) -> bool:
        if self.telemetry_config.custom_portkey.force_tracing_enabled and not is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.info("Force-enabling Portkey tracing because custom_portkey.force_tracing_enabled is set in telemetry configuration")
            return True
        else:
            return False

    @override
    def is_pipelex_gateway_portkey_logging_enabled(self, *, is_debug_configured: bool) -> bool:
        is_debug: bool = is_debug_configured
        if (
            not is_debug
            and self.telemetry_config.pipelex_gateway
            and self.telemetry_config.pipelex_gateway.portkey
            and self.telemetry_config.pipelex_gateway.portkey.force_debug_enabled
        ):
            log.verbose(
                "Force-enabling Portkey logging (debug mode) because pipelex_gateway.portkey.force_debug_enabled is set in telemetry configuration"
            )
            is_debug = True
        if is_debug and is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.warning(
                f"Disabling Pipelex Gateway Portkey logging (debug mode) "
                f"because '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}' is set and that setting takes precedence"
            )
            is_debug = False
        return is_debug

    @override
    def is_pipelex_gateway_portkey_tracing_enabled(self) -> bool:
        if (
            self.telemetry_config.pipelex_gateway
            and self.telemetry_config.pipelex_gateway.portkey
            and self.telemetry_config.pipelex_gateway.portkey.force_tracing_enabled
            and not is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY)
        ):
            log.verbose(
                "Force-enabling Pipelex Gateway Portkey tracing "
                "because pipelex_gateway.portkey.force_tracing_enabled is set in telemetry configuration"
            )
            return True
        else:
            return False

    @override
    def get_otel_tracer(self) -> OTelTracer | None:
        return self._otel_tracer

    @property
    @override
    def capture_content_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.content

    @property
    @override
    def capture_pipe_codes_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.pipe_codes

    @property
    @override
    def capture_output_class_name_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.output_class_names

    @property
    @override
    def capture_content_max_length(self) -> int | None:
        return self.telemetry_config.custom_posthog.tracing.capture.content_max_length

    @property
    @override
    def is_langfuse_enabled(self) -> bool:
        return self.telemetry_config.langfuse.enabled

    @property
    @override
    def is_pipelex_telemetry_enabled(self) -> bool:
        return self._pipelex_telemetry_enabled

    @override
    def handle_trace_start(self, *, trace_name: str, trace_name_redacted: str, trace_id: int, run_metadata: "RunMetadata | None" = None) -> None:
        """Hook to do something when a trace starts.

        Emits a trace start event to establish the trace name in PostHog.
        We send a minimal $ai_span event with the trace_name as the span name.
        This event is sent directly (not via OTel spans) to ensure it arrives
        before any batched pipe spans, establishing the correct trace name.

        Args:
            trace_name: Full trace name with pipe code (for custom telemetry).
            trace_name_redacted: Redacted trace name without pipe code (for Pipelex telemetry).
            trace_id: The trace ID.
            run_metadata: The run this trace belongs to. Carries the identity the
                event is attributed to, resolved exactly as every pipe span under
                the same trace will be, so the trace's first event and its spans
                land on the same person. None reads the caller in scope, and
                only with none in scope leaves the stream's fallback.
        """
        caller_identity = self.resolve_event_caller_identity(run_metadata=run_metadata)
        log.verbose(
            f"[Telemetry] Emitting trace start event:\n"
            f"  trace_name='{trace_name}'\n"
            f"  trace_name_redacted='{trace_name_redacted}'\n"
            f"  trace_id={trace_id:032x}"
        )

        # Send to custom PostHog if configured (uses full trace name based on user's capture settings)
        if self.custom_posthog_client and self.telemetry_config.custom_posthog.tracing.enabled:
            # Use full or redacted trace name based on user's capture_pipe_codes setting
            custom_trace_name = trace_name if self.telemetry_config.custom_posthog.tracing.capture.pipe_codes else trace_name_redacted
            custom_properties: dict[str, Any] = {
                PostHogAttr.TRACE_ID: f"{trace_id:032x}",
                PostHogAttr.SPAN_NAME: custom_trace_name,
                PostHogAttr.TRACE_NAME: custom_trace_name,
            }
            custom_identity = TelemetryIdentity.make_from_caller_identity(
                caller_identity=caller_identity,
                fallback_distinct_id=self.telemetry_config.custom_posthog.user_id,
                run_identity_policy=RunIdentityPolicy.make_for_operator_stream(posthog_mode=self.telemetry_config.custom_posthog.mode),
            )
            if custom_identity.distinct_id:
                self.custom_posthog_client.capture(
                    distinct_id=custom_identity.distinct_id,
                    event=PostHogEvent.SPAN,
                    properties=custom_properties,
                    groups=custom_identity.groups or None,
                )
            else:
                custom_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
                self.custom_posthog_client.capture(
                    event=PostHogEvent.SPAN,
                    properties=custom_properties,
                )

        # Send to Pipelex PostHog if gateway telemetry is enabled (always uses redacted trace name)
        if self.pipelex_posthog_client:
            pipelex_properties: dict[str, Any] = {
                PostHogAttr.TRACE_ID: f"{trace_id:032x}",
                PostHogAttr.SPAN_NAME: trace_name_redacted,
                PostHogAttr.TRACE_NAME: trace_name_redacted,
            }
            pipelex_identity = TelemetryIdentity.make_from_caller_identity(
                caller_identity=caller_identity,
                fallback_distinct_id=self._pipelex_distinct_id,
                run_identity_policy=RunIdentityPolicy.NAMESPACED,
            )
            if pipelex_identity.distinct_id:
                self.pipelex_posthog_client.capture(
                    distinct_id=pipelex_identity.distinct_id,
                    event=PostHogEvent.SPAN,
                    properties=pipelex_properties,
                    groups=pipelex_identity.groups or None,
                )
            else:
                pipelex_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
                self.pipelex_posthog_client.capture(
                    event=PostHogEvent.SPAN,
                    properties=pipelex_properties,
                )
