import threading
from collections.abc import Iterator

import pytest

from tests.unit.pipelex.tools.misc.fetch_ssrf_guard.loopback import LoopbackHandler, LoopbackServer


@pytest.fixture
def loopback_server() -> Iterator[LoopbackServer]:
    server = LoopbackServer(("127.0.0.1", 0), LoopbackHandler)
    server.hits = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()
