---
title: "Error Tracker Plugins"
description: "How Pipelex hands the errors it meets to the error trackers an operator selects by config, what a tracker receives about each error and must never send, the built-in posthog tracker, and how to author an out-of-tree tracker such as Sentry."
---

# Error Tracker Plugins

A log line says that something failed; an **error tracker** groups the failures into issues, counts them and alerts on them. Pipelex hands every error it reports to the error trackers installed at boot, beside its log sink. Which trackers those are comes from data: one config field, `runtime.error_tracking.trackers`, names them, and an **error tracker plugin** is what teaches Pipelex how to build each one.

Core names no tracker by import or by string, and **Pipelex ships no vendor SDK**. The built-in tracker, `posthog`, which sends an exception to the operator's own PostHog as an `$exception`, is a plugin too, the `ErrorTrackerPlugin`, riding the same seam an out-of-tree package rides. A Sentry tracker, for instance, lives in the package that contributes it and imports `sentry_sdk` when its factory runs.

This seam has the shape of the [log sink](log-sink-plugins.md) seam, a keyed registry with a config-selected result, with one difference: a process installs one log sink but any number of error trackers, so the config names a list of tokens.

---

## The seam in one view

```
RuntimeBoot.setup
  └─ build_registrar(config, builtin_plugins=…, …)   # pure, import-light
       └─ plugin.register(registrar)                  # ErrorTrackerPlugin is one
            └─ registrar.add_error_tracker(method=…, factory=…)
  └─ secrets_provider = …
  └─ telemetry_manager = …                            # the operator's telemetry streams
  └─ ErrorTrackerRegistry(registrar.error_trackers)
  └─ trackers = registry.make_error_trackers(config=runtime.error_tracking,
                                             secrets_provider=…, telemetry_manager=…)
  └─ install_error_trackers(trackers=trackers)        # and the interpreter's exception hooks, when there is one
teardown
  └─ reset_error_trackers()                           # closes each tracker, puts the hooks back, before telemetry teardown
```

Every token is looked up before any factory runs, so a token nobody registered stops the boot before a tracker initialises its SDK. A factory that finds nothing to report to in this process, a DSN left unset for instance, returns `None` and the boot goes on without that tracker.

---

## What reaches the trackers

Three paths report an error, each tagged with its **kind** (`ErrorReportKind`):

| Kind | Who reports it | When |
|------|----------------|------|
| `run_failure` | The runtime that ran the run, at the run's boundary (`PipeRun`) | A run fails with a fault the operator must fix. What is reported is the exception that escapes the run, which its caller receives: the pipe's own, or one the run's tail raised after the pipe executed, such as its trace failing to close or assemble, or the storage or a host's webhook failing to receive its results. Its anonymous usage statistics are best effort: a failure of theirs is logged and never fails the run. A run sends one report: when the pipe failed and its tail raised too, the tail's exception replaces the pipe's and is the one reported. A cancelled run reports nothing: whatever its tail raises is logged and never replaces the cancellation. A run whose pipe failed and which is then cancelled during its tail, during its delivery for instance, reports the pipe's error before the cancellation propagates. A dry run, a validation's or `pipelex run --dry-run`, does not report. |
| `uncaught` | The interpreter hooks, `sys.excepthook` and `threading.excepthook`, installed while a tracker is | An exception reaches the top of the main thread or of another thread. Interruptions such as `KeyboardInterrupt` are not reported. The hooks that were there before are still called. |
| `handled` | A host, or the runtime, through `report_exception` or `report_problem` (`pipelex.system.error_tracking.error_tracking`) | Something caught the error and went on. The API server reports this way every response it answers as an operator's fault, an error-level record, and a failure that ends a request after its response had started, which no response can answer any more. |

**Only what the server has to fix reaches the trackers, never a caller's mistake.** One rule decides, from the HTTP status the failure is, or would be, answered with and from its problem's domain, who must act on it: `reaches_error_trackers(status=..., domain=...)` in `pipelex.system.error_tracking.error_tracking`.

- **A 4xx is not reported.** It is the caller's to act on, a mistake or a benign conflict, whatever its domain.
- **A `501` is not reported.** It says this deployment does not offer what was asked, custom code without a sandbox or a document engine it was not given. The operator decides whether to offer it, but nothing is broken, and the caller meets the refusal each time it asks again, so reporting it would let any caller flood the trackers.
- **Any other 5xx is reported when its domain is `runtime` or `operator`**, and not when it is `input`, `method` or `account`, a refusal the caller can avoid, such as its own webhook receiver refusing a delivery.

A failed run is weighed by its problem's status, `problem_status_of` in `pipelex.errors.problem`, which is the status the API server would answer it with, and the API server weighs a response by the status it answers. The API server logs at `error` exactly the failures this rule reports, so its error-level records and its reports never disagree. Whether the caller's failures should reach the trackers too is an open decision; every report already carries its domain as the `error.domain` tag, so reporting them would change that one predicate and nothing else.

**One error, one report.** An exception reported once is marked, and a later report of it, or of an error raised `from` it, is skipped. A run's failure reported at the run's boundary is therefore not reported again when the API server answers it, nor when a host lets it reach the interpreter's hook, nor when a host raises its own error from it. An exception whose class refuses the mark, one whose `__setattr__` or `__getattribute__` raises, goes unmarked and may be reported twice, but never fails the reporter.

**Reporting never fails the reporter.** With no tracker installed, a report builds nothing. Reading and writing the marks the runtime leaves on an exception, the reported mark and the Pipelex span it was raised in, run the exception class's own code, so they are guarded: whatever that code raises, the exception goes unmarked and the error it stands for is the one that propagates. A report that cannot be built, from an exception whose `__str__` raises for instance, is logged at debug level and dropped, and the interpreter hooks still hand the exception on to the hooks that were there before. A tracker is a plugin's code, so each call is guarded: a failing tracker is logged at debug level and the other trackers still receive the error.

A host whose runs fail outside `PipeRun`, a distributed worker for instance, reports its run's failure itself, with `report_exception(exception=..., kind=ErrorReportKind.RUN_FAILURE, ...)`.

---

## The contract

### `ErrorTrackerFactoryFn`

A tracker is produced by a typed callable (`pipelex/plugins/error_tracker_registry.py`):

```python
class ErrorTrackerFactoryFn(Protocol):
    def __call__(
        self,
        config: ErrorTrackingConfig,
        /,
        *,
        secrets_provider: SecretsProviderAbstract,
        telemetry_manager: TelemetryManagerAbstract,
    ) -> ErrorTrackerAbstract | None: ...
```

It is called once at boot, after the telemetry manager is built, never at registration. The secrets provider is how a factory reads a credential; the telemetry manager is the one this boot built, which the built-in `posthog` tracker reports through and any other tracker ignores.

A plugin contributes one factory per token it serves, in its `register`:

```python
registrar.add_error_tracker(method="sentry", factory=_make_sentry_error_tracker)
```

`register` stays side-effect-free, as for every capability: `pipelex plugins list` shows the contribution as `error tracker sentry`. Two plugins registering the same token fail discovery with `DuplicateErrorTrackerError`, naming both.

### `ErrorTrackerAbstract`

The factory returns an `ErrorTrackerAbstract` (`pipelex/system/error_tracking/error_tracker.py`):

```python
class ErrorTrackerAbstract(ABC):
    @abstractmethod
    def report(self, *, report: ErrorReport) -> None: ...  # once per reported error

    def close(self) -> None: ...  # once, at teardown; flush what was queued
```

`report` runs on the thread that met the error, an interpreter hook's thread included, so it returns quickly: a tracker whose SDK sends over the network queues the event, as the PostHog and Sentry SDKs do.

### `ErrorReport`

Every tracker receives the same frozen `ErrorReport` (`pipelex/system/error_tracking/error_report.py`):

| Member | What it is |
|--------|------------|
| `kind` | `run_failure`, `uncaught` or `handled` |
| `problem` | The error's problem document in the **operator's view**, the view of whoever runs the runtime (see [Error Model](error-model.md)): a Pipelex error's own, else `runtime.unexpected` naming the foreign exception's class and never quoting its text, the same problem a failed run's webhooks receive |
| `exception` | The exception, or `None` for a problem reported without one |
| `error_type`, `error_chain` | The exception's class, and the classes along its cause chain |
| `frames` | The frames down to where the first exception was raised, each `module:line in function`, with no source line and no locals |
| `raise_site` | Where the first exception of the cause chain was raised, as `module:function`, with no line number so that a release moving the code keeps the issue |
| `pipeline_run_id`, `request_id` | The run and the request, from the reporter, else the problem, else the bound log context |
| `pipe_code` | The failing pipe: the pipe the problem locates, else the pipe the reporter named |
| `trace_id`, `span_id` | The Pipelex span the error was raised in, which stays readable after that span closed |
| `host_trace_id`, `host_span_id` | OpenTelemetry's current span when the error was reported, the host's own |

Three derived members give a tracker its grouping and its tags, spelled with the keys a log line about an error already carries:

- **`code`** is the problem's registry code.
- **`fingerprint`** is `[code, raise_site]`, or `[code]` with no exception: one fault is one issue, whatever its message says and whichever organization's pipe met it.
- **`tags`** holds `error.code`, `error.domain`, `error.report_kind`, `error.type`, `error.raise_site`, `pipe_code`, `pipeline_run_id`, `request_id`, `pipelex.trace_id` and `pipelex.span_id`, only those that are set; **`fields`** adds `error.chain`.

### What a tracker must never send

**A tracker never sends a run's content.** It reads the exception's class and stack, never the locals of its frames; it attaches no request body, no input and no output of a run, and none of the personal data its SDK would collect by default. The problem's sentences, its parameters and its `diagnostics.message` are written for an operator and may quote the caller's own submission, so a tracker that sends its events off the machine sends the identifiers above and leaves those members out unless its operator chose otherwise.

---

## The built-in `posthog` tracker

`pipelex/providers/error_trackers/error_tracker_plugin.py` registers the `posthog` token. Its factory asks the telemetry manager for the tracker of the operator's own PostHog stream (`TelemetryManager.make_error_tracker`), which is `None` whenever that stream is off: `[custom_posthog]` disabled in `telemetry.toml`, an integration mode the stream is not allowed in, or `DO_NOT_TRACK` set. `PostHogErrorTracker` sends the report's exception as an `$exception`, attributed to the caller the run belonged to as described in [Telemetry](../setup/telemetry.md#work-that-is-not-a-run-and-crashes), with every exception message redacted: each error along the cause chain and inside exception groups, whatever its class, a `PipelexError`, a `ValueError` quoting what it refused or a pydantic `ValidationError` rendering its input, goes out as its class name and a privacy notice, without its attributes or its notes. Each frame goes out as its module, function and line, without the source lines around it or its file's path, which the client's `before_send` strips. The frame's file name is rewritten from its module, `pipelex/tools/misc.py` for the module `pipelex.tools.misc`, because PostHog writes the absolute path there for a module of a namespace package, such as `opentelemetry` or `google`, and for a module it does not know. A report with no exception sends nothing, and an exception PostHog already captured is not sent again.

The plugin is not core-unconditional: a process may report its errors nowhere. One that disables it while `runtime.error_tracking.trackers` still names `posthog` stops at boot with `UnknownErrorTrackerError`.

---

## Selecting trackers by config

```toml
# .pipelex/pipelex.toml
[runtime.error_tracking]
trackers = ["posthog", "sentry"]   # every reported error reaches each, in this order
```

The tokens are open strings, validated at registry lookup: a token no installed plugin registered surfaces as `UnknownErrorTrackerError` at boot, which lists the registered ones. A token named twice is refused when the configuration is read. An empty list installs no tracker and no interpreter hook. The shipped default is `["posthog"]`, which reports nothing unless the operator turned their PostHog stream on.

An external tracker has no settings section of its own in `ErrorTrackingConfig`; it reads its own configuration, a DSN for instance, from the environment or the secrets provider it is handed.

---

## Writing an out-of-tree tracker

A tracker package declares an entry point in the kernel group and registers its token:

```toml
# pyproject.toml of the package
[project.entry-points."pipelex.plugins.kernel"]
my_tracker = "my_package.plugin:MyTrackerPlugin"
```

```python
class MyTrackerPlugin:
    name = "my_tracker"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_error_tracker(method="my_tracker", factory=_make_my_tracker)


def _make_my_tracker(
    config: ErrorTrackingConfig,
    /,
    *,
    secrets_provider: SecretsProviderAbstract,
    telemetry_manager: TelemetryManagerAbstract,
) -> ErrorTrackerAbstract | None:
    dsn = os.environ.get("MY_TRACKER_DSN")
    if not dsn:
        return None  # nothing to report to in this process
    import my_tracker_sdk  # the SDK is imported here, never at registration

    return MyTracker(client=my_tracker_sdk.Client(dsn=dsn, send_default_pii=False, include_locals=False))
```

`MyTracker.report` groups by `report.fingerprint`, sets `report.tags`, and joins its event to the trace through `report.trace_id` and `report.span_id`, or `report.host_trace_id` and `report.host_span_id` when the host exports its own spans to the tracker.

To test a host that reports through the seam, `pipelex.test_extras.recording_error_tracker` installs a `RecordingErrorTracker` for a block and keeps every report it receives:

```python
with recording_error_tracker() as recorder:
    ...
assert recorder.reports[0].code == "model.unknown"
```

---

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| `runtime.error_tracking.trackers` names no registered tracker | `UnknownErrorTrackerError` (lists the registered tokens), at boot, before any factory runs |
| `runtime.error_tracking.trackers` names a tracker twice | a configuration validation error |
| two plugins register the same token | `DuplicateErrorTrackerError` (names both plugins) |
| a tracker raises while reporting or closing | logged at debug level; the reporter and the other trackers carry on |
| a report cannot be built | logged at debug level; nothing is sent and the reporter carries on |
| a tracker's factory raises at boot | the boot stops with that error, after closing the trackers already built |
