"""The two mappings the ``gcp`` sink owns, read without a handler in the way.

The severity scale and the trace name are pure functions of a level and of a run id, so they are
asserted directly rather than through an entry: what the sink does with them is
``test_log_gcp_sink.py``'s subject.
"""

from __future__ import annotations

import logging

from pipelex.tools.log.gcp_log_sink import GcpLogSeverity, severity_for_level, trace_name_for_run
from pipelex.tools.misc.hash_utils import hash_md5_to_int


class TestGcpLogSinkMapping:
    def test_the_two_custom_levels_land_on_debug(self) -> None:
        assert severity_for_level(levelno=5) is GcpLogSeverity.DEBUG
        assert severity_for_level(levelno=15) is GcpLogSeverity.DEBUG

    def test_a_level_above_critical_still_maps_to_critical(self) -> None:
        assert severity_for_level(levelno=logging.CRITICAL + 10) is GcpLogSeverity.CRITICAL

    def test_the_trace_name_is_the_tracers_own_id_in_32_hex_digits(self) -> None:
        trace_name = trace_name_for_run(project="p", pipeline_run_id="plr-42")
        prefix, _, trace_id = trace_name.rpartition("/")
        assert prefix == "projects/p/traces"
        assert len(trace_id) == 32
        assert int(trace_id, 16) == hash_md5_to_int("plr-42")
