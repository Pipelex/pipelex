---
description: "Get a Pipelex API key through your browser, or paste one, and save it so methods run on the hosted Pipelex API."
---

# Login Command

`pipelex login` gets a Pipelex API key (`plx_sk_…`) and saves it where a hosted run reads it, so `pipelex run … --hosted`, and every run when [`[run] execution = "hosted"`](../../configuration/config-practical/run-config.md), works with nothing exported in your shell.

```bash
pipelex login
pipelex login --paste
```

[`pipelex init`](init.md) runs the same login when you choose to run on the hosted Pipelex API, so you only need this command to sign in on its own, to replace a key, or on a machine without a browser.

## What It Does

1. It opens the Pipelex app in your browser, on a page that creates a key for the command line, and prints the same link in case the browser does not open. Sign in, or create an account, on that page.
2. The app hands the new key back to `pipelex login`, which waits for it on a port of `127.0.0.1` it opened for this one login. It waits up to five minutes.
3. It checks the key: the key must start with `plx_sk_`, and the hosted API must accept it, which it asks by reading the account the key belongs to.
4. It saves the key as `PIPELEX_API_KEY` in `~/.pipelex/.env` (or in the `.env` of the directory `PIPELEX_HOME` names), the file Pipelex loads into its environment at startup.

The key is never printed. The `.env` file is readable and writable by you only (mode `0600`), and every other line in it, your provider keys and comments included, is kept as it was. A `PIPELEX_API_KEY` already in the file is replaced.

**The check decides what is saved:**

- When the hosted API accepts the key, it is saved, and the command says which account it belongs to.
- When the hosted API refuses it (HTTP 401 or 403), nothing is saved and the command exits with code `1`, naming the status.
- When the key cannot be checked, because the hosted API cannot be reached or answers anything else, it is saved anyway, with a warning saying why it was not checked.
- A value that does not start with `plx_sk_` is refused before any check.

**The handover is protected.** Each login sends the app a random `state` value along with the port, and the app sends it back with the key. A request to the port that does not carry this login's `state` is refused and its key discarded: any page open in your browser can send a request to a local port, so a key that arrives without it did not come from the page this login opened. The command says so in the terminal and keeps waiting.

When no key arrives in time, the command exits with code `1` and names `pipelex login --paste`.

## Paste a Key Instead

```bash
pipelex login --paste
```

On a machine where no browser can reach a local port, such as a remote server over SSH or a CI job, create a key in the Pipelex app on any machine, then paste it at the prompt. The key is not shown as you type. It goes through the same check and is saved the same way.

In CI, you can also skip the file entirely and set `PIPELEX_API_KEY` as a secret of the job.

## Other Apps and APIs

| Variable | What it changes | Default |
| --- | --- | --- |
| `PIPELEX_APP_URL` | The Pipelex app the browser opens, given as an origin (`scheme://host[:port]`, no path) | `https://app.pipelex.com` |
| `PIPELEX_BASE_URL` | The hosted API the key is checked against, and that hosted runs go to | `https://api.pipelex.com` |

A value that is not an origin is refused before anything opens. Most people never set either; they point the command at a development or staging plane, for instance:

```bash
PIPELEX_APP_URL=https://app-dev.pipelex.com PIPELEX_BASE_URL=https://api-dev.pipelex.com pipelex login
```

Set them in `~/.pipelex/.env` to keep them for every command.

## Exit Codes

- `0`: a key was saved, checked or not.
- `1`: nothing was saved: no key arrived in time, none was pasted, the value was not a Pipelex API key, the hosted API refused it, or `PIPELEX_APP_URL` is not an origin.

## Related

- [Init](init.md): the first-run setup, which asks where your runs execute and runs this login for the hosted Pipelex API
- [Running on the Hosted API](run.md#running-on-the-hosted-api): what a hosted run sends, uploads and saves
- [Run Configuration](../../configuration/config-practical/run-config.md): the `[run] execution` default
