---
title: "Hosted local file upload unavailable"
description: "Reference for the `HostedLocalFileUploadUnavailableError` Pipelex error class."
---

<!-- pipelex:generated -->

# Hosted local file upload unavailable

A hosted run's inputs name a local file, and its method calls another method by its address.

| Field | Value |
|---|---|
| `error_type` | `HostedLocalFileUploadUnavailableError` |
| `title` | Hosted local file upload unavailable |
| `type_uri` | `https://docs.pipelex.com/latest/errors/hosted-local-file-upload-unavailable-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.hosted.exceptions` |
| Parent class | [`HostedRunError`](hosted-run-error.md) |
| `user_action` | `change_input` — Pass each local file as an https URL the hosted API can fetch, instead of a path on this machine, then run again |

[Back to Error Reference](index.md)
