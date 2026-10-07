---
description: "Run methods on the hosted Pipelex API from Python with pipelex-sdk's PipelexAPIClient, the hosted half of the Pipelex Python API."
---

# Running on the Hosted API from Python

The Pipelex Python API has two halves. `PipelexMTHDSProtocol`, shown in [Executing Pipelines](executing-pipelines.md), runs a method in your own process, with your own inference backends and provider keys. **`PipelexAPIClient`**, from the `pipelex-sdk` package, runs it on the hosted Pipelex API, with only a Pipelex API key. `pipelex-sdk` is a dependency of `pipelex`, so it is installed with it, and it is the client `pipelex run --hosted` uses under the hood.

Use the client directly: it has no Pipelex wrapper, and it needs no `Pipelex.make()`, since nothing runs locally.

## The Key and the Origin

The client reads its key from `PIPELEX_API_KEY` and its origin from `PIPELEX_BASE_URL`, falling back to `https://api.pipelex.com`. Both can also be passed to the constructor, as `api_key=` and `base_url=`. The client reads the process environment only. To use a key saved in `~/.pipelex/.env`, as `pipelex run --hosted` does, import `pipelex.system.environment` before creating the client: importing it loads `~/.pipelex/.env` (or the one in `PIPELEX_HOME`), then a `.env` in the working directory.

## Running a Method

The client runs the same three sources the CLI does: a published method by its address (`method_ref`), a method stored on the hosted platform by its catalog id (`method_id`), or your own bundle by its contents (`mthds_contents`). `start_and_wait` starts the run and polls it until it ends, so a long run is not cut short by a synchronous request's timeout.

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

To run your own bundle, send its contents and name the pipe, or leave `pipe_code` out to run the bundle's `main_pipe`:

```python
from pathlib import Path

results = await client.start_and_wait(
    pipe_code="summarize",
    mthds_contents=[Path("my_bundle.mthds").read_text(encoding="utf-8")],
    inputs={"text": "…"},
)
```

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
- `prepare_inputs` reads the signature through a route that cannot load a method calling another method by its address (`github.com/…`), so it refuses such a method, which `start_and_wait` runs. Give its files as `https://` URLs and start the run without preparing the inputs.

## Errors

A failure is one of the SDK's typed errors, from `pipelex_sdk.errors`, all subclasses of the protocol's `PipelineRequestError`, with one exception: `start` and `execute`, which the client inherits from the MTHDS protocol client, let httpx's transport errors through. A `ConnectError` or a `ConnectTimeout` means the request never left your machine. A `ReadError`, a `RemoteProtocolError` or a `ReadTimeout` can come after the hosted API received it, so a run may exist with no id returned: check the run history on app.pipelex.com before starting it again.

- `ApiResponseError` is a refusal the hosted API answered: `status`, the reason in `server_message`, the next step in `user_action.detail` when the server advised one, and `validation_errors` locating the faults of a bundle it refused to load.
- `RunFailedError` is a run that started and failed; `error` holds its stored report, with the runner's `error_type`, `message`, `error_domain` and `user_action`.
- `RunTimeoutError` is a run that outlived the wait; it keeps running, and `run_id` reads its result later with `wait_for_result`.
- `ApiUnreachableError` is a hosted API that could not be reached at all, on the routes the SDK owns: the signature read, the uploads, and the polling of a started run.
- `InputPreparationError` and its subclasses are a local file that could not be read or uploaded.

## Related Documentation

- [Running on the Hosted API](../../tools/cli/run.md#running-on-the-hosted-api) — The same runs from `pipelex run --hosted`
- [Run Configuration](../../configuration/config-practical/run-config.md) — Making hosted runs the CLI's default
- [Executing Pipelines](executing-pipelines.md) — The local half of the Python API
