---
description: "Choose the error trackers Pipelex hands its errors to — the built-in posthog tracker, a tracker a plugin adds such as Sentry, or none."
---

# Error Tracking Configuration

Configuration section: `[runtime.error_tracking]`

## Overview

Beside its log lines, Pipelex hands the errors it meets to **error trackers**: a run that fails, an exception that reaches the top of a thread uncaught, an error a host caught and reported, and, in the API server, every response answered as an operator's fault. This section names the trackers that receive them.

```toml
[runtime.error_tracking]
trackers = ["posthog"]
```

The value above is the default.

## `trackers`

- A list of tokens, each naming a tracker a plugin registered. Every reported error reaches each tracker, in the list's order.
- `"posthog"` is built in. It sends each error's exception to the PostHog stream you configure in `telemetry.toml`, as an `$exception`, and sends nothing while that stream is off or `DO_NOT_TRACK` is set (see [Telemetry Configuration](telemetry-config.md#errors-on-your-posthog)).
- An installed plugin adds its own token, `"sentry"` for instance. Pipelex ships no tracker SDK of its own: the SDK comes with the plugin.
- An empty list, `trackers = []`, reports errors to no tracker and leaves the interpreter's exception hooks alone.

A token no installed plugin registered stops the boot with `UnknownErrorTrackerError`, which lists the registered tokens, and a token named twice is refused when the configuration is read.

A tracker receives identifiers, never a run's content: the error's code, where it was raised, the failing pipe, the run and request ids and the spans to join it on, beside the problem document in the operator's view. [Error Tracker Plugins](../../under-the-hood/error-tracker-plugins.md) describes what a tracker receives and how to write one.
