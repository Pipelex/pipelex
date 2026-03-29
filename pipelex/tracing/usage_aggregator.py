"""Aggregates usage report events from a trace event stream."""

from collections.abc import Sequence

from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.tracing.trace_events import TraceEvent, UsageReportEvent


class UsageAggregator:
    """Extracts token usage records from a flat list of trace events."""

    @staticmethod
    def aggregate(events: Sequence[TraceEvent]) -> list[AnyTokensUsage]:
        """Collect all UsageReportEvent token usage records, preserving order.

        Args:
            events: Flat list of trace events (any types mixed).

        Returns:
            List of token usage records from UsageReportEvent entries only.
        """
        return [evt.tokens_usage for evt in events if isinstance(evt, UsageReportEvent)]
