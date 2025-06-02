import os
from typing import List

import pytest
from pydantic import BaseModel

from pipelex.client.client import PipelexClient
from pipelex.client.protocol import PipeRequest, PipeState
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ImageContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory

from pipelex import pretty_print


class Example(BaseModel):
    pipe_code: str
    dynamic_output_concept: str
    memory: List[Stuff]


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipelexClient:
    @pytest.fixture
    def examples(self) -> List[Example]:
        """
        Fixture providing test examples for API client tests.

        Returns:
            List[Example]: A list of test examples containing different pipe execution scenarios:
                - Text-based question answering with context and excerpts
                - Gantt chart image processing
        """
        return [
            Example(
                pipe_code="retrieve_then_answer",  # pipe_code
                dynamic_output_concept="contracts.Fees",
                memory=[
                    StuffFactory.make_stuff(
                        concept_code="questions.ProjectContext",
                        name="project_context",
                        content=TextContent(
                            text="The project context is a licensing agreement between WebTech Solutions Inc. and DataAnalytics Corp for the use of WebTech's cloud-based data processing platform. The document contains various sections including licensing terms, service levels, and fee structures. The agreement was executed on January 15, 2023, and is valid for a period of 36 months."
                        ),
                    ),
                    StuffFactory.make_stuff(
                        concept_code="answer.Question",
                        name="question",
                        content=TextContent(
                            text="What are the transaction fees for using the WebTech Solutions data processing platform, and how are they calculated?"
                        ),
                    ),
                    StuffFactory.make_stuff(
                        concept_code="questions.TargetConcept",
                        name="target_concept",
                        content=TextContent(text="Fees"),
                    ),
                    StuffFactory.make_stuff(
                        concept_code="basic.ClientInstructions",
                        name="client_instructions",
                        content=TextContent(
                            text="Please focus on the standard transaction fees from Schedule B, not the implementation fees or monthly subscription costs. The client specifically wants to understand if there are percentage-based fees or fixed amount charges for each transaction and what currency they need to pay in. If there are tiered fees based on volume, please identify the standard tier (100,000 to 500,000 transactions)."
                        ),
                    ),
                    StuffFactory.make_stuff(
                        concept_code="native.Text",
                        name="text",
                        content=TextContent(
                            text="""
MASTER SERVICE AGREEMENT
BETWEEN WEBTECH SOLUTIONS INC. AND DATAANALYTICS CORP

EFFECTIVE DATE: January 15, 2023

1. DEFINITIONS
1.1 "Transaction" means each individual data processing request submitted by Licensee to the Platform.
1.2 "Platform" refers to WebTech Solutions' proprietary cloud-based data processing infrastructure and software.
1.3 "Fees" means all charges payable by the Licensee to WebTech as set forth in Schedule B.

2. TERM AND TERMINATION
2.1 This Agreement shall commence on the Effective Date and shall continue for a period of thirty-six (36) months ("Initial Term").

7. PAYMENT TERMS
7.1 Licensee shall pay all Fees in accordance with Schedule B.
7.2 All Fees are exclusive of applicable taxes.
7.3 WebTech shall invoice Licensee on a monthly basis for Transaction Fees incurred during the previous month.
7.4 All invoices are payable within thirty (30) days of receipt.
7.5 Late payments shall accrue interest at a rate of 1.5% per month or the maximum rate permitted by law, whichever is less.

SCHEDULE B - FEE SCHEDULE

1. IMPLEMENTATION FEES
One-time implementation and integration fee: $25,000 USD

2. SUBSCRIPTION FEES
Monthly platform access: $5,000 USD per month

3. TRANSACTION FEES
3.1 Standard Pricing Model:
- 0-100,000 transactions per month: 2.75% of transaction value
- 100,001-500,000 transactions per month: 2.3% of transaction value
- 500,001+ transactions per month: 1.9% of transaction value

3.2 Alternative Fixed Fee Model (available upon request):
- 0-100,000 transactions per month: $0.15 USD per transaction
- 100,001-500,000 transactions per month: $0.12 USD per transaction
- 500,001+ transactions per month: $0.09 USD per transaction

3.3 All percentage-based transaction fees are calculated based on the monetary value of the data being processed.

3.4 Minimum monthly transaction fee: $1,000 USD

9. CURRENCY AND PAYMENT METHODS
9.1 All fees specified in this Agreement are in United States Dollars (USD).
9.2 Licensee may request to be billed in EUR or GBP, subject to WebTech's current exchange rates plus a 1% currency conversion fee.
9.3 Payment methods accepted:
- ACH transfer
- Wire transfer
- Corporate credit card (subject to a 2.5% processing fee)

AMENDMENT 1 TO SCHEDULE B - EFFECTIVE MARCH 1, 2023

Upon mutual agreement between WebTech Solutions Inc. and DataAnalytics Corp, the following modifications to the Transaction Fees in Schedule B are hereby implemented:

For DataAnalytics Corp's European operations only:
- Transaction fees shall be billed at a flat rate of 2.1% of transaction value for all volume tiers
- Minimum monthly transaction fee reduced to €800 EUR
- All European transactions shall be billed in Euros (EUR)

This amendment applies only to transactions originating from DataAnalytics Corp's European business units and does not modify the fee structure for operations in other regions.

"""
                        ),
                    ),
                ],
            ),
        ]

    async def test_execute_pipe(
        self,
        examples: List[Example],
    ):
        """
        Test the execute_pipe method with different examples.

        Args:
            examples: List of test examples from the fixture
        """
        # ruff: noqa
        for example in examples:
            # Create working memory from example data
            memory = WorkingMemory()
            for stuff in example.memory:
                memory.add_new_stuff(name=stuff.stuff_name or stuff.concept_code, stuff=stuff)

            pipe_execute_request = PipeRequest(
                memory=memory,
                dynamic_output_concept=example.dynamic_output_concept,
            )

            # Execute pipe
            client = PipelexClient()
            result = await client.execute_pipe(
                pipe_code=example.pipe_code,
                pipe_execute_request=pipe_execute_request,
                use_local_execution=True,
            )
            pretty_print(result)

            # Verify result
            assert result.pipe_code == example.pipe_code
            assert result.state == PipeState.COMPLETED
            assert result.pipe_output is not None
