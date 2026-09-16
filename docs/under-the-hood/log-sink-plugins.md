---
title: "Log Sink Plugins"
description: "How Pipelex selects where its log records go by config, the keyed-registry-plus-config-selected-singleton seam a log sink plugin rides, the shipped json, console and otlp sinks, and how to author an out-of-tree sink."
---

# Log Sink Plugins

Every record the runtime emits, a `log.info(...)` in a pipe operator, a warning from a provider, the failure line of a run, leaves the process through a single **log sink** installed on the root logger at boot. Which sink that is comes entirely from data: one config field, `runtime.log.sink`, names a sink, and a **log sink plugin** is what teaches Pipelex how to build it.

Core names no sink by import or by string. The built-in sinks (`json`, `console`, `otlp`) are a plugin too, the always-on `LogSinkPlugin`, riding the exact same seam an out-of-tree package would. This page documents that seam, the contract a plugin registers, what a sink reads off a record, and how to write one.

This is the third application of the mechanism the [storage provider](storage-provider-plugins.md) seam introduced and the [secrets provider](secrets-provider-plugins.md) seam reused; the three pages describe the same shape with the nouns swapped, and this one adds what is particular to logging: the sink is resolved after logging is already configured, and every sink shares one record contract.

---

## The same shape as storage and secrets

A sink is a **process-global singleton selected by its own config key**, independent of the orchestrator and of any call, so it rides the **keyed registry + config-selected singleton** mechanism rather than a per-call registry or a hub slot:

> Plugins register N sink factories into a registry keyed by an open `method` token. At boot, core reads `runtime.log.sink`, looks that token up in the registry, calls the factory to produce the one sink, and installs that sink's handler on the root logger.

There is no `match runtime.log.sink:` anywhere in boot: the token set is open, so validation *is* the registry lookup. Adding a sink means registering a factory for its token; nothing in core changes. Every log call in the runtime and in your own code keeps going through `from pipelex import log`, and is unaffected by which sink was selected.

---

## The seam in one view

```
RuntimeBoot.__init__
  └─ log.configure(runtime.log)            # levels set; a holding handler takes every record
RuntimeBoot.setup
  └─ build_registrar(config, builtin_plugins=…, …)   # pure, import-light
       ├─ for each built-in plugin                   (LogSinkPlugin is one)
       └─ for each installed entry point in the requested groups
            └─ plugin.register(registrar)            # side-effect-free
                 └─ registrar.add_log_sink(method=…, factory=…)
  └─ LogSinkRegistry(registrar.log_sinks)
  └─ sink = registry.get_required(method=runtime.log.sink)(runtime.log)
  └─ log.install_sink(sink)                # the sink's handler replaces the holding handler,
                                           # which replays what it held through it, in order
teardown
  └─ log.reset()                           # flushes and closes the sink's handler, removes it
```

### Configured before it is selected

Logging is configured as soon as the configuration is read, in `RuntimeBoot.__init__`, so that everything the boot says afterwards is a record on a module-named logger at the configured level. The sink, though, is a plugin capability, and plugin discovery runs a little later, in `setup()`, once the boot knows which built-ins and which entry-point groups it reads. Rather than choose a default renderer for that window, `configure` installs a **holding handler** that keeps every record, and `install_sink` replays them through the selected sink's handler the moment it is installed, in the order they were emitted. A boot's own lines are therefore rendered by the sink the configuration chose, never dropped and never written in a shape nothing chose.

The sink is the first capability resolved out of the registrar, ahead of secrets and storage, precisely so that every later line of the boot goes through it. A boot that dies before that point, on the gateway terms gate for instance, releases its process globals through `log.reset()`, which closes the holding handler: what it still holds gets the stdlib's last-resort treatment, a warning or worse reaches stderr and the rest is dropped, exactly as a record emitted before `configure` would be.

`pipelex doctor`, which deliberately bypasses `Pipelex.make` to diagnose a broken configuration, selects its sink the same way: the pure `build_registrar` discovery, then the `runtime.log.sink` lookup.

---

## The contract

### `LogSinkFactoryFn`

A sink is produced by a typed **callable**, whole log config in, sink out (`pipelex/plugins/log_sink_registry.py`):

```python
LogSinkFactoryFn = Callable[[LogConfig], LogSink]
```

Passing the whole `LogConfig` is deliberate: a factory reads whatever it needs, the stream target, its own settings section, at the boot apply-point, never at registration. A plugin contributes one factory per method it serves by calling the registrar menu in its `register`, passing the token as a raw string:

```python
registrar.add_log_sink(method="gcp", factory=_make_gcp_log_sink)
```

`register` is **side-effect-free**: it may call the registrar menu and nothing else. That is what keeps `build_registrar` safe to run more than once, at boot and again for the `pipelex plugins list` diagnostic, whose rows show the sinks each plugin contributed as `log sink <method>`.

### `LogSink`

The factory returns a `LogSink` (`pipelex/tools/log/log_sink.py`), an abstract base with one method to implement and two things every sink gets from the base:

```python
class LogSink(ABC):
    processors: list[LogRecordProcessor]  # the slot every sink shares

    @abstractmethod
    def make_handler(self) -> logging.Handler: ...  # built once, at install

    @property
    def handler(self) -> logging.Handler: ...  # the same handler on every read

    def redirect_to_stderr(self) -> None: ...  # a no-op unless the sink writes to a process stream
```

- **`make_handler`** builds the stdlib handler the sink installs on the root logger, and is where a heavy import belongs. It is called once, when boot installs the sink, so selecting a sink is what pays for its dependency and a sink whose package is missing fails there, at boot, with `MissingDependencyError` naming the extra.
- **`processors`** is the slot a cross-cutting transformation hooks into. A processor is a callable that edits a record in place, `Callable[[logging.LogRecord], None]`, and the base runs every processor over each record before the handler formats it, through a filter on the sink's own handler. Redaction is the intended one: appended to the base's list, it reaches every sink, built-in or external, with no sink knowing about it. A processor sees the record the root logger shares with every other handler, so a handler an integration attached to the root logger sees the record as the processors left it only if it runs after this one.
- **`redirect_to_stderr`** exists for the agent CLI, whose stdout is reserved for its structured envelope: a sink that writes to a process stream moves it to stderr, and one that writes to a collector ignores the call.

### What a sink reads off a record

Every sink reads the same record, shaped by the [logging facade](../tools/logging.md): the message is `record.getMessage()`, and everything the call, the bound context or a record factory attached rides as attributes. `carried_attributes(record=...)` in `pipelex/tools/log/log_fields.py` hands a sink exactly that set, in the order the attributes were attached, by subtracting the attributes the stdlib gives every record. An exception a call carried with `include_exception=True` is the record's `exc_info`, the stdlib's own channel, which each sink renders its own way.

Two rules follow for a sink author, and the shipped sinks honour both:

- **A sink serializes on emit, synchronously, on the calling thread.** A field's value rides the record by reference, so a value the caller mutates after the call is not what the record said; reading it at emit is what makes the record a faithful account of the call. A sink that queues, the `otlp` sink on its batching exporter for instance, translates the record into its wire form at emit and queues the translation. The `data` attribute needs no such care: it is already a JSON-ready snapshot of the call.
- **A sink renders every record it is handed and never raises.** A value the wire cannot carry is written as text, a JSON rendering for a mapping, a `repr` for what JSON refuses; a serialization failure is a fact about the value, never a reason to lose the line. A handler failure goes through the stdlib's `handleError`, as any handler's does.

---

## The built-in `LogSinkPlugin`

`pipelex/providers/log_sinks/log_sink_plugin.py` is the reference sink plugin. It is **core-unconditional**, a process needs somewhere for its records to go, so it joins `KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES` and cannot be disabled into a boot with no sink:

```python
class LogSinkPlugin:
    name = "log_sinks"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_log_sink(method=LogSinkMethod.JSON, factory=_make_json_log_sink)
        registrar.add_log_sink(method=LogSinkMethod.CONSOLE, factory=_make_console_log_sink)
        registrar.add_log_sink(method=LogSinkMethod.OTLP, factory=_make_otlp_log_sink)
```

| Sink | What it does | Where it reads its settings |
|------|--------------|-----------------------------|
| `json` | One JSON object per line on the configured stream: `time`, `severity`, `logger`, `message`, `exception` when there is one, then the fields, the context identifiers and `data` flat beside them. The key names are the ones the CloudWatch agent, the Google Cloud Logging agent and any OTLP collector ingest without a parser, and no ANSI ever. What the hosted plane's runner and worker select. | `console_log_target` |
| `console` | The Rich handler with the emoji formatter and every `[runtime.log.rich_log]` setting, byte for byte what the console showed before sinks existed. Rich is imported when the handler is built, and a process that selects another sink never loads it through this path. | `console_log_target`, `[runtime.log.rich_log]` |
| `otlp` | The OpenTelemetry logs signal: a `LoggerProvider` carrying the same service identity as the tracer, a `BatchLogRecordProcessor` and the OTLP HTTP log exporter. The message is the body, the level maps onto the OTel severity scale, the fields, identifiers and `data` ride as attributes (a mapping as JSON text), an exception lands under the `exception.*` semantic-convention keys, and a collector receives the logs beside the spans the runtime already exports. | `[runtime.log.otlp]` |

The `otlp` factory imports the OpenTelemetry logs SDK when it runs, never at register, so registering the built-ins imports none of it, which the import-light guard pins.

### Why `console` is the default

`pipelex/pipelex.toml` ships `sink = "console"`. A user who installs the CLI expects the rendering the CLI always had, the emoji, the colours, the clickable paths, and a default that changed it would be a regression for every terminal. A server is the process that must choose: it selects `json`, and the fail-loud factory is what makes the choice hard to forget. Rich is a hard dependency today, so a server that forgot to select `json` still boots with the console sink; once Rich moves behind the CLI extra, the same server refuses to boot with the extra and the `json` alternative named, rather than shipping ANSI to a log agent.

---

## Selecting a sink by config

`runtime.log.sink` is an **open `str` token**, not a closed enum. The built-ins use `"json"`, `"console"` and `"otlp"`; an external plugin registers its own. A config naming an external token **parses fine**, the token is stored verbatim and its installability is validated later, at registry lookup:

```toml
# .pipelex/pipelex.toml
[runtime.log]
sink = "gcp"          # an out-of-tree sink, selected iff its plugin is installed
```

Whether that token names an *installed* sink is validated at **registry lookup**, not at parse: an unknown token surfaces as `UnknownLogSinkError` at boot, which lists the registered tokens so the fix is obvious.

An external sink has no settings section of its own in `LogConfig`, whose sub-models are the shipped sinks'; until a generic passthrough for external sinks lands, an out-of-tree sink reads its own configuration from the environment or its own file, as an out-of-tree storage provider does.

---

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| `runtime.log.sink` names no registered sink | `UnknownLogSinkError` (lists the registered tokens) |
| the selected sink's package is not installed | `MissingDependencyError` (package + `pipelex[<extra>]` hint), raised at install, at boot |
| two plugins register the same `method` | `DuplicateLogSinkError` (names both plugins) |
| `name` (`"log_sinks"`) in `runtime.plugins.disabled` | `CoreUnconditionalPluginDisabledError` |
| published under the retired `pipelex.plugins` group | `RetiredPluginEntryPointGroupError` |
| entry point raises while loading/registering | `BrokenPluginError` |

The duplicate detection is the same fail-loud `_add` helper the storage and secrets menus use.

---

## Authoring an out-of-tree log sink plugin

A third-party log sink plugin is a distribution that:

1. implements a `LogSink` subclass whose `make_handler` builds the handler and performs whatever SDK import the handler needs, so the module stays import-light; the handler reads the record through `carried_attributes`, serializes on emit, and never raises;
2. defines a plugin class (`name`, `targets_api`, `register`) whose `register` calls `add_log_sink(method="<token>", factory=...)` and nothing else;
3. advertises itself under the `pipelex.plugins.kernel` entry-point group, a log sink being a kernel-layer capability (see [Inference Backend Plugins](inference-backend-plugins.md#shipping-it-as-an-out-of-tree-plugin) for what each group means):

```toml
# pyproject.toml of your plugin package
[project.entry-points."pipelex.plugins.kernel"]
gcp_log_sink = "pipelex_log_gcp.plugin:GcpLogSinkPlugin"
```

Installing the distribution makes the token selectable (`runtime.log.sink = "gcp"`); uninstalling removes it. No core change, no central registration list: *presence* is the source of truth. A discovered plugin can be quarantined without uninstalling via the `runtime.plugins.disabled` denylist.

Use `pipelex plugins list` to see every discovered plugin, what each contributed (`log sink <method>` among the rows), and its denylist state.

---

## Related

- [Logging](../tools/logging.md): the facade, the fields, the context and what a record carries
- [Logging Configuration](../configuration/config-practical/logging-config.md): the `sink` key and each shipped sink's settings
- [Storage Provider Plugins](storage-provider-plugins.md) and [Secrets Provider Plugins](secrets-provider-plugins.md): the sibling config-selected-singleton seams
- [Inference Backend Plugins](inference-backend-plugins.md): the shared discovery and denylist machinery
- [Error Model](error-model.md): how these errors render and dereference
