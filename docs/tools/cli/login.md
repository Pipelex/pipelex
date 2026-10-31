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

1. It opens the Pipelex app in your browser, on a page that creates a key for the command line, and prints the same link in case the browser does not open. When no browser can be opened at all, it says so at once: open the link in a browser on this machine, or press Ctrl-C and run `pipelex login --paste`. Sign in, or create an account, on that page.
2. The app hands the new key back to `pipelex login`, which waits for it on a port of `127.0.0.1` it opened for this one login. It waits up to five minutes. The browser then shows "Key received": the key is checked and saved after that page, so the terminal, not the browser, says whether the login worked.
3. It checks the key: the key must start with `plx_sk_`, and the hosted API must accept it, which it asks by reading the account the key belongs to.
4. It saves the key as `PIPELEX_API_KEY` in `~/.pipelex/.env` (or in the `.env` of the directory `PIPELEX_HOME` names), the file Pipelex loads into its environment at startup, with the `PIPELEX_BASE_URL` it was checked against when that file would otherwise send it to another API (see [The Key Keeps Its API](#the-key-keeps-its-api)).

The key is never printed. The `.env` file is readable and writable by you only (mode `0600`), and every other line in it, your provider keys and comments included, is kept as it was. A `PIPELEX_API_KEY` already in the file is replaced.

**The check decides what is saved:**

- When the hosted API accepts the key, it is saved, and the command says which account it belongs to.
- When the hosted API refuses it (HTTP 401 or 403), nothing is saved and the command exits with code `1`, naming the status and the API the key had to belong to, with the `.env` file that set its `PIPELEX_BASE_URL` when one did. The app created a browser login's key for that login, so a refused one is a live key nobody holds: the command says to revoke it on the Developer page of the Pipelex app. Such a refusal usually means `PIPELEX_APP_URL` and `PIPELEX_BASE_URL` name different deployments. A pasted key is still yours, so the command only says to check that it is current and belongs to that API.
- When the key cannot be checked, because the hosted API cannot be reached, answers anything else, or `PIPELEX_BASE_URL` is not an origin, it is saved anyway, with a warning saying why it was not checked. It keeps the API it was meant for as an accepted key does, unless `PIPELEX_BASE_URL` is not an origin, in which case the file's base URL is left as it is.
- A value that does not start with `plx_sk_` is refused before any check.

**A `.env` in the working directory wins.** Pipelex loads the `.env` of the directory a command runs in after `~/.pipelex/.env`, so a `PIPELEX_API_KEY` line there, even an empty one, is what commands run in that directory send. When that file sets another value than the key just saved, `pipelex login` names it, without printing either value: remove the line from it. Both files also win over your shell, since each `.env` Pipelex loads replaces the variables it sets: a `PIPELEX_API_KEY` exported in your shell is read only when neither file sets it.

**The handover is protected.** Each login sends the app a random `state` value along with the port, and the app sends it back with the key. A request to the port that does not carry this login's `state` is refused and its key discarded: any page open in your browser can send a request to a local port, so a key that arrives without it did not come from the page this login opened. The command says so in the terminal and keeps waiting.

When no key arrives in time, the command exits with code `1` and names `pipelex login --paste`.

## The Key Keeps Its API

A key belongs to one Pipelex deployment. When the key was checked against another API than the one `~/.pipelex/.env` names on its own, its `PIPELEX_BASE_URL` or else `https://api.pipelex.com`, the login writes that `PIPELEX_BASE_URL` beside the key, in the same write, and says so. This happens when you log in with `PIPELEX_BASE_URL` exported in your shell, or set in the working directory's `.env`, as for a development plane:

```bash
PIPELEX_APP_URL=https://app-dev.pipelex.com PIPELEX_BASE_URL=https://api-dev.pipelex.com pipelex login
```

A command started without that shell's variables, such as a new terminal or an app launched from the desktop, then sends the key to the API it belongs to, where it would have sent it to `https://api.pipelex.com` and been refused. The Pipelex workshop (`@pipelex/mcp`) reads and writes the same file under the same rule.

Since `~/.pipelex/.env` wins over your shell, a `PIPELEX_BASE_URL` exported afterwards no longer changes where Pipelex commands send the saved key, and a later `pipelex login` checks its key against the file's API too. To use another API, change or remove the `PIPELEX_BASE_URL` line in that file first, then log in again. A `PIPELEX_BASE_URL` in the file that refers to another variable, such as `${DEV_API_URL}`, names an API only where that variable is set, so the login replaces it with the URL that checked the key. A base URL that holds whitespace, a quote, `#`, `$` or a backslash cannot be written to a `.env` file unquoted, so it is left out, with a warning.

## Paste a Key Instead

```bash
pipelex login --paste
```

On a machine where no browser can reach a local port, such as a remote server over SSH or a CI job, create a key in the Pipelex app on any machine, then paste it at the prompt. The key is not shown as you type. It goes through the same check and is saved the same way.

In CI, you can also skip the file entirely and set `PIPELEX_API_KEY` as a secret of the job. The job's value is read as long as no `.env` file Pipelex loads, in the home configuration directory or in the working directory, sets the variable.

## Other Apps and APIs

| Variable | What it changes | Default |
| --- | --- | --- |
| `PIPELEX_APP_URL` | The Pipelex app the browser opens, given as an origin (`scheme://host[:port]`, no path) | `https://app.pipelex.com` |
| `PIPELEX_BASE_URL` | The hosted API the key is checked against, and that hosted runs go to | `https://api.pipelex.com` |

A `PIPELEX_APP_URL` that is not an origin is refused before anything opens. A `PIPELEX_BASE_URL` that is not one is only met when the key is checked, after the browser has handed it back or the key was pasted: the key cannot be checked, so it is saved anyway, with a warning that names `PIPELEX_BASE_URL` and what an origin looks like, and the command exits with code `0`. Correct the value before a hosted run uses it.

Most people never set either; they point the command at a development or staging plane, as [The Key Keeps Its API](#the-key-keeps-its-api) shows. The login saves `PIPELEX_BASE_URL` in `~/.pipelex/.env` itself when the key needs it; set `PIPELEX_APP_URL` there yourself to keep it for every login. Once a `.env` file Pipelex loads sets one of them, that file wins over a value given on the command line, which is then ignored: change the value in the file instead.

## Exit Codes

- `0`: a key was saved, checked or not.
- `1`: nothing was saved: no key arrived in time, none was pasted, the value was not a Pipelex API key, the hosted API refused it, `PIPELEX_APP_URL` is not an origin, or the `.env` could not be written. In that last case the command names the file and the error. A key a browser login received and did not save, refused or unwritable, went unused: revoke it on the Developer page of the Pipelex app, then run `pipelex login` again. A pasted key that could not be saved is still yours to paste again once the file can be written.

## Related

- [Init](init.md): the first-run setup, which asks where your runs execute and runs this login for the hosted Pipelex API
- [Running on the Hosted API](run.md#running-on-the-hosted-api): what a hosted run sends, uploads and saves
- [Run Configuration](../../configuration/config-practical/run-config.md): the `[run] execution` default
