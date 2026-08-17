"""A backend's file path is spelled once, and a path-like backend name cannot escape the directory.

Boot tolerance replays a stale backend file in memory and rebuilds its specs from the result. That
retry must read *the file the loader read* — and until this test existed, that held by coincidence
rather than by construction: the load spelled the path with an f-string and the retry spelled it
with `Path.__truediv__`, which are the same for every ordinary name and differ for exactly one
class. A backend name is a raw top-level table key of the user's own `inference/backends.toml`, TOML
permits a quoted `["/abs/path"]` key, and `Path(directory) / "/abs/path.toml"` discards the
directory. The retry would then read a file the load never saw, and name it in the warning.
"""

from pathlib import Path

from pipelex.cogt.model_backends.backend_library import backend_toml_path


class TestBackendTomlPath:
    def test_an_ordinary_backend_name_lands_beside_its_siblings(self) -> None:
        path = backend_toml_path(backends_dir_path="/home/someone/.pipelex/inference/backends", backend_name="openai")

        assert path == Path("/home/someone/.pipelex/inference/backends/openai.toml")

    def test_an_absolute_backend_name_stays_under_the_backends_directory(self) -> None:
        backends_dir = Path("/home/someone/.pipelex/inference/backends")

        path = backend_toml_path(backends_dir_path=str(backends_dir), backend_name="/etc/passwd")

        assert path.is_relative_to(backends_dir), f"a path-like backend name escaped the backends directory: {path}"
