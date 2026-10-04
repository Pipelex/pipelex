"""Test data for PipeJudge E2E tests."""

from typing import ClassVar


class PipeJudgeTestCases:
    """Inputs pinned with the verdicts a live judgment returns for them."""

    URGENT_MESSAGE: ClassVar[str] = "Our production database has been down for an hour and no customer can log in. Please help."
    BILLING_TICKET: ClassVar[str] = "I was charged twice for my subscription this month and I would like a refund for the second charge."
    BLOCKING_REPORT: ClassVar[str] = "Since this morning's release, clicking Save on any invoice crashes the app, so nobody can issue an invoice."
