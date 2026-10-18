---
title: "pipelex.run.already_exists"
description: "A run with this id already exists: what the Pipelex error code pipelex.run.already_exists means, who must act and what to do."
---

# pipelex.run.already_exists

**A run with this id already exists**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.run.already_exists` |
| Family | [`pipelex.run`](../../index.md#pipelex-run): Pipelex's extensions to runs. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The caller chose the run's id, which Pipelex allows as an extension of the protocol, whose run id is always the runner's, and a run already holds that id.

## What to do

Start the run with a new id, or with none so that the runner assigns it. To see the run that holds the id, read it by that id.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Start the run with another id, or with none so that the runner assigns one. |
| Any other reader | `change_input` | Pass this to the caller, who chose the run id '`{pipeline_run_id}`', which is already taken. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A run with the id '`{pipeline_run_id}`' already exists.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `pipeline_run_id` | `identifier` | The run id the caller chose. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
