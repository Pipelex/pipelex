# Running on the Hosted API from Python

The Pipelex Python API has two halves. `PipelexMTHDSProtocol`, shown in [Executing Pipelines](executing-pipelines.md), runs a method in your own process, with your own inference backends and provider keys. **`PipelexAPIClient`**, from the `pipelex-sdk` package, runs it on the hosted Pipelex API, with only a Pipelex API key. `pipelex-sdk` is a dependency of `pipelex`, so it is installed with it, and it is the client `pipelex run --hosted` uses under the hood.

Use the client directly: it has no Pipelex wrapper, and it needs no `Pipelex.make()`, since nothing runs locally. Its requests identify themselves in their `User-Agent` as pipelex-sdk's, while the CLI's lead with `pipelex-cli/<version>`; to put your own application's name in front, pass pipelex-sdk's `app_info` to the constructor.

## The Key and the Origin

The client reads its key from `PIPELEX_API_KEY` and its origin from `PIPELEX_BASE_URL`, falling back to `https://api.pipelex.com`. Both can also be passed to the constructor, as `api_key=` and `base_url=`. The client reads the process environment only. To use a key saved in `~/.pipelex/.env`, as `pipelex run --hosted` does, import `pipelex.system.environment` before creating the client: importing it loads `~/.pipelex/.env` (or the one in `PIPELEX_HOME`), then a `.env` in the working directory. Each of those files replaces the variables it sets, so a `PIPELEX_API_KEY` or `PIPELEX_BASE_URL` set in one of them wins over the same variable already in the process environment, whether exported in your shell or set by your program before the import. To use a key of your own whatever the files say, pass it to the constructor as `api_key=`.

## Running a Method

The client runs the same three sources the CLI does: a published method by its address (`method_ref`), a method stored on the hosted platform by its catalog id (`method_id`), or your own method as its tree, the MTHDS protocol's `files` map from each file's path in the method's folder to its content, which the client builds for you from a folder or a `.mthds` file (`tree`) or from each file's bytes or text by its path (`contents`). `start_and_wait` starts the run and polls it until it ends, so a long run is not cut short by a synchronous request's timeout.

```python
import asyncio

from pipelex_sdk.client import PipelexAPIClient


async def main() -> None:
    async with PipelexAPIClient() as client:
        results = await client.start_and_wait(
            method_ref="github.com/Pipelex/methods/text_stats@v0.1.7",
            inputs={"text": "Hello world. Second sentence."},
        )
    print(results.pipeline_run_id)
    print(results.main_stuff["text"])


asyncio.run(main())
```

`results.main_stuff` is the main output's content, as JSON. `results.working_memory` holds every stuff of the run, each naming its concept by ref, and `results.graph_spec` the run's execution graph.

To run your own method, send its tree and name the pipe, or leave `pipe_code` out to run the method's entry pipe:

```python
from pathlib import Path

results = await client.start_and_wait(
    pipe_code="summarize",
    tree=Path("my_bundle.mthds"),
    inputs={"text": "…"},
)
```

The client lists the tree as every MTHDS client lists it, so a `.gitignore`d or hidden file, and a run's `inputs.json`, stay out. A small tree travels inline; a larger one by the hash of each file, once the client has uploaded the files the hosted API lacks.

## Inputs That Name Local Files

The hosted API cannot read your machine's files, so a document or an image given as a local path is uploaded first. `prepare_inputs` reads the pipe's signature from the hosted API, uploads each local file found at a document or image input, and returns the inputs with each one replaced by its storage URI. It takes the method the same way the run does, and the pipe as its qualified ref, `domain.pipe_code`:

```python
prepared = await client.prepare_inputs(
    method_ref="github.com/Pipelex/methods/documents@v0.1.7",
    pipe_ref="documents.extract_document_text",
    inputs={"document": "invoices/march.pdf"},
)
results = await client.start_and_wait(
    method_ref="github.com/Pipelex/methods/documents@v0.1.7",
    pipe_code="extract_document_text",
    inputs=prepared.inputs,
)
```

A relative path is read from the working directory, and a `file://` URI is not decoded, so pass the path itself. `http(s)://` URLs are passed through for the hosted API to fetch. Call `prepare_inputs` only when the inputs name a local file: other inputs can go to the run as they are.

Two cases where `pipelex run --hosted` goes further than `prepare_inputs`:

- `prepare_inputs` refuses an explicit `None` at a document or image input. Leave an optional file out of the inputs rather than setting it to `None`. The CLI uploads the files itself and keeps the `null` for the run.
- `prepare_inputs` reads the signature through a route that loads only the packages the request sends in `dependencies`, so it refuses a method calling another method by its address (`github.com/…`) whose package is not sent with it, which `start_and_wait` runs, the hosted API fetching the package itself. Send that package in `dependencies`, or give the files as `https://` URLs and start the run without preparing the inputs.

## Errors

A failure is one of the SDK's typed errors, from `pipelex_sdk.errors`, all subclasses of the protocol's `PipelineRequestError`, and every one carries what went wrong as the MTHDS standard's problem document, `exc.problem`. Branch on `exc.problem.code`, the stable name of the case in the [error registry](../../errors/index.md), never on an HTTP status or the wording of a message. Beside its code, the problem says who acts on the failure (`exc.problem.effective_domain`), whether sending the same thing again can help (`exc.problem.effective_retry`: `yes`, `no`, or `outcome_unknown` when a run may have started), how long to wait first when the answer said (`retry_after`, in seconds), what to do next (`next_step.kind` and `next_step.detail`), and the faults one by one when there are several (`errors`, each with its own `code`, `detail` and `location`).

- `ApiResponseError` is an answer the hosted API, or a server in front of it, gave. Its problem is the answer's own problem document, as the hosted API answers every refusal, with the runner's own code and next step. An answer that is no problem document, such as a gateway's error page, is read from its status: `auth.missing_credential` for a `401`, `auth.invalid_credential` for a `403`, `request.not_found` for a `404`, `runtime.unavailable` with `retry` `yes` for a `408`, a `429`, a `502`, a `503` or a `504`, `runtime.unexpected` for a `500`, and `client.response_unreadable` naming the status for any other. `status` is the answer's HTTP status and `request_id` the id to quote to support.
- `RunFailedError` is a run that started and failed. Its problem is `run.failed`, naming the run and its terminal status, and `run_error` is the run's own problem, why it did not succeed, under its own code, with its own retry verdict and next step, or `None` when the run stored none.
- `RunTimeoutError` is a run that outlived the wait. Its problem is `client.follow_failed`: the run keeps running, and `run_id` reads its result later with `wait_for_result`.
- `ApiUnreachableError` is a request that got no answer, on every route, `start` and `execute` included. Its problem is `client.unreachable` naming the base URL, or `client.timeout` naming the time limit for a request whose time ran out. Its `__cause__` is httpx's exception, and its `network_code` names the failure: `ABORT_TIMEOUT` for a read or a write that timed out, otherwise httpx's class name, such as `ConnectError`, `ConnectTimeout`, `ReadError` or `RemoteProtocolError`.
- `InputPreparationError` and its subclasses are a local file that could not be read or uploaded.
- `MethodFileTransferError` is a file of a tree sent by hash that could not be uploaded to the hosted API's storage before the request, so nothing was started. Its `reason` says why, `unreachable`, `storage_error`, `refused` or `mismatch`, and its problem's retry verdict whether the same call can succeed later, which holds for `unreachable` and `storage_error`.

### A Start That Got No Answer

A failure of `start` or `execute` says whether the run may have been created: its problem is then `client.outcome_unknown`, whose retry verdict is `outcome_unknown`. pipelex-sdk reads it on the start or the execute request alone. An `ApiUnreachableError` reads so unless the transport failure proves the request never left your machine: a connection that could not be made, or a failure on a request the call sends before the run's, such as the blob check of a tree sent by hash, created no run, so starting again is safe. A read or a write that failed or timed out, a connection closed once the request had left, a proxy's failure or a TLS handshake that was dropped can each come after the hosted API received the request. So can a gateway's bare answer to the start, a `408` or a `5xx` other than `501`, which arrives as an `ApiResponseError`. In those cases a run may exist with no id returned, so check the run history on app.pipelex.com before starting it again.

```python
from mthds.protocol.problem.registry import RetryVerdict
from pipelex_sdk.errors import PipelexRequestError

try:
    started = await client.start(method_ref="github.com/Pipelex/methods/text_stats@v0.1.7", inputs={"text": "Hello world."})
except PipelexRequestError as exc:
    match exc.problem.effective_retry:
        case RetryVerdict.OUTCOME_UNKNOWN:
            ...  # A run may exist: look it up in the run history before starting again.
        case RetryVerdict.YES:
            ...  # No run was created: wait `exc.problem.retry_after` seconds when it says, then start again.
        case RetryVerdict.NO:
            ...  # Starting again changes nothing: do what `exc.problem.next_step.detail` says first.
```

`start_and_wait` sends more than the start, so tell its requests apart with its two callbacks. `on_starting` is called right before each request that may create a run is sent, and `on_started` with the acknowledgement once the run exists. A failure before `on_starting` was called started nothing, a failure after `on_started` concerns a run whose id you hold, which `wait_for_result` follows, and only a failure in between needs its retry verdict read as above.

`pipelex run --hosted` and `pipelex-agent run --runner hosted` draw the same line, and report a connection lost on the run request as pipelex's own `HostedRunOutcomeUnknownError`. `PipelexAPIClient` never raises that error, so a program that calls the client directly reads the problem itself.

## Related Documentation

- [Running on the Hosted API](../../tools/cli/run.md#running-on-the-hosted-api) — The same runs from `pipelex run --hosted`
- [Run Configuration](../../configuration/config-practical/run-config.md) — Making hosted runs the CLI's default
- [Executing Pipelines](executing-pipelines.md) — The local half of the Python API
