---
title: "pipelex.storage.not_configured"
description: "This deployment serves no storage for that address: what the Pipelex error code pipelex.storage.not_configured means, who must act and what to do."
---

# pipelex.storage.not_configured

**This deployment serves no storage for that address**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.not_configured` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A storage address names a scheme for which this deployment configures no bucket.

## What to do

If you run the runtime, configure the storage for the scheme. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Configure a storage for the scheme '`{scheme}`' on this deployment, then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> This deployment serves no storage for the scheme '`{scheme}`'.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `scheme` | `identifier` | The scheme of the storage address. |

## See also

- [Storage Provider Plugins](../../../under-the-hood/storage-provider-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
