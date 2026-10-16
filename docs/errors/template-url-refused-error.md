---
title: "Relative URL refused"
description: "Reference for the `TemplateUrlRefusedError` Pipelex error class."
---

<!-- pipelex:authored -->

# Relative URL refused

A relative URL of an HTML document names no image, stylesheet or font of its template's method tree, so the print reads nothing.

| Field | Value |
|---|---|
| `error_type` | `TemplateUrlRefusedError` |
| `title` | Relative URL refused |
| `type_uri` | `https://docs.pipelex.com/latest/errors/template-url-refused-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.cogt.doc_gen.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |

## When it is raised

A relative URL in a `PipeDocGen` HTML template names a file of the template's method, resolved against the template file, or against the bundle file of an inline template ([Images, stylesheets and fonts beside a template](../building-methods/pipes/pipe-operators/PipeDocGen.md#images-stylesheets-and-fonts-beside-a-template)). The print refuses it, and reads nothing, when:

- **It names no file of the method.** It climbs above the folder holding `METHODS.toml`, it names a folder or a missing file, or it names a file the method leaves out, such as a hidden or a gitignored one.
- **It names a file that is not an image, a stylesheet or a font.** A document reads only those from its method, whatever the URL's origin, so a URL a run's input supplies cannot make the document carry the method's Python, its bundles, its manifest or its data, as a `rel="attachment"` link would.
- **The template belongs to no method's folder**, such as an inline template of a bundle loaded from a string with no file sent beside it, where a relative URL names no file at all.
- **A document with no HTML names a method file.** Only the relative URLs of an HTML template name one.

A URL the template writes as it is, such as `<img src="logo.png">`, is checked when the method loads, so this error is raised at print for a URL the template builds from the run's inputs. `refusal_code` carries the MTHDS standard's refusal code when the standard names the reason, and is `None` otherwise. The message names the method's files by their paths in the method, never by a path on the machine that prints.

[Back to Error Reference](index.md)
