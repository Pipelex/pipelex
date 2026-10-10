"""Test data for PipeJudge E2E tests."""

from typing import ClassVar


class PipeJudgeTestCases:
    """Inputs pinned with the evidence and the question each judge sends, and the verdicts a live judgment returns for them."""

    URGENT_MESSAGE: ClassVar[str] = "Our production database has been down for an hour and no customer can log in. Please help."
    BILLING_TICKET: ClassVar[str] = "I was charged twice for my subscription this month and I would like a refund for the second charge."
    BLOCKING_REPORT: ClassVar[str] = "Since this morning's release, clicking Save on any invoice crashes the app, so nobody can issue an invoice."

    # The evidence each prompt renders over its input, and the question each judge asks about it, exactly as sent.
    URGENT_EVIDENCE: ClassVar[str] = f"A message from someone writing to the inbox:\n<message>\n{URGENT_MESSAGE}\n</message>"
    URGENT_QUESTION: ClassVar[str] = "Does this message need an answer today?"
    BILLING_EVIDENCE: ClassVar[str] = f"A support ticket, as the customer wrote it:\n<ticket>\n{BILLING_TICKET}\n</ticket>"
    BILLING_QUESTION: ClassVar[str] = "Which team should handle this support ticket?"
    BLOCKING_EVIDENCE: ClassVar[str] = f"A bug report filed by a user:\n<report>\n{BLOCKING_REPORT}\n</report>"
    BLOCKING_QUESTION: ClassVar[str] = "How severe is the bug this report describes?"

    SEVERITY_LABELS: ClassVar[list[str]] = ["Cosmetic", "Degraded", "Blocking"]

    # The verdicts a live judgment returns, measured on the deck's default judgment model.
    EXPECTED_URGENT_PROBABILITY: ClassVar[float] = 0.98
    EXPECTED_BILLING_PROBABILITY: ClassVar[float] = 1.0
    EXPECTED_BLOCKING_LEVEL: ClassVar[int] = 2
    EXPECTED_BLOCKING_POSITION: ClassVar[float] = 2.0
