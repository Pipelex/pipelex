---
description: "Choose which installed document engine prints a PipeDocGen format when more than one can, and how a deployment that must not print documents refuses them at load."
---

# Document Generation Configuration

Configuration section: `[runtime.doc_gen]`

## Overview

A [`PipeDocGen`](../../building-methods/pipes/pipe-operators/PipeDocGen.md) step asks for a format (`pdf`, `xlsx`, `docx` or `pptx`), and its template decides the source a document engine prints it from: the layout of the inputs when it has no template, HTML for a `pdf` with an HTML template, or an office template file. Document engines are plugins, and each registers for a format and a source; open Pipelex ships one, the built-in `reportlab` engine, which prints a `pdf` without a template. See [Document Engine Plugins](../../under-the-hood/document-engine-plugins.md) for how they register.

When exactly one installed engine prints a format from a source, Pipelex uses it, and there is nothing to configure. This section only matters when two installed engines print the same format from the same source:

```toml
[runtime.doc_gen]
engines = {}
```

The value above is the default.

## Choosing an engine

`engines` maps a format and a source, written `"<format>.<source>"`, to the name of the engine that prints them:

```toml
[runtime.doc_gen]
engines = { "pdf.layout" = "reportlab" }
```

The sources are `layout`, `html` and `template_file`. When two installed engines print the same key and the configuration names neither, or when it names an engine that is not installed, a method with a step that needs that key is refused when it loads, with [`DocumentEngineChoiceError`](../../errors/document-engine-choice-error.md).

## Refusing documents altogether

A step whose format and source no installed engine prints is refused when its method loads, with [`DocGenEngineMissingError`](../../errors/doc-gen-engine-missing-error.md), before a run spends anything. So a deployment that must not print documents needs no setting of its own: it disables the built-in engine in the plugin denylist and installs no other.

```toml
[runtime.plugins]
disabled = ["reportlab"]
```

Every `PipeDocGen` step is then refused at load, and the error names the plugin that would print it.
