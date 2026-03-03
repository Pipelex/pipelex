from pipelex.cogt.search.fetch_worker_abstract import FetchWorkerAbstract
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract

# Cache of search worker instances by provider prefix
_search_workers: dict[str, SearchWorkerAbstract] = {}
_fetch_workers: dict[str, FetchWorkerAbstract] = {}


def get_search_worker(model_handle: str) -> SearchWorkerAbstract:
    """Get a search worker instance for the given model handle.

    The model handle format is "provider/variant" (e.g., "linkup/standard", "linkup/deep").
    The provider prefix determines which worker implementation to use.

    Args:
        model_handle: The search model handle (e.g., "linkup/standard")

    Returns:
        A SearchWorkerAbstract instance for the provider
    """
    provider = model_handle.split("/", maxsplit=1)[0] if "/" in model_handle else model_handle

    if provider in _search_workers:
        return _search_workers[provider]

    worker: SearchWorkerAbstract
    match provider:
        case "linkup":
            from pipelex.plugins.linkup.linkup_worker import LinkupWorker  # noqa: PLC0415

            worker = LinkupWorker()
        case _:
            msg = f"Unknown search provider: '{provider}' (from model handle '{model_handle}')"
            raise ValueError(msg)

    _search_workers[provider] = worker
    return worker


def get_fetch_worker(provider: str) -> FetchWorkerAbstract:
    """Get a fetch worker instance for the given provider.

    Args:
        provider: The fetch provider name (e.g., "linkup")

    Returns:
        A FetchWorkerAbstract instance for the provider
    """
    if provider in _fetch_workers:
        return _fetch_workers[provider]

    worker: FetchWorkerAbstract
    match provider:
        case "linkup":
            from pipelex.plugins.linkup.linkup_worker import LinkupWorker  # noqa: PLC0415

            worker = LinkupWorker()
        case _:
            msg = f"Unknown fetch provider: '{provider}'"
            raise ValueError(msg)

    _fetch_workers[provider] = worker
    return worker
