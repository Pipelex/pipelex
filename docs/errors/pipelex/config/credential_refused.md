---
title: "pipelex.config.credential_refused"
description: "A service refused the configured credential: what the Pipelex error code pipelex.config.credential_refused means, who must act and what to do."
---

# pipelex.config.credential_refused

**A service refused the configured credential**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.config.credential_refused` |
| Family | [`pipelex.config`](../../index.md#pipelex-config): The runtime's own configuration. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A service that is not an inference provider, such as a log sink or a storage, refused the deployment's credential. An inference provider refusing its key is `provider.credential_refused` instead.

## What to do

If you run the runtime, renew or correct the credential. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `check_credentials` | Check the credential the `{surface}` configuration holds for the service '`{service}`'. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A service the runtime depends on refused the credential it is configured with.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `surface` | one of `log_sink`, `storage` (operator-only) | The part of the configuration that holds the credential. |
| `service` | `identifier` (operator-only) | The service that refused it. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
