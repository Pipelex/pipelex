from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.plugins.linkup.linkup_search_worker import LinkupSearchWorker

# Cache of search worker instances by provider prefix
_search_workers: dict[str, SearchWorkerAbstract] = {}


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
            worker = LinkupSearchWorker()
        case _:
            msg = f"Unknown search provider: '{provider}' (from model handle '{model_handle}')"
            raise ValueError(msg)

    _search_workers[provider] = worker
    return worker
