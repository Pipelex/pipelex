import asyncio
import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents
from mthds.method_tree.models import MethodTree, TreeLimits
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    scoped_current_library,
    set_current_library,
)
from pipelex.libraries.method_load_threads import METHOD_LOAD_THREADS
from pipelex.libraries.method_trees import list_local_method_tree
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pipelex.pipeline.execution_seams import acquire_library_async
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.plugins.pipe_func_package_offer_registry import (
    PipeFuncPackageOffer,
    PipeFuncPackageOfferRegistry,
    PipeFuncPackageOfferRequest,
    PipeFuncPackageRefusal,
)

#: How long a test waits for a thread to reach a point it signals, which bounds a regression's run.
_SIGNAL_TIMEOUT_SECONDS = 10.0

_ECHO_MTHDS = b"""\
domain = "off_the_loop"
main_pipe = "echo"

[pipe.echo]
type = "PipeCompose"
description = "Echo the data"
inputs = { data = "Text" }
output = "Text"
template = "$data"
"""

# A method whose tree holds Python and a requirements.txt, so its every load asks the package-offer factory.
_TREE_WITH_REQUIREMENTS = {
    "main.mthds": _ECHO_MTHDS,
    "helpers/constants.py": b"ANSWER = 42\n",
    "requirements.txt": b"pandas>=2\n",
}


def _all_in_the_method_load_pool(thread_names: list[str]) -> bool:
    """Whether every one of these calls ran, and at least one did, in a thread of the method-load pool, which runs no loop."""
    return bool(thread_names) and all(thread_name.startswith(METHOD_LOAD_THREADS.name) for thread_name in thread_names)


class _RecordingOffer:
    """The package-offer factory of the neutral `sandbox` mode, noting, at each call, the thread it was called on.

    Once ``hold`` is called, a call signals ``started`` and blocks until ``release`` is set, as a factory resolving the
    requirements does while it works.
    """

    def __init__(self) -> None:
        self.thread_names: list[str] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def hold(self) -> None:
        self.release.clear()

    def __call__(self, request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:  # ruff: ignore[unused-method-argument]
        self.thread_names.append(threading.current_thread().name)
        self.started.set()
        if not self.release.wait(timeout=_SIGNAL_TIMEOUT_SECONDS):
            msg = "the held factory was never released"
            raise AssertionError(msg)
        return PipeFuncPackageOffer(
            environment="the sandbox under test",
            distributions={"pandas": "2.2.3"},
            marker_environment={"python_version": "3.12", "sys_platform": "linux"},
        )


@pytest.fixture(name="recording_offer")
def recording_offer_fixture(mocker: MockerFixture, sandbox_hosted_mode: None) -> _RecordingOffer:  # ruff: ignore[unused-function-argument]
    """Run PipeFunc steps in the neutral `sandbox` mode, whose plugin's factory records the thread of each call."""
    offer = _RecordingOffer()
    mocker.patch(
        "pipelex.libraries.package_environments.get_pipe_func_package_offer_registry", return_value=PipeFuncPackageOfferRegistry({"sandbox": offer})
    )
    return offer


@pytest.fixture(name="held_tree")
def held_tree_fixture(tmp_path: Path) -> Generator[Path, None, None]:
    """The tree with requirements, written and held as a host holds a request's tree, its directory yielded."""
    written = write_method_tree(
        contents=_TREE_WITH_REQUIREMENTS, destination=tmp_path / "tree", expected_digest=digest_of_contents(_TREE_WITH_REQUIREMENTS)
    )
    with WRITTEN_METHOD_TREES.holding(tree=written):
        yield tmp_path / "tree"


@pytest.mark.asyncio(loop_scope="class")
class TestMethodLoadsOffTheEventLoop:
    async def test_a_validation_of_a_method_tree_asks_the_package_offer_off_the_event_loop(
        self, held_tree: Path, recording_offer: _RecordingOffer
    ) -> None:
        result = await validate_bundle(method_dir=held_tree)

        assert [pipe.code for pipe in result.pipes] == ["echo"]
        assert _all_in_the_method_load_pool(recording_offer.thread_names), recording_offer.thread_names

    async def test_the_in_process_validator_lists_the_tree_once_off_the_event_loop_and_draws_its_graph_from_it(
        self, mocker: MockerFixture, held_tree: Path, recording_offer: _RecordingOffer
    ) -> None:
        """The validation lists the tree off the loop, and the entry pipe its graph draws is read from that same listing."""
        listing_threads: list[str] = []

        def list_after_noting_the_thread(*, handed_over: Path, limits: TreeLimits | None = None) -> MethodTree:
            listing_threads.append(threading.current_thread().name)
            return list_local_method_tree(handed_over=handed_over, limits=limits)

        mocker.patch("pipelex.libraries.method_tree_listing.list_local_method_tree", side_effect=list_after_noting_the_thread)

        report = await validate_bundles_in_process(method_dir=held_tree)

        assert report.graph_spec is not None
        assert len(listing_threads) == 1
        assert _all_in_the_method_load_pool(listing_threads), listing_threads
        assert _all_in_the_method_load_pool(recording_offer.thread_names), recording_offer.thread_names

    async def test_an_asynchronous_acquisition_loads_off_the_event_loop_and_leaves_the_library_current(
        self, held_tree: Path, recording_offer: _RecordingOffer
    ) -> None:
        library_manager = get_library_manager()
        outer_library_id = get_current_library_id_or_none()

        library_id, qualified_main_pipe = await acquire_library_async("off-the-loop-acquisition", library_dirs=[str(held_tree)])
        try:
            assert library_id == "off-the-loop-acquisition"
            assert qualified_main_pipe is None
            assert get_current_library_id_or_none() == library_id
            assert _all_in_the_method_load_pool(recording_offer.thread_names), recording_offer.thread_names
        finally:
            library_manager.teardown(library_id=library_id)
            if outer_library_id is not None:
                set_current_library(library_id=outer_library_id)
            else:
                clear_current_library()

        assert outer_library_id != library_id

    async def test_a_load_called_on_the_event_loop_is_refused_before_the_package_offer_is_asked(
        self, held_tree: Path, recording_offer: _RecordingOffer
    ) -> None:
        """The factory is never called on a thread running an event loop: a load called on the loop itself fails loudly."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id), pytest.raises(PipelexUnexpectedError, match="thread running an event loop"):
                library_manager.load_libraries(library_id=library_id, library_dirs=[held_tree])
        finally:
            library_manager.teardown(library_id=library_id)

        assert recording_offer.thread_names == []

    async def test_a_cancelled_acquisition_tears_its_library_down_once_the_load_has_ended(
        self, mocker: MockerFixture, held_tree: Path, recording_offer: _RecordingOffer
    ) -> None:
        """A load cannot be interrupted in its thread, so the library is torn down only once the load is over."""
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        recording_offer.hold()

        acquisition = asyncio.create_task(acquire_library_async("off-the-loop-cancelled", library_dirs=[str(held_tree)]))
        assert await asyncio.to_thread(recording_offer.started.wait, _SIGNAL_TIMEOUT_SECONDS), "the load never asked the factory"
        acquisition.cancel()
        await asyncio.sleep(0.05)
        assert not acquisition.done(), "the cancellation went through while the load was still running"
        assert teardown_spy.call_count == 0

        recording_offer.release.set()
        with pytest.raises(asyncio.CancelledError):
            await acquisition

        teardown_spy.assert_called_once_with(library_id="off-the-loop-cancelled")
        assert _all_in_the_method_load_pool(recording_offer.thread_names), recording_offer.thread_names
